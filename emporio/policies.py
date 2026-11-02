"""Seções do manual da loja, recuperadas por número ou tema (sem busca vetorial).

data/politicas.txt é gerado do PDF com:
    pdftotext -layout data/políticas_da_loja.pdf data/politicas.txt
"""
import re
from pathlib import Path

from emporio.ingest import _sem_acento

POLITICAS_PATH = Path(__file__).resolve().parent.parent / "data" / "politicas.txt"
SECOES_CONSULTAVEIS = range(3, 10)
TEMAS = {
    3: ("pagamento", "pix", "parcela", "parcelamento", "cartao", "boleto"),
    4: ("troca", "trocas", "devolucao", "devolucoes", "arrependimento", "reembolso"),
    5: ("frete", "entrega", "entregas", "rastreamento", "rastreio"),
    6: ("promocao", "promocoes", "desconto", "descontos"),
    7: ("atendimento", "whatsapp", "reclamacao"),
    8: ("garantia",),
    9: ("privacidade", "lgpd", "dados"),
}
_RUIDO = re.compile(r"^\s*(Empório da Música Manual de Políticas.*|Página \d+)\s*$", re.MULTILINE)
_TITULO = re.compile(r"^(\d{1,2})\. (\S.*)$", re.MULTILINE)


def carregar_secoes(path: Path = POLITICAS_PATH) -> dict[int, str]:
    texto = path.read_text(encoding="utf-8").replace("​", "").replace("\f", "")
    texto = _RUIDO.sub("", texto)
    titulos = list(_TITULO.finditer(texto))
    secoes = {}
    for atual, proximo in zip(titulos, titulos[1:] + [None]):
        fim = proximo.start() if proximo else len(texto)
        secoes[int(atual.group(1))] = re.sub(r"\n{3,}", "\n\n", texto[atual.start():fim]).strip()
    return secoes


def resolver_secao(secao: str) -> int | None:
    """Aceita "4", "4.1" ou um tema ("devolução"). A seção vem sempre inteira, com exceções."""
    consulta = _sem_acento(str(secao).strip())
    numero = re.match(r"(?:secao\s*)?(\d{1,2})", consulta)
    if numero:
        n = int(numero.group(1))
        return n if n in SECOES_CONSULTAVEIS else None
    palavras = set(re.findall(r"\w+", consulta))
    for n, temas in TEMAS.items():
        if palavras & set(temas):
            return n
    return None
