@echo off
rem Atualiza so o campo Observacoes dos contratos ja importados. Nao altera pagamentos nem o resto.
cd /d "%~dp0"
for %%f in (data\*.json) do (
  py -3 -m gestao_contratos atualizar-obs "%%f"
)
echo.
pause
