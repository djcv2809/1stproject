import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date

from gestao_contratos import db, lembretes, server

HOJE = date(2026, 11, 6)
CONTRATO = {
    "nome": "Locação sala", "contraparte": "Imob Ltda", "data_fim": "2027-01-31",
    "renovacao_automatica": True, "aviso_previo_dias": 90,
    "clausulas": [{"titulo": "Reajuste", "texto": "IGP-M anual"}],
    "pagamentos": [
        {"descricao": "Aluguel nov", "vencimento": "2026-11-13", "valor": "3.500,00".replace(".", "")},
        {"descricao": "Aluguel out", "vencimento": "2026-11-01", "valor": 3500},
        {"descricao": "Aluguel dez (pago)", "vencimento": "2026-12-10", "valor": 3500, "status": "pago"},
    ],
    "compromissos": [{"descricao": "Vistoria", "data": "2026-11-06", "responsavel": "Paulo"}],
}


class Core(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")

    def test_validacao(self):
        with self.assertRaises(ValueError):
            db.clean("contratos", {"nome": "x"})  # falta contraparte
        with self.assertRaises(ValueError):
            db.clean("pagamentos", {"descricao": "x", "vencimento": "31/12/2026", "valor": 1})
        with self.assertRaises(ValueError):
            db.clean("pagamentos", {"descricao": "x", "vencimento": "2026-12-31", "valor": "abc"})
        self.assertEqual(db.clean("pagamentos", {"descricao": "x", "vencimento": "2026-12-31",
                                                 "valor": "1500,50"})["valor"], 1500.5)

    def test_importacao_atomica(self):
        ruim = {**CONTRATO, "pagamentos": [{"descricao": "x", "vencimento": "errada", "valor": 1}]}
        with self.assertRaises(ValueError):
            db.create_contract(self.conn, ruim)
        self.assertEqual(db.list_contracts(self.conn), [])

    def test_agenda(self):
        cid = db.create_contract(self.conn, CONTRATO)
        ev = db.agenda(self.conn, HOJE)
        tipos = [(e["tipo"], e["data"]) for e in ev]
        self.assertIn(("pagamento", "2026-11-01"), tipos)            # atrasado
        self.assertNotIn(("pagamento", "2026-12-10"), tipos)         # pago fica fora
        self.assertIn(("aviso_renovacao", "2026-11-02"), tipos)      # 2027-01-31 - 90d
        self.assertEqual(ev[0]["dias"], -5)  # 01/11 vs 06/11
        db.update(self.conn, "contratos", cid, {"status": "encerrado"})
        self.assertEqual(db.agenda(self.conn, HOJE), [])

    def test_pagar_registra_data(self):
        db.create_contract(self.conn, CONTRATO)
        pid = self.conn.execute("SELECT id FROM pagamentos WHERE descricao='Aluguel nov'").fetchone()[0]
        db.update(self.conn, "pagamentos", pid, {"status": "pago"})
        row = self.conn.execute("SELECT * FROM pagamentos WHERE id=?", (pid,)).fetchone()
        self.assertEqual(row["pago_em"], date.today().isoformat())

    def test_lembretes_sem_duplicar(self):
        db.create_contract(self.conn, CONTRATO)
        enviados = []
        ev = lembretes.executar(self.conn, HOJE, enviar=lambda a, c, t: enviados.append((a, c)))
        # hoje: vistoria (0d), pagamento atrasado, aviso de renovação atrasado; nov/13 = 7d
        self.assertEqual(len(ev), 4)
        self.assertEqual(len(enviados), 1)
        self.assertIn("ATRASADO", enviados[0][1])
        self.assertIn("R$ 3.500,00", enviados[0][1])
        self.assertIn("13/11/2026", enviados[0][1])
        self.assertEqual(lembretes.executar(self.conn, HOJE, enviar=lambda a, c, t: enviados.append(1)), [])
        self.assertEqual(len(enviados), 1)

    def test_falha_no_envio_nao_marca_como_enviado(self):
        db.create_contract(self.conn, CONTRATO)

        def falha(a, c, t):
            raise OSError("smtp fora do ar")
        with self.assertRaises(OSError):
            lembretes.executar(self.conn, HOJE, enviar=falha)
        self.assertEqual(len(lembretes.pendentes(self.conn, HOJE)), 4)

    def test_mudar_data_reabre_aviso(self):
        db.create_contract(self.conn, CONTRATO)
        lembretes.executar(self.conn, HOJE, enviar=lambda a, c, t: None)
        mid = self.conn.execute("SELECT id FROM compromissos").fetchone()[0]
        db.update(self.conn, "compromissos", mid, {"data": "2026-11-13"})
        novos = [e for e in lembretes.pendentes(self.conn, HOJE) if e["tipo"] == "compromisso"]
        self.assertEqual(len(novos), 1)  # nova data => nova chave; 7 dias está na lista


    def test_destinatarios_por_contrato(self):
        db.create_contract(self.conn, {**CONTRATO, "nome": "Pessoal", "emails_aviso": "A@x.com; b@y.com a@x.com"})
        db.create_contract(self.conn, {**CONTRATO, "nome": "Empresa"})
        envios = []
        lembretes.executar(self.conn, HOJE, enviar=lambda a, c, t: envios.append((t, c)))
        self.assertEqual(len(envios), 2)
        por_dest = {tuple(t): c for t, c in envios}
        self.assertEqual(set(por_dest), {("a@x.com", "b@y.com"), ()})
        self.assertEqual(por_dest[("a@x.com", "b@y.com")].count("Contrato: Pessoal"), 4)
        self.assertNotIn("Contrato: Empresa", por_dest[("a@x.com", "b@y.com")])

    def test_falha_de_um_grupo_nao_bloqueia_o_outro(self):
        db.create_contract(self.conn, {**CONTRATO, "nome": "Pessoal", "emails_aviso": "a@x.com"})
        db.create_contract(self.conn, {**CONTRATO, "nome": "Empresa"})

        def so_empresa(a, c, t):
            if t:
                raise OSError("falhou")
        with self.assertRaises(OSError):
            lembretes.executar(self.conn, HOJE, enviar=so_empresa)
        restantes = lembretes.pendentes(self.conn, HOJE)
        self.assertEqual({e["contrato"] for e in restantes}, {"Pessoal"})

    def test_emails_validacao(self):
        with self.assertRaises(ValueError):
            db.clean("contratos", {"nome": "x", "contraparte": "y", "emails_aviso": "sem-arroba"})
        ok = db.clean("contratos", {"nome": "x", "contraparte": "y", "emails_aviso": ["A@x.com", "a@x.com"]})
        self.assertEqual(ok["emails_aviso"], "a@x.com")

    def test_migracao_de_banco_antigo(self):
        import os
        import sqlite3
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "velho.db")
        old = sqlite3.connect(path)
        old.executescript(db.SCHEMA.replace(" emails_aviso TEXT,", ""))
        old.execute("INSERT INTO contratos (nome, contraparte) VALUES ('a', 'b')")
        old.commit()
        old.close()
        conn = db.connect(path)
        self.assertEqual(db.list_contracts(conn)[0]["emails_aviso"], None)
        db.update(conn, "contratos", 1, {"emails_aviso": "z@x.com"})
        self.assertEqual(db.get_contract(conn, 1)["emails_aviso"], "z@x.com")


class Http(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.make_server(db.connect(":memory:"), "127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw and "json" in r.headers["Content-Type"] else raw)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_fluxo(self):
        st, out = self.call("POST", "/api/contratos", CONTRATO)
        self.assertEqual(st, 201)
        cid = out["id"]
        st, c = self.call("GET", f"/api/contratos/{cid}")
        self.assertEqual((st, len(c["pagamentos"]), len(c["clausulas"])), (200, 3, 1))
        st, _ = self.call("POST", f"/api/contratos/{cid}/compromissos",
                          {"descricao": "Renovar seguro", "data": "2027-02-01"})
        self.assertEqual(st, 201)
        st, err = self.call("POST", f"/api/contratos/{cid}/pagamentos", {"descricao": "x"})
        self.assertEqual(st, 400)
        self.assertIn("obrigatório", err["erro"])
        self.assertEqual(self.call("POST", "/api/contratos/999/clausulas", {"titulo": "x"})[0], 404)
        self.assertEqual(self.call("GET", "/api/agenda")[0], 200)
        self.assertEqual(self.call("DELETE", f"/api/contratos/{cid}")[0], 204)
        self.assertEqual(self.call("GET", f"/api/contratos/{cid}")[0], 404)

    def test_pagina(self):
        st, body = self.call("GET", "/")
        self.assertEqual(st, 200)
        self.assertIn(b"Gest\xc3\xa3o de Contratos", body)


if __name__ == "__main__":
    unittest.main()
