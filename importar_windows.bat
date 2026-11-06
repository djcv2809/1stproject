@echo off
rem Importa todos os JSON da pasta data\ UMA vez. Recusa rodar de novo, para nao duplicar contratos.
cd /d "%~dp0"
if exist data\contratos.db (
  echo O banco ja existe. Importar de novo duplicaria os contratos. Nada foi feito.
  pause
  exit /b 1
)
for %%f in (data\*.json) do (
  echo Importando %%f
  py -3 -m gestao_contratos importar "%%f"
)
echo.
echo Concluido. Teste sem enviar e-mail: py -3 -m gestao_contratos lembretes --simular
pause
