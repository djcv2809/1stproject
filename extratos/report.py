from __future__ import annotations

import csv
import html
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from .model import Lancamento, Titulo


def brl(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def dedup(lancs: list[Lancamento]) -> tuple[list[Lancamento], int]:
    vistos, saida = set(), []
    for l in lancs:
        if l.chave in vistos:
            continue
        vistos.add(l.chave)
        saida.append(l)
    return sorted(saida, key=lambda l: (l.data, l.fonte)), len(lancs) - len(saida)


def conciliar_rede(lancs: list[Lancamento], janela: int = 3) -> list[dict]:
    """Soma da Rede por data de pagamento x crédito bancário com 'REDE' na descrição."""
    por_dia: dict[date, Decimal] = defaultdict(Decimal)
    for l in lancs:
        if l.fonte == "rede":
            por_dia[l.data] += l.valor
    bancos = [l for l in lancs if l.fonte != "rede" and l.valor > 0 and "REDE" in l.descricao.upper()]
    usados, saida = set(), []
    for dia, esperado in sorted(por_dia.items()):
        achado = None
        for k, b in enumerate(bancos):
            if k in usados:
                continue
            if timedelta(0) <= b.data - dia <= timedelta(days=janela) and abs(b.valor - esperado) <= Decimal("0.01"):
                achado = k
                break
        if achado is not None:
            usados.add(achado)
            saida.append({"dia": dia, "esperado": esperado, "banco": bancos[achado].valor, "status": "OK"})
        else:
            parcial = next((b for k, b in enumerate(bancos) if k not in usados
                            and timedelta(0) <= b.data - dia <= timedelta(days=janela)), None)
            saida.append({"dia": dia, "esperado": esperado,
                          "banco": parcial.valor if parcial else None,
                          "status": "DIVERGENTE" if parcial else "NÃO ENCONTRADO"})
    return saida


def gravar_csv(path: Path, cab: list[str], linhas: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel abre acentos certo
        w = csv.writer(f, delimiter=";")
        w.writerow(cab)
        w.writerows(linhas)


def gerar(lancs: list[Lancamento], titulos: list[Titulo], ref: date, saida: Path, duplicados: int) -> Path:
    saida.mkdir(parents=True, exist_ok=True)
    gravar_csv(saida / "lancamentos.csv",
               ["data", "fonte", "conta", "descricao", "valor", "documento", "arquivo"],
               [[l.data.strftime("%d/%m/%Y"), l.fonte, l.conta, l.descricao,
                 str(l.valor).replace(".", ","), l.documento, l.arquivo] for l in lancs])
    gravar_csv(saida / "titulos_santander.csv",
               ["nosso_numero", "documento", "sacado", "vencimento", "valor", "situacao", "valor_pago", "data_credito"],
               [[t.nosso_numero, t.documento, t.sacado,
                 t.vencimento.strftime("%d/%m/%Y") if t.vencimento else "",
                 str(t.valor).replace(".", ","), t.situacao(ref),
                 str(t.valor_pago).replace(".", ","),
                 t.data_credito.strftime("%d/%m/%Y") if t.data_credito else ""]
                for t in sorted(titulos, key=lambda t: t.vencimento or date.min)])

    e = html.escape
    por_fonte: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0), Decimal(0)])
    for l in lancs:
        p = por_fonte[l.fonte]
        p[0 if l.valor > 0 else 1] += l.valor
        p[2] += 1
    sit: dict[str, list] = defaultdict(lambda: [0, Decimal(0)])
    for t in titulos:
        s = t.situacao(ref)
        sit[s][0] += 1
        sit[s][1] += t.valor_pago if s == "liquidado" else t.valor
    conc = conciliar_rede(lancs)

    h = [f"<!doctype html><meta charset=utf-8><title>Resumo</title><style>body{{font:14px sans-serif;max-width:900px;margin:2em auto}}"
         "table{border-collapse:collapse;width:100%;margin-bottom:2em}td,th{border:1px solid #ccc;padding:4px 8px;text-align:right}"
         "th:first-child,td:first-child{text-align:left}.v{color:#b00}.ok{color:#070}</style>",
         f"<h1>Resumo — posição em {ref:%d/%m/%Y}</h1>",
         f"<p>{len(lancs)} lançamentos ({duplicados} duplicados descartados), {len(titulos)} títulos de cobrança.</p>",
         "<h2>Lançamentos por fonte</h2><table><tr><th>Fonte<th>Qtd<th>Créditos<th>Débitos<th>Líquido</tr>"]
    for f, (c, d, n) in sorted(por_fonte.items()):
        h.append(f"<tr><td>{e(f)}<td>{n}<td>{brl(c)}<td>{brl(d)}<td>{brl(c + d)}</tr>")
    h.append("</table><h2>Cobrança Santander</h2><table><tr><th>Situação<th>Qtd<th>Valor</tr>")
    for s in ("liquidado", "vencido", "a vencer", "baixado", "rejeitado"):
        if s in sit:
            cls = ' class="v"' if s == "vencido" else ""
            h.append(f"<tr{cls}><td>{s}<td>{sit[s][0]}<td>{brl(sit[s][1])}</tr>")
    h.append("</table>")
    vencidos = [t for t in titulos if t.situacao(ref) == "vencido"]
    if vencidos:
        h.append("<h3>Títulos vencidos</h3><table><tr><th>Sacado<th>Documento<th>Vencimento<th>Dias<th>Valor</tr>")
        for t in sorted(vencidos, key=lambda t: t.vencimento):
            h.append(f"<tr><td>{e(t.sacado)}<td>{e(t.documento)}<td>{t.vencimento:%d/%m/%Y}"
                     f"<td>{(ref - t.vencimento).days}<td>{brl(t.valor)}</tr>")
        h.append("</table>")
    if conc:
        h.append("<h2>Conciliação Rede × banco</h2><table><tr><th>Pagamento Rede<th>Esperado<th>Crédito no banco<th>Status</tr>")
        for c in conc:
            cls = "ok" if c["status"] == "OK" else "v"
            b = brl(c["banco"]) if c["banco"] is not None else "—"
            h.append(f"<tr class={cls}><td>{c['dia']:%d/%m/%Y}<td>{brl(c['esperado'])}<td>{b}<td>{c['status']}</tr>")
        h.append("</table>")
    out = saida / "resumo.html"
    out.write_text("".join(h), encoding="utf-8")
    return out
