"""Chat de terminal: python -m emporio.cli [--trace]"""
import argparse
import os
from pathlib import Path

from emporio.agent import Agente, ClienteOpenAICompativel, ErroLLM
from emporio.ingest import DB_PATH, ingerir
from emporio.tools import conectar

COMANDOS_SAIDA = {"sair", "exit", "quit"}


def carregar_env(path: Path = DB_PATH.parent.parent / ".env") -> None:
    """Lê KEY=valor do .env sem sobrescrever o ambiente."""
    if not path.exists():
        return
    for linha in path.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


def preparar_agente(cliente=None, relogio=None) -> Agente:
    carregar_env()
    if not DB_PATH.exists():
        ingerir()
    return Agente(cliente or ClienteOpenAICompativel(), conectar(), relogio)


def conversar(agente: Agente, trace: bool = False, entrada=input, saida=print) -> None:
    saida('Empório da Música: oi! Sou o Carlos. Digite "sair" para encerrar.')
    while True:
        try:
            texto = entrada("você> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if texto.lower() in COMANDOS_SAIDA:
            return
        if not any(c.isalnum() for c in texto):
            continue
        try:
            resposta = agente.responder(texto)
        except ErroLLM as e:
            saida(f"[erro] {e}\nConfira se o modelo está rodando (ver README).")
            continue
        if trace:
            for c in agente.chamadas:
                saida(f"  [tool] {c['tool']}({c['argumentos']}) -> {c['resultado'][:200]}")
        saida(f"carlos> {resposta}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", action="store_true", help="mostra as tools chamadas")
    conversar(preparar_agente(), parser.parse_args().trace)


if __name__ == "__main__":
    main()
