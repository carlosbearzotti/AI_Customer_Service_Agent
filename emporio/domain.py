"""Regras de negócio puras da Empório da Música (sem LLM e sem banco).

Fonte das regras: data/políticas_da_loja.pdf (seções 3, 4, 5, 6 e 8).
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
DESCONTO_PIX = Decimal("5")
FRETE_GRATIS_MINIMO = Decimal("500")
FRETE_TAXA_FIXA = Decimal("35")
CIDADES_METROPOLITANAS = {"campo grande"}
LIMITE_PAGAMENTO_COMBINADO = Decimal("2000")
MAX_PARCELAS = 12
PRAZO_ARREPENDIMENTO_DIAS = 7
PRAZO_PREFERENCIA_DIAS = 7
PRAZO_DEFEITO_DIAS = 30
PRAZO_GARANTIA_LEGAL_DIAS = 90


def _dinheiro(valor) -> Decimal:
    return Decimal(str(valor)).quantize(CENT, rounding=ROUND_HALF_UP)


def _aplicar_desconto(preco: Decimal, percentual: Decimal) -> Decimal:
    return _dinheiro(preco * (Decimal(100) - Decimal(str(percentual))) / Decimal(100))


@dataclass(frozen=True)
class PrecoProduto:
    preco_original: Decimal
    em_promocao: bool
    desconto_percentual: Decimal | None
    preco_vigente: Decimal
    pix_elegivel: bool
    preco_pix: Decimal | None
    promocao_expirada: bool


def calcular_preco_produto(
    preco: float | Decimal,
    desconto_promocao_ativa: float | Decimal | None = None,
    havia_promocao_inativa: bool = False,
) -> PrecoProduto:
    """Preço vigente de um produto (manual 3 e 6.2).

    Promoção vigente é a com `is_active = 1`. Promoção não é cumulativa com o
    PIX: com promoção ativa não há desconto de 5%.
    """
    original = _dinheiro(preco)
    if desconto_promocao_ativa:
        pct = Decimal(str(desconto_promocao_ativa))
        return PrecoProduto(original, True, pct, _aplicar_desconto(original, pct), False, None, False)
    return PrecoProduto(
        preco_original=original,
        em_promocao=False,
        desconto_percentual=None,
        preco_vigente=original,
        pix_elegivel=True,
        preco_pix=_aplicar_desconto(original, DESCONTO_PIX),
        promocao_expirada=havia_promocao_inativa,
    )


def parcela_minima(n_parcelas: int) -> Decimal:
    """Parcela mínima por faixa (manual 3.1). Até 3x só vale o piso de R$ 50."""
    if n_parcelas <= 3:
        return Decimal("50")
    if n_parcelas <= 6:
        return Decimal("80")
    return Decimal("100")


@dataclass(frozen=True)
class OpcaoParcelamento:
    parcelas: int
    valor_parcela: Decimal


def calcular_opcoes_parcelamento(valor: float | Decimal) -> list[OpcaoParcelamento]:
    """Opções de 1x a 12x sem juros que respeitam a parcela mínima da faixa."""
    total = _dinheiro(valor)
    opcoes = []
    for n in range(1, MAX_PARCELAS + 1):
        parcela = _dinheiro(total / n)
        if n == 1 or parcela >= parcela_minima(n):
            opcoes.append(OpcaoParcelamento(n, parcela))
    return opcoes


def pagamento_combinado_permitido(valor: float | Decimal) -> bool:
    """Combinar formas de pagamento só vale acima de R$ 2.000 (manual 3.1)."""
    return _dinheiro(valor) > LIMITE_PAGAMENTO_COMBINADO


@dataclass(frozen=True)
class Frete:
    metropolitana: bool
    valor: Decimal | None
    gratis: bool
    prazo_dias_uteis: tuple[int, int] | None
    modalidades: tuple[tuple[str, int, int], ...] = ()
    cotacao_especial: bool = False


MODALIDADES_OUTRAS_CIDADES = (("PAC", 5, 12), ("SEDEX", 2, 5), ("Jadlog", 3, 8))


def calcular_frete(
    valor_final_pago: float | Decimal, cidade: str, grande_porte: bool = False
) -> Frete:
    """Frete (manual 5). Base = valor final pago; R$ 500 exato é grátis (suposição)."""
    if cidade.strip().lower() in CIDADES_METROPOLITANAS:
        gratis = _dinheiro(valor_final_pago) >= FRETE_GRATIS_MINIMO
        return Frete(True, Decimal("0.00") if gratis else FRETE_TAXA_FIXA.quantize(CENT), gratis, (1, 3))
    return Frete(False, None, False, None, MODALIDADES_OUTRAS_CIDADES, grande_porte)


@dataclass(frozen=True)
class Elegibilidade:
    elegivel: bool | None
    motivo: str
    dias_decorridos: int | None = None
    prazo_dias: int | None = None


def avaliar_elegibilidade_prazo(
    tipo: str,
    hoje: date,
    data_compra: date | None = None,
    data_recebimento: date | None = None,
) -> Elegibilidade:
    """Prazo de devolução/troca/garantia (manual 4 e 8).

    tipo: arrependimento | preferencia | defeito | garantia_legal.
    Os prazos de arrependimento, preferência e garantia legal contam do
    recebimento; o de defeito, da compra. `elegivel=None` = falta uma data.
    """
    regras = {
        "arrependimento": (PRAZO_ARREPENDIMENTO_DIAS, "recebimento"),
        "preferencia": (PRAZO_PREFERENCIA_DIAS, "recebimento"),
        "defeito": (PRAZO_DEFEITO_DIAS, "compra"),
        "garantia_legal": (PRAZO_GARANTIA_LEGAL_DIAS, "recebimento"),
    }
    if tipo not in regras:
        raise ValueError(f"tipo desconhecido: {tipo}")
    prazo, marco = regras[tipo]
    base = data_compra if marco == "compra" else data_recebimento
    if base is None:
        return Elegibilidade(None, f"aguardando_data_{marco}", prazo_dias=prazo)
    dias = (hoje - base).days
    if dias < 0:
        return Elegibilidade(None, "data_futura", dias, prazo)
    if dias <= prazo:
        return Elegibilidade(True, "dentro_do_prazo", dias, prazo)
    motivo = "fora_do_prazo_acionar_fabricante" if tipo == "defeito" else "fora_do_prazo"
    return Elegibilidade(False, motivo, dias, prazo)


@dataclass(frozen=True)
class Expediente:
    aberto: bool
    proximo_retorno: datetime


def _janela(dia: date) -> tuple[time, time] | None:
    """Horário de atendimento do dia (manual 2). Feriados não são conhecidos pelo sistema."""
    if dia.weekday() < 5:
        return time(9), time(18)
    if dia.weekday() == 5:
        return time(9), time(13)
    return None


def avaliar_expediente(agora: datetime) -> Expediente:
    """Diz se a loja está aberta e, se não, quando o atendimento retorna (manual 7.1)."""
    janela = _janela(agora.date())
    if janela and janela[0] <= agora.time() < janela[1]:
        return Expediente(True, agora)
    if janela and agora.time() < janela[0]:
        return Expediente(False, datetime.combine(agora.date(), janela[0], agora.tzinfo))
    dia = agora.date() + timedelta(days=1)
    while _janela(dia) is None:
        dia += timedelta(days=1)
    return Expediente(False, datetime.combine(dia, _janela(dia)[0], agora.tzinfo))
