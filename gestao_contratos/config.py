"""Leitura opcional de um arquivo .env (CHAVE=valor), sem sobrescrever o ambiente."""
import os


def carregar_env(path=None):
    path = path or os.environ.get("GC_ENV") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip("\"'"))
    return True
