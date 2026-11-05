from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from .cnab240 import parse_retorno
from .ofx import parse_ofx
from .rede import parse_rede
from .report import dedup, gerar

# pasta de entrada -> (fonte, padrões de arquivo)
OFX = {"bb": "bb", "itau": "itau", "santander": "santander"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="extratos", description=__doc__)
    ap.add_argument("--entrada", default="entrada", help="pasta com subpastas bb/ itau/ santander/ santander_cobranca/ rede/")
    ap.add_argument("--saida", default="saida")
    ap.add_argument("--ref", help="data de referência AAAA-MM-DD (padrão: hoje)")
    a = ap.parse_args(argv)
    ref = datetime.strptime(a.ref, "%Y-%m-%d").date() if a.ref else date.today()
    ent = Path(a.entrada)
    lancs, titulos, erros = [], [], []

    for sub, fonte in OFX.items():
        for f in sorted((ent / sub).glob("*")) if (ent / sub).is_dir() else []:
            if f.suffix.lower() in (".ofx", ".qfx"):
                try:
                    lancs += parse_ofx(f, fonte)
                except Exception as ex:  # noqa: BLE001
                    erros.append(f"{f}: {ex}")
    d = ent / "santander_cobranca"
    for f in sorted(d.glob("*")) if d.is_dir() else []:
        if f.suffix.lower() in (".ret", ".txt", ".rem"):
            try:
                titulos += parse_retorno(f)
            except Exception as ex:  # noqa: BLE001
                erros.append(f"{f}: {ex}")
    d = ent / "rede"
    for f in sorted(d.glob("*.csv")) if d.is_dir() else []:
        try:
            lancs += parse_rede(f)
        except Exception as ex:  # noqa: BLE001
            erros.append(f"{f}: {ex}")

    lancs, dups = dedup(lancs)
    out = gerar(lancs, titulos, ref, Path(a.saida), dups)
    print(f"{len(lancs)} lançamentos, {len(titulos)} títulos, {dups} duplicados descartados -> {out}")
    for e in erros:
        print("ERRO:", e, file=sys.stderr)
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
