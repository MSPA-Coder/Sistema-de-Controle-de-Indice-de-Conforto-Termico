@echo off
setlocal EnableExtensions
chcp 65001 >NUL

set "ROOT_DIR=%~dp0.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"

set "APP_FILE=%ROOT_DIR%\app.py"
set "VENV_PY=%ROOT_DIR%\.venv\Scripts\python.exe"
if exist "%VENV_PY%" (
    set "PYTHON_EXE=%VENV_PY%"
) else (
    set "PYTHON_EXE=python"
)

if not defined CONFORTO_PORT set "CONFORTO_PORT=5000"

:menu
cls
echo ================================================
echo Conforto Térmico - Menu Flask
echo ================================================
echo.
echo Pasta: %ROOT_DIR%
echo Python: %PYTHON_EXE%
echo Porta atual: %CONFORTO_PORT%
echo.
echo 1 - Rodar aplicativo localmente
echo 2 - Rodar aplicativo como servidor na rede
echo 3 - Encerrar processos deste aplicativo
echo 4 - Alterar porta desta sessão
echo 0 - Sair
echo.
choice /C 12340 /N /M "Escolha uma opção: "

if errorlevel 5 goto sair
if errorlevel 4 goto alterar_porta
if errorlevel 3 goto encerrar_app
if errorlevel 2 goto iniciar_servidor
if errorlevel 1 goto iniciar_localhost

:iniciar_localhost
call :iniciar_app 127.0.0.1 local
goto pausa_menu

:iniciar_servidor
call :iniciar_app 0.0.0.0 rede
goto pausa_menu

:alterar_porta
echo.
set "NOVA_PORTA="
set /P "NOVA_PORTA=Informe a porta desejada [%CONFORTO_PORT%]: "
if not "%NOVA_PORTA%"=="" set "CONFORTO_PORT=%NOVA_PORTA%"
goto menu

:encerrar_app
echo.
echo Procurando processos deste aplicativo...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$currentPid = $PID; $root = [System.IO.Path]::GetFullPath($env:ROOT_DIR); $procs = Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $currentPid -and $_.CommandLine -and $_.Name -match '^(python|py)(\.exe)?$' -and $_.CommandLine -match '(?i)(^|\s|[\\/])app\.py(\s|$)' -and $_.CommandLine.Contains($root) }; if (-not $procs) { Write-Host 'Nenhum processo deste aplicativo foi encontrado.'; exit 0 }; foreach ($proc in $procs) { Stop-Process -Id $proc.ProcessId -Force; Write-Host ('Processo encerrado. PID: ' + $proc.ProcessId + ' - ' + $proc.CommandLine) }"
goto pausa_menu

:iniciar_app
set "CONFORTO_HOST=%~1"
set "MODO=%~2"
set "APP_URL=http://127.0.0.1:%CONFORTO_PORT%"
echo.
echo Iniciando em modo %MODO%...
echo URL local: %APP_URL%
if "%CONFORTO_HOST%"=="0.0.0.0" echo Na rede, acesse pelo IP desta máquina na porta %CONFORTO_PORT%.
start "Conforto Termico Flask - %MODO%" /D "%ROOT_DIR%" "%PYTHON_EXE%" "%APP_FILE%"
echo Abrindo navegador...
timeout /T 2 /NOBREAK >NUL
start "" "%APP_URL%"
exit /B 0

:pausa_menu
echo.
pause
goto menu

:sair
endlocal
exit /B 0
