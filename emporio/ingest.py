"""Carrega os CSVs em SQLite, com a normalização necessária para o agente."""
import csv
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "emporio.db"
PREFIXO = "desafio_tecnico_ai_eng - "

MARCAS = [
    "Yamaha", "Fender", "Gibson", "Ibanez", "PRS", "Music Man", "Pearl", "Tama",
    "Korg", "Roland", "Nord", "Takamine", "Tagima", "Giannini", "Shelby",
    "Kala", "Kalani", "Crafter", "Ohana", "Epiphone", "Squier", "Cort", "Martin", "Taylor", "Casio",
]

# Modelos que identificam a marca mesmo sem citá-la (ex.: "Contrabaixo Precision").
ALIAS_MARCAS = {"Precision": "Fender", "Jazz Bass": "Fender", "StingRay": "Music Man"}

SCHEMA = """
CREATE TABLE categories (category_id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT);
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY, name TEXT NOT NULL, category_id INTEGER REFERENCES categories,
    price_brl REAL NOT NULL, stock_quantity INTEGER NOT NULL, status TEXT NOT NULL,
    description TEXT, description_discarded INTEGER NOT NULL DEFAULT 0,
    specs TEXT, created_at TEXT);
CREATE TABLE promotions (
    promotion_id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products,
    discount_percent REAL NOT NULL, description TEXT, is_active INTEGER NOT NULL);
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT, phone_digits TEXT,
    email TEXT, email_norm TEXT, city TEXT);
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers, order_date TEXT,
    status TEXT, total_brl REAL, payment_method TEXT, tracking_code TEXT,
    estimated_delivery TEXT, notes TEXT);
CREATE TABLE order_items (
    order_id INTEGER REFERENCES orders, product_id INTEGER REFERENCES products, quantity INTEGER);
CREATE TABLE atendimentos (
    protocolo INTEGER PRIMARY KEY AUTOINCREMENT, criado_em TEXT NOT NULL, tipo TEXT NOT NULL,
    contato TEXT NOT NULL, resumo TEXT NOT NULL, pedido_id INTEGER);
CREATE VIEW sellable_products AS
    SELECT * FROM products WHERE status = 'active' AND stock_quantity > 0;
"""


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def normalizar_email(email: str) -> str:
    return _sem_acento(email.strip())


def normalizar_telefone(telefone: str) -> str:
    return re.sub(r"\D", "", telefone)


def marcas_em(texto: str) -> set[str]:
    achadas = {m for m in MARCAS if re.search(rf"\b{re.escape(m)}\b", texto, re.IGNORECASE)}
    achadas |= {b for a, b in ALIAS_MARCAS.items() if re.search(rf"\b{a}\b", texto, re.IGNORECASE)}
    return achadas


def descricao_diverge(nome: str, descricao: str) -> bool:
    """True se a descrição cita marca que não aparece no nome (nome é a fonte de verdade)."""
    citadas = marcas_em(descricao)
    return bool(citadas) and not citadas <= marcas_em(nome)


def _ler(nome: str) -> list[dict]:
    with open(DATA_DIR / f"{PREFIXO}{nome}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _nulo(valor: str):
    valor = valor.strip()
    return valor or None


def ingerir(db_path: Path = DB_PATH) -> dict:
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    descartadas = []

    for r in _ler("categories"):
        con.execute("INSERT INTO categories VALUES (?,?,?)",
                    (r["category_id"], r["name"].strip(), _nulo(r["description"])))
    for r in _ler("products"):
        desc = _nulo(r["description"])
        descartar = bool(desc) and descricao_diverge(r["name"], desc)
        if descartar:
            descartadas.append(int(r["product_id"]))
        con.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?)", (
            r["product_id"], r["name"].strip(), r["category_id"], r["price_brl"],
            r["stock_quantity"], r["status"].strip().lower(), None if descartar else desc,
            int(descartar), _nulo(r["specs"]), _nulo(r["created_at"])))
    for r in _ler("promotions"):
        con.execute("INSERT INTO promotions VALUES (?,?,?,?,?)", (
            r["promotion_id"], r["product_id"], r["discount_percent"],
            _nulo(r["description"]), r["is_active"]))
    for r in _ler("customers"):
        con.execute("INSERT INTO customers VALUES (?,?,?,?,?,?,?)", (
            r["customer_id"], r["name"].strip(), r["phone"], normalizar_telefone(r["phone"]),
            r["email"].strip(), normalizar_email(r["email"]), r["city"].strip()))
    for r in _ler("orders"):
        con.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)", (
            r["order_id"], r["customer_id"], r["order_date"], r["status"].strip().lower(),
            r["total_brl"], r["payment_method"].strip().lower(), _nulo(r["tracking_code"]),
            _nulo(r["estimated_delivery"]), _nulo(r["notes"])))
    for r in _ler("order_items"):
        con.execute("INSERT INTO order_items VALUES (?,?,?)",
                    (r["order_id"], r["product_id"], r["quantity"]))
    con.commit()
    contagens = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                 for t in ("categories", "products", "promotions", "customers", "orders", "order_items")}
    con.close()
    return {"contagens": contagens, "descricoes_descartadas": descartadas}


if __name__ == "__main__":
    resultado = ingerir(Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH)
    print(resultado)
