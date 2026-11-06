"""Servidor HTTP (stdlib) com API JSON e interface web."""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import db

STATIC = os.path.join(os.path.dirname(__file__), "static")
MAX_BODY = 5 * 1024 * 1024
CHILD_RE = "clausulas|pagamentos|compromissos"


class Handler(BaseHTTPRequestHandler):
    conn = None  # definido em make_server

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, payload=None, ctype="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(
            payload, ensure_ascii=False).encode() if payload is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("Corpo grande demais.")
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            raise ValueError("JSON inválido.")

    def _route(self, method):
        path = self.path.split("?")[0]
        if method == "GET" and not path.startswith("/api/"):
            f = os.path.join(STATIC, "index.html")
            with open(f, "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")
        c = self.conn
        m = None
        if (path, method) == ("/api/agenda", "GET"):
            return self._send(200, db.agenda(c))
        if path == "/api/contratos":
            if method == "GET":
                return self._send(200, db.list_contracts(c))
            if method == "POST":
                return self._send(201, {"id": db.create_contract(c, self._body())})
        m = re.fullmatch(r"/api/contratos/(\d+)", path)
        if m:
            cid = int(m[1])
            if method == "GET":
                return self._send(200, db.get_contract(c, cid))
            if method == "PUT":
                db.update(c, "contratos", cid, self._body())
                return self._send(200, db.get_contract(c, cid))
            if method == "DELETE":
                db.delete(c, "contratos", cid)
                return self._send(204)
        m = re.fullmatch(rf"/api/contratos/(\d+)/({CHILD_RE})", path)
        if m and method == "POST":
            rid = db.create_child(c, m[2], int(m[1]), self._body())
            return self._send(201, {"id": rid})
        m = re.fullmatch(rf"/api/({CHILD_RE})/(\d+)", path)
        if m and method == "PUT":
            db.update(c, m[1], int(m[2]), self._body())
            return self._send(200, {"ok": True})
        if m and method == "DELETE":
            db.delete(c, m[1], int(m[2]))
            return self._send(204)
        self._send(404, {"erro": "Rota não encontrada."})

    def _handle(self, method):
        try:
            self._route(method)
        except ValueError as e:
            self._send(400, {"erro": str(e)})
        except LookupError as e:
            self._send(404, {"erro": str(e)})
        except Exception:  # não vaza detalhes internos ao cliente
            self._send(500, {"erro": "Erro interno."})

    def do_GET(self): self._handle("GET")
    def do_POST(self): self._handle("POST")
    def do_PUT(self): self._handle("PUT")
    def do_DELETE(self): self._handle("DELETE")


def make_server(conn, host="127.0.0.1", port=8000):
    handler = type("BoundHandler", (Handler,), {"conn": conn})
    return ThreadingHTTPServer((host, port), handler)
