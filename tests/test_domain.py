from datetime import date
from decimal import Decimal as D

import pytest

from emporio.domain import (
    avaliar_elegibilidade_prazo,
    calcular_frete,
    calcular_opcoes_parcelamento,
    calcular_preco_produto,
    pagamento_combinado_permitido,
)


def test_takamine_promocao_expirada_usa_preco_cheio_e_pix():
    p = calcular_preco_produto(2199, None, havia_promocao_inativa=True)
    assert p.preco_vigente == D("2199.00")
    assert p.preco_pix == D("2089.05")
    assert p.promocao_expirada and not p.em_promocao


def test_promocao_ativa_nao_acumula_com_pix():
    p = calcular_preco_produto(549, 20)
    assert p.preco_vigente == D("439.20")
    assert not p.pix_elegivel and p.preco_pix is None


def test_pix_fg800():
    assert calcular_preco_produto(1299).preco_pix == D("1234.05")


def test_parcelas_takamine_ate_12x():
    ops = calcular_opcoes_parcelamento(2199)
    assert ops[-1].parcelas == 12 and ops[-1].valor_parcela == D("183.25")


@pytest.mark.parametrize(
    "valor,max_parcelas",
    [(349.92, 4), (429.9, 5), (459.84, 5), (80, 1), (150, 3), (1200, 12), (1199, 11)],
)
def test_maximo_de_parcelas(valor, max_parcelas):
    assert calcular_opcoes_parcelamento(valor)[-1].parcelas == max_parcelas


def test_pedidos_historicos_violam_regra():
    # pedido 9: 6x de R$ 58,32 (total 349,92) não é permitido em 6x
    assert all(o.parcelas < 6 for o in calcular_opcoes_parcelamento(349.92))


def test_pagamento_combinado():
    assert pagamento_combinado_permitido(2000.01)
    assert not pagamento_combinado_permitido(2000)


@pytest.mark.parametrize("valor,gratis", [(499.99, False), (500, True), (520, True)])
def test_frete_campo_grande(valor, gratis):
    f = calcular_frete(valor, "Campo Grande")
    assert f.gratis is gratis
    assert f.valor == (D("0.00") if gratis else D("35.00"))
    assert f.prazo_dias_uteis == (1, 3)


def test_frete_usa_valor_final_pago_com_pix():
    # R$ 520 no PIX = R$ 494 -> abaixo do mínimo
    assert not calcular_frete(calcular_preco_produto(520).preco_pix, "Campo Grande").gratis


def test_frete_outras_cidades_sem_valor():
    f = calcular_frete(3000, "Dourados", grande_porte=True)
    assert f.valor is None and f.cotacao_especial
    assert {m[0] for m in f.modalidades} == {"PAC", "SEDEX", "Jadlog"}


def test_arrependimento_conta_do_recebimento():
    hoje = date(2026, 3, 25)
    assert avaliar_elegibilidade_prazo("arrependimento", hoje, data_recebimento=date(2026, 3, 18)).elegivel
    assert not avaliar_elegibilidade_prazo("arrependimento", hoje, data_recebimento=date(2026, 3, 17)).elegivel


def test_data_limite_conta_do_marco():
    r = avaliar_elegibilidade_prazo("arrependimento", date(2026, 3, 25), data_recebimento=date(2026, 3, 20))
    assert r.data_limite == date(2026, 3, 27)


def test_sem_data_de_recebimento_pergunta():
    r = avaliar_elegibilidade_prazo("arrependimento", date(2026, 3, 25), data_compra=date(2026, 3, 1))
    assert r.elegivel is None and r.motivo == "aguardando_data_recebimento"


def test_defeito_conta_da_compra():
    hoje = date(2026, 3, 25)
    assert avaliar_elegibilidade_prazo("defeito", hoje, data_compra=date(2026, 2, 23)).elegivel
    r = avaliar_elegibilidade_prazo("defeito", hoje, data_compra=date(2026, 2, 22))
    assert not r.elegivel and r.motivo == "fora_do_prazo_acionar_fabricante"
