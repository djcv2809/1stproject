"""Gera arquivos SINTÉTICOS (dados fictícios) para testar o fluxo. Não são layouts reais dos bancos."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path


def ofx(path: Path, banco: str, conta: str, movs):
    corpo = "".join(
        f"<STMTTRN>\n<TRNTYPE>{'CREDIT' if v > 0 else 'DEBIT'}\n<DTPOSTED>{d:%Y%m%d}\n<TRNAMT>{v}\n"
        f"<FITID>{banco}{i:04d}\n<MEMO>{m}\n</STMTTRN>\n"
        for i, (d, v, m) in enumerate(movs)
    )
    path.write_text(
        f"OFXHEADER:100\nDATA:OFXSGML\nVERSION:102\n\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS>"
        f"<BANKACCTFROM><BANKID>{banco}<ACCTID>{conta}</BANKACCTFROM><BANKTRANLIST>\n{corpo}"
        f"</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>\n",
        "latin-1",
    )


def _set(lin: list[str], ini: int, fim: int, v: str, num=False):
    v = v.rjust(fim - ini + 1, "0") if num else v.ljust(fim - ini + 1)
    lin[ini - 1:fim] = list(v[: fim - ini + 1])


def cnab_par(seq: int, mov: str, nosso: str, doc: str, venc: date, valor: Decimal, sacado: str,
             pago=Decimal(0), ocorr: date | None = None, cred: date | None = None):
    t, u = [" "] * 240, [" "] * 240
    for lin, seg in ((t, "T"), (u, "U")):
        _set(lin, 1, 3, "033"); _set(lin, 4, 7, "0001", True); _set(lin, 8, 8, "3")
        _set(lin, 9, 13, str(seq * 2 - (1 if seg == "T" else 0)), True); _set(lin, 14, 14, seg)
        _set(lin, 16, 17, mov)
    _set(t, 38, 57, nosso); _set(t, 59, 73, doc); _set(t, 74, 81, f"{venc:%d%m%Y}")
    _set(t, 82, 96, str(int(valor * 100)), True); _set(t, 149, 188, sacado)
    _set(u, 78, 92, str(int(pago * 100)), True)
    _set(u, 138, 145, f"{ocorr:%d%m%Y}" if ocorr else "00000000")
    _set(u, 146, 153, f"{cred:%d%m%Y}" if cred else "00000000")
    return "".join(t) + "\n" + "".join(u) + "\n"


def main(destino: str, ref: date):
    d = Path(destino)
    for sub in ("bb", "itau", "santander", "santander_cobranca", "rede"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    dia = lambda n: ref - timedelta(days=n)
    ofx(d / "bb/extrato.ofx", "001", "12345-6", [
        (dia(10), Decimal("-3500.00"), "PAGTO FORNECEDOR CREMER"),
        (dia(7), Decimal("-1200.50"), "TARIFA PACOTE SERVICOS"),
        (dia(5), Decimal("8000.00"), "TED RECEBIDA CLIENTE X"),
    ])
    ofx(d / "itau/extrato.ofx", "341", "9876-5", [
        (dia(9), Decimal("-2200.00"), "PAGTO BOLETO BIOLINE"),
        (dia(4), Decimal("15000.00"), "PIX RECEBIDO HOSPITAL Y"),
    ])
    ofx(d / "santander/extrato.ofx", "033", "13000123-4", [
        (dia(6), Decimal("4850.00"), "CREDITO COBRANCA"),
        (dia(3), Decimal("1941.20"), "CREDITO REDE ELO/VISA"),
        (dia(2), Decimal("-980.00"), "DEBITO CONSORCIO"),
    ])
    # cobrança: A liquidado, B registrado vencido, C registrado a vencer, D baixado
    r = "".join([
        cnab_par(1, "02", "0000000001", "NF1001", dia(20), Decimal("4850.00"), "HOSPITAL ALFA LTDA", ocorr=dia(30)),
        cnab_par(2, "06", "0000000001", "NF1001", dia(20), Decimal("4850.00"), "HOSPITAL ALFA LTDA",
                 pago=Decimal("4850.00"), ocorr=dia(6), cred=dia(6)),
        cnab_par(3, "02", "0000000002", "NF1002", dia(15), Decimal("3200.00"), "CLINICA BETA SA", ocorr=dia(30)),
        cnab_par(4, "02", "0000000003", "NF1003", ref + timedelta(days=12), Decimal("7100.00"), "HOSPITAL GAMA", ocorr=dia(5)),
        cnab_par(5, "02", "0000000004", "NF1004", dia(40), Decimal("900.00"), "CLINICA DELTA", ocorr=dia(60)),
        cnab_par(6, "09", "0000000004", "NF1004", dia(40), Decimal("900.00"), "CLINICA DELTA", ocorr=dia(35)),
    ])
    (d / "santander_cobranca/retorno.ret").write_text(r, "latin-1")
    # Rede: dois dias de pagamento; o 1º bate com o banco (1941,20), o 2º diverge
    (d / "rede/pagamentos.csv").write_text(
        "Data de pagamento;Bandeira;Parcela;Valor bruto;Valor líquido;NSU\n"
        f"{dia(3):%d/%m/%Y};Visa;1/1;1.000,00;970,00;111\n"
        f"{dia(3):%d/%m/%Y};Elo;1/1;1.000,00;971,20;112\n"
        f"{dia(1):%d/%m/%Y};Master;1/1;500,00;485,00;113\n", "utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "entrada_demo", date(2026, 11, 5))
