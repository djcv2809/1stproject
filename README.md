# Gestão de Contratos

Controle de contratos: escopo, cláusulas, pagamentos e compromissos, com aviso por e-mail
das datas. Python 3.10+ puro (sem dependências), dados em SQLite local.

## Uso

```bash
python -m gestao_contratos servir                 # interface em http://127.0.0.1:8000
python -m gestao_contratos importar contrato.json # cadastra contrato(s) a partir de JSON
python -m gestao_contratos lembretes --simular    # mostra o e-mail sem enviar
python -m gestao_contratos lembretes              # envia e registra o que já foi avisado
python -m unittest discover -s tests -t .         # testes
```

Banco em `data/contratos.db` (ignorado pelo git; troque com `GC_DB=/caminho/arquivo.db`).

## Formato do JSON de importação

```json
{
  "nome": "Locação sala", "contraparte": "Imobiliária X", "objeto": "...", "escopo": "...",
  "data_inicio": "2026-02-01", "data_fim": "2027-01-31", "valor_total": 42000,
  "renovacao_automatica": true, "aviso_previo_dias": 90,
  "clausulas":    [{"titulo": "Reajuste", "texto": "IGP-M anual", "categoria": "Financeira"}],
  "pagamentos":   [{"descricao": "Aluguel nov/26", "vencimento": "2026-11-10", "valor": 3500}],
  "compromissos": [{"descricao": "Vistoria", "data": "2026-11-20", "responsavel": "Paulo"}]
}
```
Datas em `AAAA-MM-DD`. Se qualquer item for inválido, nada é gravado.

## O que entra na agenda e nos e-mails (só contratos com status "ativo")

- pagamentos pendentes · compromissos pendentes
- fim da vigência · prazo-limite de aviso de não-renovação (`data_fim − aviso_previo_dias`, se houver renovação automática)

Os avisos saem com antecedência de 30, 15, 7, 1 e 0 dias (ajustável em `GC_ANTECEDENCIA="30,10,3,0"`)
e uma vez para itens atrasados. Cada aviso é enviado uma única vez; se a data mudar, o aviso é reaberto.
Os avisos de um mesmo conjunto de destinatários vão num único e-mail-resumo.

### Destinatários por contrato

Cada contrato pode ter o campo `emails_aviso` (um ou mais e-mails separados por vírgula, no JSON ou
na tela do contrato). Os avisos desse contrato vão **só** para esses endereços; contratos sem o campo
usam `MAIL_TO`. Útil para separar assuntos pessoais dos da empresa. Bancos antigos recebem o campo
automaticamente.

## Configurar o e-mail

```bash
export SMTP_HOST=smtp.gmail.com SMTP_PORT=587
export SMTP_USER=voce@gmail.com SMTP_PASS='senha-de-app'   # Gmail exige "senha de app"
export MAIL_FROM=voce@gmail.com MAIL_TO=voce@gmail.com,socio@empresa.com
```

Para envio diário automático, agende `python -m gestao_contratos lembretes` (cron, Agendador de
Tarefas do Windows etc.) em uma máquina que fique ligada, com essas variáveis definidas.

## Rodar todo dia (Windows)

1. Instale o Python 3.10+ (python.org; marque "Add Python to PATH") e copie esta pasta para o computador.
2. Copie `.env.example` para `.env` e preencha (no Gmail, gere uma *senha de app* em
   myaccount.google.com/apppasswords; exige verificação em duas etapas).
3. Coloque os JSONs em `data\` e importe cada um: `python -m gestao_contratos importar data\arquivo.json`
4. Teste sem enviar: `python -m gestao_contratos lembretes --simular`
5. Agendador de Tarefas > Criar Tarefa Básica > Diária (ex.: 08:00) > Iniciar um programa:
   programa `python`, argumentos `-m gestao_contratos lembretes`, "Iniciar em" = a pasta do projeto.
   Em Configurações da tarefa, marque **"Executar assim que possível se uma execução agendada for perdida"**.
6. Faça backup periódico de `data\contratos.db`: é o único lugar onde os dados existem.

Se o computador ficar desligado, o aviso sai na próxima vez que ele ligar (cada aviso é enviado uma vez,
ao entrar na janela de 30/15/7/1/0 dias). No macOS/Linux, use `cron` com o mesmo comando.

## Segurança

- O servidor escuta só em `127.0.0.1` e **não tem login**. Não exponha à rede/internet sem
  colocar autenticação na frente.
- O banco contém dados contratuais: não o versione nem o compartilhe sem necessidade.
