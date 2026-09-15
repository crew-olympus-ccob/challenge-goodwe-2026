@echo off
rem EV ChargeHub - duplo clique para abrir o sistema.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 main.py %*
) else (
    python main.py %*
)
if errorlevel 1 (
    echo.
    echo Nao foi possivel iniciar. Verifique se o Python 3.11 ou mais novo esta instalado ^(python.org^).
    pause
)
