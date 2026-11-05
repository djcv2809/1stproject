"""Relatório CSV da Rede (vendas/pagamentos). Layout detectado por nome de coluna.

ATENÇÃO: o layout real varia conforme o relatório exportado; se uma coluna não
for reconhecida o erro lista os cabeçalhos encontrados, para ajuste do mapa.
"""
from __future__ import annotations

import csv
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from .model import Lancamento

MAPA = {
    "data": ["data de pagamento", "data pagamento", "data do pagamento", "data da venda", "data venda", "data"],
    "liquido": ["valor liquido", "valor líquido", "valor liquido da parcela", "liquido"],
    "bruto": ["valor bruto", "valor da venda", "valor da parcela", "valor"],
    "bandeira": ["bandeira"],
    "parcela": ["parcela", "parcelas"],
    "doc": ["nsu", "numero da autorizacao", "autorizacao", "comprovante de venda"],
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _valor(s: str) -> Decimal:
    s = s.strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return Decimal(s or "0")


def _data(s: str) -> date:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"data não reconhecida: {s!r}")


def _achar(cabecalho: list[str], chave: str) -> int | None:
    normal = [_norm(c) for c in cabecalho]
    for cand in MAPA[chave]:
        if _norm(cand) in normal:
            return normal.index(_norm(cand))
    return None


def parse_rede(path: Path) -> list[Lancamento]:
    texto = path.read_bytes()
    try:
        texto = texto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = texto.decode("cp1252")
    delim = ";" if texto.splitlines()[0].count(";") >= texto.splitlines()[0].count(",") else ","
    linhas = list(csv.reader(texto.splitlines(), delimiter=delim))
    cab, dados = linhas[0], linhas[1:]
    i = {k: _achar(cab, k) for k in MAPA}
    if i["data"] is None or (i["liquido"] is None and i["bruto"] is None):
        raise ValueError(f"{path.name}: colunas não reconhecidas. Cabeçalhos: {cab}")
    col_valor = i["liquido"] if i["liquido"] is not None else i["bruto"]
    saida = []
    for r in dados:
        if not r or not r[i["data"]].strip():
            continue
        get = lambda k: r[i[k]].strip() if i[k] is not None and i[k] < len(r) else ""
        saida.append(
            Lancamento(
                fonte="rede",
                conta="rede",
                data=_data(r[i["data"]]),
                descricao=" ".join(x for x in ("REDE", get("bandeira"), get("parcela")) if x),
                valor=_valor(r[col_valor]),
                documento=get("doc"),
                arquivo=path.name,
            )
        )
    return saida
