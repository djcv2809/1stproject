# Cria a tarefa diária das 10:00 no Agendador de Tarefas do Windows.
# Use pelo agendar_windows.bat (clique duplo). Para mudar o horário, edite $hora e rode de novo.
$ErrorActionPreference = "Stop"
$hora = "10:00"
$nome = "Gestao de Contratos - Avisos"
$pasta = Split-Path -Parent $MyInvocation.MyCommand.Path

# 'py' (instalador do python.org) é mais confiável que o atalho 'python' da Microsoft Store
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { $exe = $py.Source; $args = "-3 -m gestao_contratos lembretes" }
else {
    $p = Get-Command python -ErrorAction SilentlyContinue
    if (-not $p) { throw "Python não encontrado. Instale em python.org (marque 'Add Python to PATH')." }
    $exe = $p.Source; $args = "-m gestao_contratos lembretes"
}

$acao = New-ScheduledTaskAction -Execute $exe -Argument $args -WorkingDirectory $pasta
$gatilho = New-ScheduledTaskTrigger -Daily -At $hora
# StartWhenAvailable: se o PC estava desligado às 10:00, roda assim que ligar
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $config `
    -Description "Envia por e-mail os avisos de contratos (Gestão de Contratos)" -Force | Out-Null

Write-Host ""
Write-Host "Tarefa '$nome' criada: todos os dias às $hora."
Write-Host "Para testar agora, sem esperar: Start-ScheduledTask -TaskName '$nome'"
