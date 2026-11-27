@echo off
title Instalando Puente Nativo - BRO-Downloads
chcp 65001 >nul
echo Ejecutando instalador de Native Messaging...
python "%~dp0native_host\install_host.py"
pause
