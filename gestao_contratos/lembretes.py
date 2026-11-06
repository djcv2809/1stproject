"""Lembretes por e-mail das datas de compromissos dos contratos.

Configuração por variáveis de ambiente:
  SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASS, MAIL_FROM, MAIL_TO (vários separados por vírgula)
  GC_ANTECEDENCIA  dias de antecedência que disparam aviso (padrão "30,15,7,1,0")
"""
import os
import smtplib
from datetime import date, datetime
from email.message import EmailMessage

from . import db

ROTULOS = {
    "pagamento": "Pagamento",
    "compromisso": "Compromisso",
    "vencimento_contrato": "Fim de vigência",
    "aviso_renovacao": "Prazo de aviso de renovação",
}


def brl(v):
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def br_date(iso):
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def antecedencias():
    raw = os.environ.get("GC_ANTECEDENCIA", "30,15,7,1,0")
    return sorted({int(x) for x in raw.split(",") if x.strip()}, reverse=True)


def pendentes(conn, hoje=None, leads=None):
    """Eventos que devem ser avisados agora e ainda não foram."""
    leads = antecedencias() if leads is None else leads
    out = []
    for e in db.agenda(conn, hoje):
        if e["dias"] < 0:
            bucket = "atraso"
        elif e["dias"] in leads:
            bucket = str(e["dias"])
        else:
            continue
        chave = f"{e['chave']}|{bucket}"
        if conn.execute("SELECT 1 FROM lembretes_enviados WHERE chave=?", (chave,)).fetchone():
            continue
        out.append({**e, "bucket": bucket, "chave_envio": chave})
    return out


def montar_email(eventos, hoje):
    def quando(e):
        d = e["dias"]
        if d < 0:
            return f"ATRASADO há {-d} dia(s)"
        return "HOJE" if d == 0 else ("amanhã" if d == 1 else f"em {d} dias")

    linhas = [f"Gestão de Contratos — avisos de {hoje.strftime('%d/%m/%Y')}", ""]
    for e in sorted(eventos, key=lambda e: e["dias"]):
        valor = f" — {brl(e['valor'])}" if e["valor"] is not None else ""
        linhas.append(f"• [{quando(e)}] {br_date(e['data'])} · {ROTULOS[e['tipo']]}: "
                      f"{e['descricao']}{valor}")
        linhas.append(f"    Contrato: {e['contrato']} ({e['contraparte']})")
    assunto = f"[Contratos] {len(eventos)} aviso(s) de compromissos"
    if any(e["dias"] < 0 for e in eventos):
        assunto += " — há itens ATRASADOS"
    return assunto, "\n".join(linhas)


def enviar_smtp(assunto, corpo):
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("MAIL_TO")
    if not host or not to:
        raise RuntimeError("Defina SMTP_HOST e MAIL_TO (veja README).")
    user, pwd = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
    msg = EmailMessage()
    msg["Subject"], msg["To"] = assunto, to
    msg["From"] = os.environ.get("MAIL_FROM") or user or "contratos@localhost"
    msg.set_content(corpo)
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        if user:
            s.login(user, pwd or "")
        s.send_message(msg)


def executar(conn, hoje=None, enviar=enviar_smtp, simular=False):
    """Envia um resumo único com todos os avisos pendentes. Retorna a lista de eventos."""
    hoje = hoje or date.today()
    eventos = pendentes(conn, hoje)
    if not eventos:
        return []
    assunto, corpo = montar_email(eventos, hoje)
    if simular:
        print(f"Assunto: {assunto}\n\n{corpo}")
        return eventos
    enviar(assunto, corpo)  # se falhar, nada é marcado como enviado
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO lembretes_enviados (chave, enviado_em) VALUES (?, ?)",
            [(e["chave_envio"], datetime.now().isoformat(timespec="seconds")) for e in eventos])
    return eventos
