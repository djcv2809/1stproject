import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from demo.gerar_demo import main as gerar_demo
from extratos.__main__ import main as cli
from extratos.cnab240 import parse_retorno
from extratos.ofx import parse_ofx
from extratos.rede import parse_rede
from extratos.report import conciliar_rede, dedup

REF = date(2026, 11, 5)


class Fluxo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        gerar_demo(str(self.tmp / "e"), REF)
        self.e = self.tmp / "e"

    def test_ofx(self):
        l = parse_ofx(self.e / "bb/extrato.ofx", "bb")
        self.assertEqual(len(l), 3)
        self.assertEqual(l[0].valor, Decimal("-3500.00"))
        self.assertEqual(l[2].conta, "001/12345-6")

    def test_cobranca_status(self):
        t = {x.documento: x.situacao(REF) for x in parse_retorno(self.e / "santander_cobranca/retorno.ret")}
        self.assertEqual(t, {"NF1001": "liquidado", "NF1002": "vencido", "NF1003": "a vencer", "NF1004": "baixado"})

    def test_rede_e_conciliacao(self):
        rede = parse_rede(self.e / "rede/pagamentos.csv")
        banco = parse_ofx(self.e / "santander/extrato.ofx", "santander")
        self.assertEqual(sum(x.valor for x in rede), Decimal("2426.20"))
        c = conciliar_rede(rede + banco)
        self.assertEqual([x["status"] for x in c], ["OK", "NÃO ENCONTRADO"])

    def test_dedup_idempotente(self):
        l = parse_ofx(self.e / "bb/extrato.ofx", "bb")
        out, dups = dedup(l + l)
        self.assertEqual((len(out), dups), (3, 3))

    def test_cli(self):
        rc = cli(["--entrada", str(self.e), "--saida", str(self.tmp / "s"), "--ref", "2026-11-05"])
        self.assertEqual(rc, 0)
        self.assertTrue((self.tmp / "s/resumo.html").exists())


if __name__ == "__main__":
    unittest.main()
