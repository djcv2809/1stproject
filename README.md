# Consolidador de extratos e recebíveis (uso local)

Lê arquivos que os próprios bancos geram e consolida tudo num formato único,
**sem precisar da sua senha de internet banking**. Fase 1 do plano em fases
(arquivos agora; APIs oficiais depois, trocando só o importador).

## Fontes suportadas (fase 1 — importador por arquivo)

| Banco | Formato esperado | Pasta |
|-------|------------------|-------|
| Banco do Brasil | extrato `.ofx` | `entrada/bb/` |
| Itaú | extrato `.ofx` | `entrada/itau/` |
| Santander (conta) | extrato `.ofx` | `entrada/santander/` |
| Santander (cobrança) | retorno CNAB 240 `.ret/.txt` | `entrada/santander_cobranca/` |
| Rede (maquininha) | relatório `.csv` | `entrada/rede/` |

## Rodar

```bash
python3 -m extratos --entrada entrada --saida saida --ref 2026-11-05
```

Saída em `saida/`: `lancamentos.csv`, `titulos_santander.csv` (com situação
liquidado/vencido/a vencer/baixado) e `resumo.html` (resumo por banco,
situação da cobrança e conciliação Rede × crédito no banco). Os CSV abrem
direto no Excel.

## Testar com dados fictícios (sem tocar em dado real)

```bash
python3 demo/gerar_demo.py entrada_demo
python3 -m extratos --entrada entrada_demo --saida saida_demo --ref 2026-11-05
python3 -m unittest discover -s tests -t .
```

## Avisos importantes

- **CNAB 240 (Santander cobrança):** as posições seguem o padrão FEBRABAN.
  O layout do Santander pode divergir — valide com um arquivo de retorno real
  antes de confiar nos valores.
- **Rede:** o layout do CSV varia conforme o relatório exportado; se uma coluna
  não for reconhecida, o erro lista os cabeçalhos para ajuste do mapa em
  `extratos/rede.py`.
- Para sair dos dados fictícios, troque os importadores pelo layout real dos
  seus arquivos. Mande um exemplo de cada (com dados sensíveis ocultados).

## Próximas fases

- **Fase 2 — APIs oficiais:** BB, Itaú, Santander (extrato + cobrança) e Rede.
  Exige credenciamento PJ e certificado digital; só troca a fonte, o resto fica.
