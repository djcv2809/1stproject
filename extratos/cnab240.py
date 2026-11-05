"""Retorno de cobrança CNAB 240 (segmentos T/U, padrão FEBRABAN).

ATENÇÃO: posições baseadas no padrão FEBRABAN. O layout do Santander pode
divergir em detalhes; validar com um arquivo real antes de confiar nos números.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from .model import Titulo

LIQUIDACAO = {"06", "17"}
BAIXA = {"09", "10"}
REGISTRO = {"02"}
REJEICAO = {"03"}


def _dec(s: str) -> Decimal:
    s = s.strip()
    return Decimal(s or "0") / 100


def _data(s: str) -> date | None:
    s = s.strip()
    if len(s) != 8 or not s.isdigit() or s == "00000000":
        return None
    return date(int(s[4:]), int(s[2:4]), int(s[:2]))


def parse_retorno(path: Path) -> list[Titulo]:
    linhas = [l.rstrip("\r\n").ljust(240) for l in path.read_text("latin-1").splitlines() if l.strip()]
    titulos: dict[str, Titulo] = {}
    eventos = []  # (data_ocorrencia, ordem, mov, T-dict, U-dict)
    ultimo_t = None
    for ordem, l in enumerate(linhas):
        if l[7] != "3":
            continue
        seg = l[13]
        if seg == "T":
            ultimo_t = {
                "mov": l[15:17],
                "nosso": l[37:57].strip(),
                "doc": l[58:73].strip(),
                "venc": _data(l[73:81]),
                "valor": _dec(l[81:96]),
                "sacado": l[148:188].strip(),
            }
        elif seg == "U" and ultimo_t:
            u = {
                "pago": _dec(l[77:92]),
                "ocorr": _data(l[137:145]),
                "cred": _data(l[145:153]),
            }
            eventos.append((u["ocorr"] or date.min, ordem, ultimo_t, u))
            ultimo_t = None
    for _, _, t, u in sorted(eventos, key=lambda e: (e[0], e[1])):
        tit = titulos.setdefault(
            t["nosso"],
            Titulo(t["nosso"], t["doc"], t["sacado"], t["venc"], t["valor"], arquivo=path.name),
        )
        if t["mov"] in LIQUIDACAO:
            tit.status, tit.valor_pago, tit.data_credito = "liquidado", u["pago"], u["cred"]
        elif t["mov"] in BAIXA and tit.status == "aberto":
            tit.status = "baixado"
        elif t["mov"] in REJEICAO and tit.status == "aberto":
            tit.status = "rejeitado"
    return list(titulos.values())
