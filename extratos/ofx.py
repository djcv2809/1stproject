from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from .model import Lancamento


def _ler(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _tag(bloco: str, nome: str) -> str:
    m = re.search(rf"<{nome}>([^<\r\n]*)", bloco, re.I)
    return m.group(1).strip() if m else ""


def parse_ofx(path: Path, fonte: str) -> list[Lancamento]:
    texto = _ler(path)
    conta = f"{_tag(texto, 'BANKID')}/{_tag(texto, 'ACCTID')}".strip("/")
    blocos = re.findall(
        r"<STMTTRN>(.*?)(?=<STMTTRN>|</BANKTRANLIST>|$)", texto, re.I | re.S
    )
    saida = []
    for b in blocos:
        dt = _tag(b, "DTPOSTED")[:8]
        valor = _tag(b, "TRNAMT").replace(",", ".")
        if len(dt) != 8 or not valor:
            continue
        saida.append(
            Lancamento(
                fonte=fonte,
                conta=conta,
                data=date(int(dt[:4]), int(dt[4:6]), int(dt[6:8])),
                descricao=" ".join((_tag(b, "MEMO") or _tag(b, "NAME")).split()),
                valor=Decimal(valor),
                documento=_tag(b, "FITID") or _tag(b, "CHECKNUM"),
                arquivo=path.name,
            )
        )
    return saida
