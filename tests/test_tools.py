import json
from datetime import datetime

import pytest

from emporio import tools
from emporio.ingest import ingerir


@pytest.fixture
def con(tmp_path):
    path = tmp_path / "t.db"
    ingerir(path)
    c = tools.conectar(path)
    yield c
    c.close()


def _nomes(produtos):
    return [p["nome"] for p in produtos]


def test_violoes_ate_1000_excluem_indisponiveis(con):
    r = tools.buscar_produtos(con, categoria="Violões", preco_max=1000)
    assert len(r["produtos"]) == 12
    assert not any("GF-3D" in n or "SN-7C" in n for n in _nomes(r["produtos"]))


def test_giannini_sem_estoque_sugere_dreadnoughts(con):
    r = tools.buscar_produtos(con, termo="Giannini GF-3D")
    assert r["produtos"] == []
    item = r["indisponiveis"][0]
    assert item["situacao"] == "sem_estoque"
    nomes = _nomes(item["alternativas"])
    assert len(nomes) == 3
    assert any("Woodstock" in n for n in nomes) and any("FG800" in n for n in nomes)


def test_descontinuado_com_estoque_nao_e_vendavel(con):
    item = tools.buscar_produtos(con, termo="Ibanez Bass 2X")["indisponiveis"][0]
    assert item["situacao"] == "descontinuado" and item["alternativas"]


def test_coming_soon_nao_e_vendavel(con):
    item = tools.buscar_produtos(con, termo="KA-ABP-CTG")["indisponiveis"][0]
    assert item["situacao"] == "em_breve"


@pytest.mark.parametrize("categoria", ["Cordas Orquestrais", "Sopro"])
def test_categoria_vazia_tem_flag(con, categoria):
    r = tools.buscar_produtos(con, categoria=categoria)
    assert r["categoria_sem_produtos"] and r["produtos"] == []


def test_busca_vazia_indica_categorias_com_produtos(con):
    r = tools.buscar_produtos(con, categoria="Sopro")
    assert "Violões" in r["categorias_com_produtos"]
    assert not any("Sopro" in c for c in r["categorias_com_produtos"])
    assert "categorias_com_produtos" not in tools.buscar_produtos(con, termo="Giannini GF-3D")


def test_categoria_desconhecida(con):
    assert tools.buscar_produtos(con, categoria="Amplificadores")["erro"] == "categoria_desconhecida"


def test_violao_7_cordas_e_produto(con):
    assert tools.buscar_produtos(con, termo="7 cordas")["produtos"]


def test_descricao_descartada_nao_vaza_marca(con):
    p = tools.buscar_produtos(con, termo="Music Man Bass 1X")["produtos"][0]
    assert p["descricao"] is None
    assert tools.buscar_produtos(con, termo="Korg Synth 1")["produtos"][0]["descricao"] is None


def test_takamine_promocao_expirada(con):
    r = tools.consultar_preco(con, 95)
    assert r["promocao_expirada"] and not r["em_promocao"]
    assert r["preco_vigente"] == 2199 and r["preco_pix"] == 2089.05
    assert r["parcelamento"][-1] == {"parcelas": 12, "valor_parcela": 183.25}


def test_ohana_promocao_ativa_sem_pix(con):
    r = tools.consultar_preco(con, 121)
    assert r["preco_original"] == 549 and r["desconto_percentual"] == 20
    assert r["preco_vigente"] == 439.2 and r["preco_pix"] is None and not r["desconto_pix_aplicavel"]


def test_produto_inexistente(con):
    assert tools.consultar_preco(con, 9999)["erro"] == "produto_nao_encontrado"


@pytest.mark.parametrize("contato", ["anacarol.ferreira@coldmail.com", "ANACAROL.FERREIRA@coldmail.com ",
                                     "(67) 99654-7821", "5567996547821"])
def test_pedido_com_contato_correto(con, contato):
    r = tools.consultar_pedido(con, 8, contato)
    assert r["status"] == "shipped" and r["codigo_rastreio"] == "BRJL5544332BR"


@pytest.mark.parametrize("pedido,contato", [(8, "outra@pessoa.com"), (8, ""), (8, "abc"), (9999, "a@b.com")])
def test_pedido_sem_verificacao_nao_vaza_nada(con, pedido, contato):
    assert tools.consultar_pedido(con, pedido, contato) == {"erro": "verificacao_falhou"}


def test_email_duplicado_nao_abre_pedido_alheio(con):
    # Bruno 43 tem o mesmo e-mail do 11, dono do pedido 10; só o telefone distingue os dois.
    assert tools.consultar_pedido(con, 10, "(67) 99456-3456") == {"erro": "verificacao_falhou"}
    assert tools.consultar_pedido(con, 10, "(67) 98543-2109")["pedido_id"] == 10


def test_email_compartilhado_sozinho_nao_abre_pedido(con):
    assert tools.consultar_pedido(con, 10, "bruno.martins@jmail.com") == {"erro": "telefone_necessario"}


def test_simular_parcelas():
    assert tools.simular_parcelas(429.9)["parcelamento"][-1] == {"parcelas": 5, "valor_parcela": 85.98}


def test_total_divergente_e_o_gravado(con):
    dono = con.execute("SELECT email FROM customers WHERE customer_id = 12").fetchone()[0]
    assert tools.consultar_pedido(con, 3, dono)["total_registrado"] == 3450


@pytest.mark.parametrize("secao,numero,trecho", [
    ("3", 3, "Parcelamento de 4x a 6x"),
    ("4.1", 4, "Direito de Arrependimento"),
    ("devolução", 4, "Boquilhas"),
    ("frete", 5, "Jadlog"),
    ("garantia", 8, "6\nmeses"),
    ("LGPD", 9, "exclusão de seus dados"),
])
def test_politica_devolve_secao_inteira(secao, numero, trecho):
    r = tools.consultar_politica(secao)
    assert r["secao"] == numero
    assert "Página" not in r["texto"] and "​" not in r["texto"]
    assert trecho.split("\n")[0] in r["texto"]


@pytest.mark.parametrize("secao", ["1", "10", "receita de bolo"])
def test_politica_fora_das_secoes(secao):
    assert tools.consultar_politica(secao)["erro"] == "secao_nao_encontrada"


def test_frete_bateria_tem_cotacao_especial(con):
    assert tools.consultar_frete(con, 4439, "Dourados", produto_id=141)["cotacao_especial"]


def test_prazo_usa_data_de_referencia(monkeypatch):
    monkeypatch.setenv("REFERENCE_DATE", "2026-03-25")
    assert tools.avaliar_prazo("arrependimento", data_recebimento="2026-03-20")["elegivel"] is True
    assert tools.avaliar_prazo("arrependimento")["motivo"] == "aguardando_data_recebimento"
    assert "erro" in tools.avaliar_prazo("arrependimento", data_recebimento="ontem")


def test_registro_de_atendimento_gera_protocolo(con):
    r = tools.registrar_atendimento_humano(con, "reclamacao", "a@b.com", "Chegou riscado")
    assert r["protocolo"] == 1 and "24 horas úteis" in r["orientacao"]
    assert tools.registrar_atendimento_humano(con, "xyz", "a", "b")["erro"] == "tipo_desconhecido"


@pytest.mark.parametrize("agora,aberto,retorno", [
    (datetime(2026, 3, 25, 10, 0), True, None),            # quarta
    (datetime(2026, 3, 25, 18, 0), False, "2026-03-26T09:00"),
    (datetime(2026, 3, 25, 8, 30), False, "2026-03-25T09:00"),
    (datetime(2026, 3, 28, 12, 59), True, None),           # sábado
    (datetime(2026, 3, 28, 13, 0), False, "2026-03-30T09:00"),
    (datetime(2026, 3, 29, 10, 0), False, "2026-03-30T09:00"),  # domingo
])
def test_expediente(agora, aberto, retorno):
    r = tools.verificar_expediente(agora)
    assert r["aberto"] is aberto and r["proximo_retorno"] == retorno


def test_executar_ignora_argumento_extra_e_nao_quebra(con):
    r = json.loads(tools.executar(con, "consultar_preco", {"produto_id": 95, "desconto": 50}))
    assert r["preco_vigente"] == 2199
    assert "erro" in json.loads(tools.executar(con, "consultar_preco", {}))
    assert "erro" in json.loads(tools.executar(con, "drop_table", {}))


def test_schemas_cobrem_todas_as_tools():
    assert {s["name"] for s in tools.SCHEMAS} == set(tools._COM_CONEXAO) | set(tools._SEM_CONEXAO)
