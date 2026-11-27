@echo off
title Desinstalando Puente Nativo - BRO-Downloads
chcp 65001 >nul
echo Eliminando registro de Native Messaging...
python "%~dp0native_host\uninstall_host.py"
pause
