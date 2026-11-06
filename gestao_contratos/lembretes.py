"""Lembretes por e-mail das datas de compromissos dos contratos.

Configuração por variáveis de ambiente:
  SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASS, MAIL_FROM,
  MAIL_TO  destinatários padrão (vários separados por vírgula), usados pelos contratos sem `emails_aviso`
  GC_ANTECEDENCIA  dias de antecedência que disparam aviso (padrão "30,15,7,1,0")
"""
import os
import smtplib
import socket
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
        else:
            janelas = [l for l in leads if l >= e["dias"]]
            if not janelas:  # ainda fora da primeira janela
                continue
            bucket = str(min(janelas))  # janela mais próxima; recupera dias em que o app não rodou
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


class ErroEmail(RuntimeError):
    """Falha de envio com explicação em português."""


def _explicar(exc, host, port):
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return ("Login recusado pelo servidor. No Gmail, use a SENHA DE APP de 16 letras (não a senha "
                "normal), com verificação em duas etapas ativa, e SMTP_USER igual ao Gmail que gerou a senha.")
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return (f"A conexão com {host}:{port} foi fechada. Causas comuns: antivírus/firewall bloqueando "
                f"e-mail, rede ou operadora bloqueando a porta {port}, ou porta errada. Tente "
                f"SMTP_PORT={'587' if port == 465 else '465'} no .env. ({exc})")
    if isinstance(exc, (socket.timeout, TimeoutError, ConnectionError, socket.gaierror, OSError)):
        return (f"Não consegui conectar em {host}:{port} ({exc}). Verifique a internet, o firewall/"
                f"antivírus e tente a outra porta (587 ou 465).")
    return str(exc)


def enviar_smtp(assunto, corpo, destinatarios=None):
    host = os.environ.get("SMTP_HOST")
    to = ",".join(destinatarios) if destinatarios else os.environ.get("MAIL_TO")
    if not host or not to:
        raise RuntimeError("Defina SMTP_HOST e MAIL_TO (veja README).")
    user, pwd = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
    msg = EmailMessage()
    msg["Subject"], msg["To"] = assunto, to
    msg["From"] = os.environ.get("MAIL_FROM") or user or "contratos@localhost"
    msg.set_content(corpo)
    port = int(os.environ.get("SMTP_PORT", "587"))
    try:
        # porta 465 = SSL direto; demais (587) = STARTTLS
        srv = smtplib.SMTP_SSL(host, port, timeout=30) if port == 465 else smtplib.SMTP(host, port, timeout=30)
        with srv as s:
            if port != 465:
                s.starttls()
            if user:
                s.login(user, pwd or "")
            s.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise ErroEmail(_explicar(exc, host, port)) from exc


def executar(conn, hoje=None, enviar=enviar_smtp, simular=False):
    """Envia os avisos pendentes: um e-mail-resumo por conjunto de destinatários.

    Contratos com `emails_aviso` vão só para esses endereços; os demais, para MAIL_TO.
    Um envio que falha não marca nada como enviado; os outros grupos seguem normalmente.
    """
    hoje = hoje or date.today()
    grupos = {}
    for e in pendentes(conn, hoje):
        dest = tuple(e["emails_aviso"].split(",")) if e["emails_aviso"] else ()
        grupos.setdefault(dest, []).append(e)
    enviados, erros = [], []
    for dest, eventos in grupos.items():
        assunto, corpo = montar_email(eventos, hoje)
        if simular:
            print(f"Para: {', '.join(dest) or '(MAIL_TO padrão)'}\nAssunto: {assunto}\n\n{corpo}\n")
            enviados += eventos
            continue
        try:
            enviar(assunto, corpo, list(dest))
        except Exception as exc:
            erros.append(exc)
            continue
        with conn:
            conn.executemany(
                "INSERT OR IGNORE INTO lembretes_enviados (chave, enviado_em) VALUES (?, ?)",
                [(e["chave_envio"], datetime.now().isoformat(timespec="seconds")) for e in eventos])
        enviados += eventos
    if erros:
        raise erros[0]
    return enviados
