"""Tools do agente: consultas determinísticas sobre o SQLite e as regras de domain.py."""
import json
import os
import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from emporio import domain
from emporio.ingest import DB_PATH, _sem_acento, normalizar_email, normalizar_telefone
from emporio.policies import SECOES_CONSULTAVEIS, carregar_secoes, resolver_secao

FUSO_LOJA = ZoneInfo("America/Campo_Grande")
REFERENCE_DATE_PADRAO = "2026-03-25"
CATEGORIA_GRANDE_PORTE = "Baterias e Percussão"
MAX_ALTERNATIVAS = 3
# Palavras do nome que indicam o tipo do instrumento; cor e marca não contam como semelhança.
TIPOS_INSTRUMENTO = {"dreadnought", "folk", "nylon", "aco", "eletrico", "soprano", "concert", "tenor", "baritono"}
TIPOS_ATENDIMENTO = {
    "arrependimento": "A equipe entra em contato para combinar a devolução. Reembolso na mesma forma "
                      "de pagamento em até 10 dias úteis; frete de devolução por conta da loja.",
    "troca": "A equipe entra em contato para avaliar a troca.",
    "reclamacao": "Encaminhado ao responsável. Prazo de retorno: 24 horas úteis.",
    "exclusao_lgpd": "A equipe entra em contato para tratar a exclusão dos dados.",
    "caso_omisso": "Encaminhado à gerência, que retorna ao cliente.",
}
_SECOES = carregar_secoes()


def conectar(db_path=DB_PATH) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"{db_path} não existe; rode: python -m emporio.ingest")
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def data_referencia() -> date:
    """O "hoje" dos prazos: os pedidos terminam em mar/2026 (ver README)."""
    return date.fromisoformat(os.environ.get("REFERENCE_DATE", REFERENCE_DATE_PADRAO))


def _float(valor: Decimal | None) -> float | None:
    return None if valor is None else float(valor)


def _situacao(p: sqlite3.Row) -> str:
    if p["status"] == "discontinued":
        return "descontinuado"
    if p["status"] == "coming_soon":
        return "em_breve"
    return "disponivel" if p["stock_quantity"] > 0 else "sem_estoque"


def _preco(con: sqlite3.Connection, p: sqlite3.Row) -> domain.PrecoProduto:
    promos = con.execute(
        "SELECT discount_percent, is_active FROM promotions WHERE product_id = ?", (p["product_id"],)
    ).fetchall()
    ativas = [r["discount_percent"] for r in promos if r["is_active"]]
    return domain.calcular_preco_produto(
        p["price_brl"], max(ativas) if ativas else None, havia_promocao_inativa=bool(promos)
    )


def _preco_dict(preco: domain.PrecoProduto) -> dict:
    return {
        "preco_original": _float(preco.preco_original),
        "em_promocao": preco.em_promocao,
        "desconto_percentual": _float(preco.desconto_percentual),
        "preco_vigente": _float(preco.preco_vigente),
        "desconto_pix_aplicavel": preco.pix_elegivel,
        "preco_pix": _float(preco.preco_pix),
        "promocao_expirada": preco.promocao_expirada,
    }


def _produto_dict(con: sqlite3.Connection, p: sqlite3.Row) -> dict:
    return {
        "produto_id": p["product_id"],
        "nome": p["name"],
        "categoria": p["categoria"],
        "situacao": _situacao(p),
        "descricao": p["description"],
        "specs": json.loads(p["specs"]) if p["specs"] else None,
        **_preco_dict(_preco(con, p)),
    }


def _produtos(con: sqlite3.Connection, where: str = "1", params: tuple = ()) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT p.*, c.name AS categoria FROM products p JOIN categories c USING (category_id) "
        f"WHERE {where} ORDER BY p.price_brl", params,
    ).fetchall()


def _palavras(texto: str) -> set[str]:
    return set(re.findall(r"[\w-]+", _sem_acento(texto)))


def _alternativas(con: sqlite3.Connection, produto: sqlite3.Row) -> list[dict]:
    """Vendáveis da mesma categoria: primeiro as do mesmo tipo, depois as de preço próximo."""
    tipos = _palavras(produto["name"]) & TIPOS_INSTRUMENTO
    candidatos = [c for c in _produtos(con, "p.category_id = ?", (produto["category_id"],))
                  if _situacao(c) == "disponivel" and c["product_id"] != produto["product_id"]]
    candidatos.sort(key=lambda c: (-len(tipos & _palavras(c["name"])),
                                   abs(c["price_brl"] - produto["price_brl"])))
    return [_produto_dict(con, c) for c in candidatos[:MAX_ALTERNATIVAS]]


def buscar_produtos(con, termo=None, categoria=None, preco_max=None, apenas_disponiveis=True) -> dict:
    """Busca no catálogo. preco_max compara com o preço vigente (já com promoção ativa)."""
    resposta: dict = {}
    produtos = _produtos(con)
    if categoria:
        alvo = _sem_acento(categoria.strip())
        nomes = [r["name"] for r in con.execute("SELECT name FROM categories")]
        validas = [n for n in nomes if alvo in _sem_acento(n)]
        if not validas:
            return {"erro": "categoria_desconhecida", "categorias_validas": nomes}
        produtos = [p for p in produtos if p["categoria"] in validas]
        if not produtos:
            resposta["categoria_sem_produtos"] = True

    tokens = _palavras(termo) if termo else set()
    indisponiveis = []
    encontrados = []
    for p in produtos:
        no_nome = tokens <= _palavras(p["name"])
        texto = " ".join(filter(None, (p["name"], p["categoria"], p["description"])))
        if not (no_nome or tokens <= _palavras(texto)):
            continue
        if preco_max is not None and _preco(con, p).preco_vigente > Decimal(str(preco_max)):
            continue
        if _situacao(p) == "disponivel" or not apenas_disponiveis:
            encontrados.append(_produto_dict(con, p))
        elif tokens and no_nome:
            indisponiveis.append({**_produto_dict(con, p), "alternativas": _alternativas(con, p)})

    resposta["produtos"] = encontrados
    if not encontrados and not indisponiveis:
        # Dá ao modelo o que existe de fato, para ele não sugerir itens que a loja não tem.
        resposta["categorias_com_produtos"] = [r[0] for r in con.execute(
            "SELECT DISTINCT c.name FROM sellable_products p JOIN categories c USING (category_id) ORDER BY c.name")]
    if indisponiveis:
        resposta["indisponiveis"] = indisponiveis
    return resposta


def consultar_preco(con, produto_id) -> dict:
    """Preço vigente, PIX e parcelamento de um produto, calculados pelo domínio."""
    linhas = _produtos(con, "p.product_id = ?", (produto_id,))
    if not linhas:
        return {"erro": "produto_nao_encontrado"}
    p = linhas[0]
    preco = _preco(con, p)
    return {
        "produto_id": p["product_id"],
        "nome": p["name"],
        "situacao": _situacao(p),
        **_preco_dict(preco),
        "parcelamento": [{"parcelas": o.parcelas, "valor_parcela": _float(o.valor_parcela)}
                         for o in domain.calcular_opcoes_parcelamento(preco.preco_vigente)],
        "pagamento_combinado_permitido": domain.pagamento_combinado_permitido(preco.preco_vigente),
    }


def simular_parcelas(valor) -> dict:
    """Parcelamento de um valor qualquer, para perguntas sem produto definido."""
    return {"parcelamento": [{"parcelas": o.parcelas, "valor_parcela": _float(o.valor_parcela)}
                             for o in domain.calcular_opcoes_parcelamento(valor)]}


def _contato_confere(pedido: sqlite3.Row, contato: str) -> bool:
    contato = (contato or "").strip()
    if "@" in contato:
        return normalizar_email(contato) == pedido["email_norm"]
    digitos = normalizar_telefone(contato)
    if len(digitos) == 13 and digitos.startswith("55"):
        digitos = digitos[2:]
    return bool(digitos) and digitos == pedido["phone_digits"]


def consultar_pedido(con, pedido_id, email_ou_telefone) -> dict:
    """Só responde se o contato bate com o dono do pedido. O total é o gravado, sem recálculo."""
    pedido = con.execute(
        "SELECT o.*, c.name AS cliente, c.email_norm, c.phone_digits FROM orders o "
        "JOIN customers c USING (customer_id) WHERE o.order_id = ?", (pedido_id,),
    ).fetchone()
    # Mesma resposta para pedido inexistente e contato errado: não revela quais pedidos existem.
    if pedido is None or not _contato_confere(pedido, email_ou_telefone):
        return {"erro": "verificacao_falhou"}
    # E-mail compartilhado (clientes 11 e 43) não identifica o dono: só o telefone serve.
    if "@" in email_ou_telefone and con.execute(
        "SELECT COUNT(*) FROM customers WHERE email_norm = ?", (pedido["email_norm"],)
    ).fetchone()[0] > 1:
        return {"erro": "telefone_necessario"}
    itens = con.execute(
        "SELECT p.name, i.quantity FROM order_items i JOIN products p USING (product_id) "
        "WHERE i.order_id = ?", (pedido_id,),
    ).fetchall()
    return {
        "pedido_id": pedido["order_id"],
        "primeiro_nome": pedido["cliente"].split()[0],
        "status": pedido["status"],
        "data_compra": pedido["order_date"],
        "total_registrado": pedido["total_brl"],
        "forma_pagamento": pedido["payment_method"],
        "codigo_rastreio": pedido["tracking_code"],
        "previsao_entrega": pedido["estimated_delivery"],
        "observacao": pedido["notes"],
        "itens": [{"nome": i["name"], "quantidade": i["quantity"]} for i in itens],
    }


def consultar_politica(secao) -> dict:
    n = resolver_secao(secao)
    if n is None:
        return {"erro": "secao_nao_encontrada", "secoes_validas": list(SECOES_CONSULTAVEIS)}
    return {"secao": n, "texto": _SECOES[n]}


def consultar_frete(con, valor_final_pago, cidade, produto_id=None) -> dict:
    grande_porte = False
    if produto_id is not None:
        linhas = _produtos(con, "p.product_id = ?", (produto_id,))
        if not linhas:
            return {"erro": "produto_nao_encontrado"}
        grande_porte = linhas[0]["categoria"] == CATEGORIA_GRANDE_PORTE
    frete = domain.calcular_frete(valor_final_pago, cidade, grande_porte)
    return {
        "regiao_metropolitana": frete.metropolitana,
        "valor": _float(frete.valor),
        "gratis": frete.gratis,
        "prazo_dias_uteis": frete.prazo_dias_uteis,
        "modalidades": [{"nome": n, "prazo_min": a, "prazo_max": b} for n, a, b in frete.modalidades],
        "cotacao_especial": frete.cotacao_especial,
    }


def avaliar_prazo(tipo, data_compra=None, data_recebimento=None) -> dict:
    """Elegibilidade de devolução, troca ou garantia na data de referência."""
    hoje = data_referencia()
    try:
        compra = date.fromisoformat(data_compra) if data_compra else None
        recebimento = date.fromisoformat(data_recebimento) if data_recebimento else None
        r = domain.avaliar_elegibilidade_prazo(tipo, hoje, compra, recebimento)
    except ValueError as e:
        return {"erro": str(e)}
    return {"elegivel": r.elegivel, "motivo": r.motivo, "dias_decorridos": r.dias_decorridos,
            "prazo_dias": r.prazo_dias, "data_limite": r.data_limite.isoformat() if r.data_limite else None,
            "data_referencia": hoje.isoformat()}


def registrar_atendimento_humano(con, tipo, contato, resumo, pedido_id=None, agora=None) -> dict:
    if tipo not in TIPOS_ATENDIMENTO:
        return {"erro": "tipo_desconhecido", "tipos_validos": list(TIPOS_ATENDIMENTO)}
    agora = agora or datetime.now(FUSO_LOJA)
    cur = con.execute(
        "INSERT INTO atendimentos (criado_em, tipo, contato, resumo, pedido_id) VALUES (?,?,?,?,?)",
        (agora.isoformat(), tipo, contato, resumo, pedido_id),
    )
    con.commit()
    return {"protocolo": cur.lastrowid, "orientacao": TIPOS_ATENDIMENTO[tipo]}


def verificar_expediente(agora=None) -> dict:
    agora = agora or datetime.now(FUSO_LOJA)
    r = domain.avaliar_expediente(agora)
    return {"aberto": r.aberto, "agora": agora.isoformat(timespec="minutes"),
            "proximo_retorno": None if r.aberto else r.proximo_retorno.isoformat(timespec="minutes")}


_string = {"type": "string"}
SCHEMAS = [
    {"name": "buscar_produtos",
     "description": "Busca instrumentos no catálogo por nome, categoria e preço máximo. Item buscado "
                    "pelo nome e indisponível volta em `indisponiveis`, com alternativas.",
     "parameters": {"type": "object", "properties": {
         "termo": {**_string, "description": "Marca ou modelo, ex.: 'Takamine GD20'"},
         "categoria": {**_string, "description": "Guitarras, Baixos, Baterias e Percussão, Teclados e "
                       "Pianos, Violões, Instrumentos de Sopro (Madeiras), Instrumentos de Sopro "
                       "(Metais), Cordas Orquestrais ou Ukuleles"},
         "preco_max": {"type": "number"},
         "apenas_disponiveis": {"type": "boolean"}}}},
    {"name": "consultar_preco",
     "description": "Preço vigente, promoção ativa ou expirada, valor no PIX e parcelas de um produto.",
     "parameters": {"type": "object", "properties": {"produto_id": {"type": "integer"}},
                    "required": ["produto_id"]}},
    {"name": "simular_parcelas",
     "description": "Opções de parcelamento permitidas para um valor em reais, sem produto definido.",
     "parameters": {"type": "object", "properties": {"valor": {"type": "number"}}, "required": ["valor"]}},
    {"name": "consultar_pedido",
     "description": "Status, rastreio e itens de um pedido. Exige número do pedido e e-mail ou "
                    "telefone informados pelo cliente; nunca tente adivinhar. Se o cliente informar "
                    "os dois, envie o telefone. Erro telefone_necessario: peça o telefone da compra.",
     "parameters": {"type": "object", "properties": {
         "pedido_id": {"type": "integer"}, "email_ou_telefone": _string},
         "required": ["pedido_id", "email_ou_telefone"]}},
    {"name": "consultar_politica",
     "description": "Texto integral de uma seção do manual: 3 pagamento, 4 trocas e devoluções, "
                    "5 frete, 6 promoções, 7 atendimento, 8 garantia, 9 privacidade/LGPD.",
     "parameters": {"type": "object", "properties": {"secao": {**_string,
                    "description": "Número ou tema, ex.: '4' ou 'garantia'"}}, "required": ["secao"]}},
    {"name": "consultar_frete",
     "description": "Valor e prazo de frete para uma cidade, sobre o valor final que o cliente paga.",
     "parameters": {"type": "object", "properties": {
         "valor_final_pago": {"type": "number"}, "cidade": _string, "produto_id": {"type": "integer"}},
         "required": ["valor_final_pago", "cidade"]}},
    {"name": "avaliar_prazo",
     "description": "Verifica se o cliente está no prazo. Datas em AAAA-MM-DD. Se faltar a data de "
                    "recebimento, pergunte ao cliente.",
     "parameters": {"type": "object", "properties": {
         "tipo": {"type": "string", "enum": ["arrependimento", "preferencia", "defeito", "garantia_legal"]},
         "data_compra": _string, "data_recebimento": _string}, "required": ["tipo"]}},
    {"name": "registrar_atendimento_humano",
     "description": "Abre protocolo para a equipe humana: devolução, troca, reclamação, exclusão de "
                    "dados ou caso sem resposta no manual.",
     "parameters": {"type": "object", "properties": {
         "tipo": {"type": "string", "enum": list(TIPOS_ATENDIMENTO)},
         "contato": _string, "resumo": _string, "pedido_id": {"type": "integer"}},
         "required": ["tipo", "contato", "resumo"]}},
    {"name": "verificar_expediente",
     "description": "Diz se a loja está em horário de atendimento e quando retorna.",
     "parameters": {"type": "object", "properties": {}}},
]
_COM_CONEXAO = {"buscar_produtos": buscar_produtos, "consultar_preco": consultar_preco,
                "consultar_pedido": consultar_pedido, "consultar_frete": consultar_frete,
                "registrar_atendimento_humano": registrar_atendimento_humano}
_SEM_CONEXAO = {"consultar_politica": consultar_politica, "simular_parcelas": simular_parcelas, "avaliar_prazo": avaliar_prazo,
                "verificar_expediente": verificar_expediente}


def executar(con, nome: str, argumentos: dict) -> str:
    """Executa a tool pedida pelo modelo; erro volta como dado para o modelo se corrigir."""
    permitidos = {s["name"]: set(s["parameters"]["properties"]) for s in SCHEMAS}
    if nome not in permitidos:
        return json.dumps({"erro": f"tool desconhecida: {nome}"})
    args = {k: v for k, v in argumentos.items() if k in permitidos[nome]}
    try:
        resultado = _COM_CONEXAO[nome](con, **args) if nome in _COM_CONEXAO else _SEM_CONEXAO[nome](**args)
    except (TypeError, ValueError) as e:
        resultado = {"erro": str(e)}
    return json.dumps(resultado, ensure_ascii=False)
