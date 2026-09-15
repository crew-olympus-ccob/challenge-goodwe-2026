@echo off
rem Apaga o banco de dados e gera os dados de demonstracao de novo.
cd /d "%~dp0"
call iniciar.bat --reset
