import sqlite3

import pytest

from emporio.ingest import descricao_diverge, ingerir, normalizar_email, normalizar_telefone


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "t.db"
    resultado = ingerir(path)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    yield con, resultado
    con.close()


def test_contagens(db):
    _, r = db
    assert r["contagens"] == {"categories": 9, "products": 65, "promotions": 25,
                              "customers": 50, "orders": 20, "order_items": 22}


def test_descricoes_trocadas_sao_descartadas(db):
    _, r = db
    assert r["descricoes_descartadas"] == [135, 136, 137, 139, 140, 142, 144]


def test_descricao_correta_e_mantida(db):
    con, _ = db
    row = con.execute("SELECT description FROM products WHERE product_id = 81").fetchone()
    assert row["description"]


def test_descricao_diverge():
    assert descricao_diverge("Music Man Bass 1X", "Contrabaixo Fender Jazz Bass")
    assert not descricao_diverge("Gibson Les Paul Standard", "Guitarra Gibson Les Paul")
    assert not descricao_diverge("Yamaha C40", "Violão clássico com tampo em Spruce")


def test_vendavel_exige_ativo_e_estoque(db):
    con, _ = db
    vendaveis = {r[0] for r in con.execute("SELECT product_id FROM sellable_products")}
    assert 96 not in vendaveis      # ativo sem estoque
    assert 136 not in vendaveis     # descontinuado com estoque
    assert 130 not in vendaveis     # coming_soon
    assert 113 not in vendaveis     # descontinuado


def test_promocoes_vigentes_sao_as_ativas(db):
    con, _ = db
    ativos = {r[0] for r in con.execute("SELECT product_id FROM promotions WHERE is_active = 1")}
    assert ativos == {90, 94, 121, 127}
    assert 95 not in ativos  # Takamine GD20: promoção expirada


def test_email_duplicado_dos_clientes_11_e_43(db):
    con, _ = db
    ids = [r[0] for r in con.execute(
        "SELECT customer_id FROM customers WHERE email_norm = 'bruno.martins@jmail.com'")]
    assert ids == [11, 43]


def test_total_do_pedido_e_mantido_como_gravado(db):
    con, _ = db
    assert con.execute("SELECT total_brl FROM orders WHERE order_id = 3").fetchone()[0] == 3450


def test_normalizacao():
    assert normalizar_email("  José@Jmail.com ") == "jose@jmail.com"
    assert normalizar_telefone("(67) 99812-3456") == "67998123456"
