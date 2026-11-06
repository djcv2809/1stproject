"""Uso:
  python -m gestao_contratos servir [--porta 8000] [--host 127.0.0.1]
  python -m gestao_contratos lembretes [--simular]
  python -m gestao_contratos importar arquivo.json
  python -m gestao_contratos atualizar-obs arquivo.json
"""
import argparse
import json
import sys

from . import config, db, lembretes, server


def main(argv=None):
    p = argparse.ArgumentParser(prog="gestao_contratos")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("servir", help="Inicia a interface web")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--porta", type=int, default=8000)
    l = sub.add_parser("lembretes", help="Envia por e-mail os avisos pendentes")
    l.add_argument("--simular", action="store_true", help="Mostra o e-mail sem enviar nem registrar")
    i = sub.add_parser("importar", help="Importa contrato(s) de um arquivo JSON")
    i.add_argument("arquivo")
    u = sub.add_parser("atualizar-obs", help="Atualiza só as observações dos contratos de um JSON (casa pelo nome)")
    u.add_argument("arquivo")
    a = p.parse_args(argv)
    config.carregar_env()
    conn = db.connect()

    if a.cmd == "servir":
        srv = server.make_server(conn, a.host, a.porta)
        print(f"Gestão de Contratos em http://{a.host}:{a.porta}  (Ctrl+C para sair)")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    elif a.cmd == "lembretes":
        try:
            ev = lembretes.executar(conn, simular=a.simular)
        except Exception as e:
            print(f"Falha ao enviar lembretes: {e}", file=sys.stderr)
            return 1
        print(f"{len(ev)} aviso(s) {'simulado(s)' if a.simular else 'enviado(s)'}.")
    elif a.cmd == "importar":
        with open(a.arquivo, encoding="utf-8") as fh:
            data = json.load(fh)
        for c in data if isinstance(data, list) else [data]:
            print("Contrato criado, id =", db.create_contract(conn, c))
    elif a.cmd == "atualizar-obs":
        with open(a.arquivo, encoding="utf-8") as fh:
            data = json.load(fh)
        for c in data if isinstance(data, list) else [data]:
            if not c.get("observacoes"):
                continue
            rows = conn.execute("SELECT id FROM contratos WHERE nome=?", (c["nome"],)).fetchall()
            if not rows:
                print("Não encontrado no banco:", c["nome"])
            for r in rows:
                db.update(conn, "contratos", r["id"], {"observacoes": c["observacoes"]})
                print("Observações atualizadas:", c["nome"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
