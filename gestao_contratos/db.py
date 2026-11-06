"""Banco de dados (SQLite), validação e cálculo da agenda de compromissos."""
import os
import sqlite3
from datetime import date, timedelta

DB_PATH = os.environ.get(
    "GC_DB", os.path.join(os.path.dirname(__file__), "..", "data", "contratos.db")
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS contratos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL, contraparte TEXT NOT NULL,
  objeto TEXT, escopo TEXT,
  data_inicio TEXT, data_fim TEXT, valor_total REAL,
  renovacao_automatica INTEGER NOT NULL DEFAULT 0,
  aviso_previo_dias INTEGER,
  status TEXT NOT NULL DEFAULT 'ativo',
  observacoes TEXT,
  criado_em TEXT NOT NULL DEFAULT (date('now'))
);
CREATE TABLE IF NOT EXISTS clausulas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contrato_id INTEGER NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
  titulo TEXT NOT NULL, texto TEXT, categoria TEXT
);
CREATE TABLE IF NOT EXISTS pagamentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contrato_id INTEGER NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
  descricao TEXT NOT NULL, vencimento TEXT NOT NULL, valor REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'pendente', pago_em TEXT
);
CREATE TABLE IF NOT EXISTS compromissos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  contrato_id INTEGER NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
  descricao TEXT NOT NULL, data TEXT NOT NULL, responsavel TEXT,
  status TEXT NOT NULL DEFAULT 'pendente'
);
CREATE TABLE IF NOT EXISTS lembretes_enviados (
  chave TEXT PRIMARY KEY, enviado_em TEXT NOT NULL
);
"""

# campo -> (tipo, obrigatório)
SPEC = {
    "contratos": {
        "nome": ("text", True), "contraparte": ("text", True),
        "objeto": ("text", False), "escopo": ("text", False),
        "data_inicio": ("date", False), "data_fim": ("date", False),
        "valor_total": ("num", False),
        "renovacao_automatica": ("bool", False), "aviso_previo_dias": ("int", False),
        "status": ("enum:ativo,encerrado,rescindido", False),
        "observacoes": ("text", False),
    },
    "clausulas": {
        "titulo": ("text", True), "texto": ("text", False), "categoria": ("text", False),
    },
    "pagamentos": {
        "descricao": ("text", True), "vencimento": ("date", True), "valor": ("num", True),
        "status": ("enum:pendente,pago", False), "pago_em": ("date", False),
    },
    "compromissos": {
        "descricao": ("text", True), "data": ("date", True), "responsavel": ("text", False),
        "status": ("enum:pendente,concluido", False),
    },
}
CHILDREN = ("clausulas", "pagamentos", "compromissos")


def connect(path=None):
    path = path or DB_PATH
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def clean(table, data, partial=False):
    """Valida `data` contra SPEC[table]. Levanta ValueError em português."""
    if not isinstance(data, dict):
        raise ValueError("Corpo da requisição inválido.")
    out = {}
    for field, (kind, required) in SPEC[table].items():
        if field not in data or data[field] in (None, ""):
            if required and not partial:
                raise ValueError(f"Campo obrigatório: {field}")
            if field in data and partial and required:
                raise ValueError(f"Campo obrigatório: {field}")
            if field in data:
                out[field] = None
            continue
        v = data[field]
        try:
            if kind == "text":
                v = str(v).strip()
                if required and not v:
                    raise ValueError
            elif kind == "date":
                v = date.fromisoformat(str(v)).isoformat()
            elif kind == "num":
                if isinstance(v, str):
                    v = v.replace(",", ".")
                v = float(v)
                if v != v or v in (float("inf"), float("-inf")):
                    raise ValueError
            elif kind == "int":
                v = int(v)
                if v < 0:
                    raise ValueError
            elif kind == "bool":
                v = 1 if v in (True, 1, "1", "true", "sim") else 0
            elif kind.startswith("enum:"):
                if v not in kind[5:].split(","):
                    raise ValueError
        except (ValueError, TypeError):
            raise ValueError(f"Valor inválido para {field}: {data[field]!r}")
        out[field] = v
    return out


def _insert(conn, table, values):
    cols = ", ".join(values)
    marks = ", ".join("?" * len(values))
    cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(values.values()))
    return cur.lastrowid


def create_contract(conn, data):
    """Cria contrato e, opcionalmente, cláusulas/pagamentos/compromissos aninhados."""
    main = clean("contratos", data)
    children = {}
    for t in CHILDREN:
        items = data.get(t) or []
        if not isinstance(items, list):
            raise ValueError(f"{t} deve ser uma lista.")
        children[t] = [clean(t, i) for i in items]  # valida tudo antes de gravar
    with conn:
        cid = _insert(conn, "contratos", main)
        for t, items in children.items():
            for item in items:
                _insert(conn, t, {"contrato_id": cid, **item})
    return cid


def create_child(conn, table, contrato_id, data):
    if not conn.execute("SELECT 1 FROM contratos WHERE id=?", (contrato_id,)).fetchone():
        raise LookupError("Contrato não encontrado.")
    with conn:
        return _insert(conn, table, {"contrato_id": contrato_id, **clean(table, data)})


def update(conn, table, row_id, data):
    values = clean(table, data, partial=True)
    if table == "pagamentos" and values.get("status") == "pago" and not values.get("pago_em"):
        values["pago_em"] = date.today().isoformat()
    if table == "pagamentos" and values.get("status") == "pendente":
        values["pago_em"] = None
    if not values:
        raise ValueError("Nada para atualizar.")
    sets = ", ".join(f"{k}=?" for k in values)
    with conn:
        cur = conn.execute(f"UPDATE {table} SET {sets} WHERE id=?", [*values.values(), row_id])
    if cur.rowcount == 0:
        raise LookupError("Registro não encontrado.")


def delete(conn, table, row_id):
    with conn:
        cur = conn.execute(f"DELETE FROM {table} WHERE id=?", (row_id,))
    if cur.rowcount == 0:
        raise LookupError("Registro não encontrado.")


def get_contract(conn, cid):
    row = conn.execute("SELECT * FROM contratos WHERE id=?", (cid,)).fetchone()
    if not row:
        raise LookupError("Contrato não encontrado.")
    out = dict(row)
    order = {"clausulas": "id", "pagamentos": "vencimento", "compromissos": "data"}
    for t in CHILDREN:
        out[t] = [dict(r) for r in conn.execute(
            f"SELECT * FROM {t} WHERE contrato_id=? ORDER BY {order[t]}", (cid,))]
    return out


def list_contracts(conn):
    rows = conn.execute("""
      SELECT c.*,
        (SELECT COUNT(*) FROM clausulas WHERE contrato_id=c.id) AS n_clausulas,
        (SELECT COALESCE(SUM(valor),0) FROM pagamentos WHERE contrato_id=c.id AND status='pendente') AS a_pagar,
        (SELECT COALESCE(SUM(valor),0) FROM pagamentos WHERE contrato_id=c.id AND status='pago') AS pago
      FROM contratos c ORDER BY c.data_fim IS NULL, c.data_fim, c.nome""")
    return [dict(r) for r in rows]


def agenda(conn, hoje=None):
    """Todos os compromissos em aberto de contratos ativos, ordenados por data.

    Cada evento tem `chave` estável (muda se a data mudar) e `dias` até a data
    (negativo = atrasado).
    """
    hoje = hoje or date.today()
    ev = []

    def add(tipo, data, c, descricao, valor=None, ref=0):
        d = date.fromisoformat(data)
        ev.append({
            "tipo": tipo, "data": data, "dias": (d - hoje).days,
            "contrato_id": c["id"], "contrato": c["nome"], "contraparte": c["contraparte"],
            "descricao": descricao, "valor": valor, "chave": f"{tipo}:{c['id']}:{ref}:{data}",
        })

    for c in conn.execute("SELECT * FROM contratos WHERE status='ativo'"):
        if c["data_fim"]:
            add("vencimento_contrato", c["data_fim"], c, "Fim da vigência do contrato")
            if c["renovacao_automatica"] and c["aviso_previo_dias"]:
                aviso = date.fromisoformat(c["data_fim"]) - timedelta(days=c["aviso_previo_dias"])
                add("aviso_renovacao", aviso.isoformat(), c,
                    f"Último dia para avisar não-renovação (aviso prévio de {c['aviso_previo_dias']} dias)")
        for p in conn.execute(
                "SELECT * FROM pagamentos WHERE contrato_id=? AND status='pendente'", (c["id"],)):
            add("pagamento", p["vencimento"], c, p["descricao"], p["valor"], p["id"])
        for m in conn.execute(
                "SELECT * FROM compromissos WHERE contrato_id=? AND status='pendente'", (c["id"],)):
            desc = m["descricao"] + (f" (resp.: {m['responsavel']})" if m["responsavel"] else "")
            add("compromisso", m["data"], c, desc, None, m["id"])
    ev.sort(key=lambda e: (e["data"], e["contrato"]))
    return ev
