#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
install_host.py - Registra el Host de Native Messaging en Windows para navegadores Chromium.
Configura:
1. native_host.bat con la ruta exacta de Python.
2. com.brodownloads.host.json con la ruta del .bat y el ID fijo de la extensión.
3. Claves en el Registro de Windows bajo HKEY_CURRENT_USER (no requiere privilegios de administrador).
"""

import os
import sys
import json
import winreg
from pathlib import Path

HOST_NAME = "com.brodownloads.host"
EXTENSION_ID = "aigjjkapingeecjkmcpcebopkjfikhcl"

REGISTRY_PATHS = [
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
    r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
    r"Software\Chromium\NativeMessagingHosts",
    r"Software\Opera Software\Opera Stable\NativeMessagingHosts",
    r"Software\Vivaldi\NativeMessagingHosts",
]


def install():
    native_dir = Path(__file__).resolve().parent
    native_host_py = native_dir / "native_host.py"
    native_host_bat = native_dir / "native_host.bat"
    manifest_json_path = native_dir / "com.brodownloads.host.json"

    python_exe = sys.executable

    print("==========================================================")
    print("  BRO-Downloads - Instalador de Puente Nativo (MV3)   ")
    print("==========================================================")
    print(f"[*] Directorio nativo: {native_dir}")
    print(f"[*] Python detectado:  {python_exe}")
    print(f"[*] Extension ID:      {EXTENSION_ID}")

    # 1. Crear native_host.bat
    bat_content = f'@echo off\n"{python_exe}" "{native_host_py}" %*\n'
    with open(native_host_bat, "w", encoding="utf-8") as f:
        f.write(bat_content)
    print(f"[+] Archivo bat generado: {native_host_bat.name}")

    # 2. Crear com.brodownloads.host.json
    manifest_data = {
        "name": HOST_NAME,
        "description": "BRO-Downloads Native Messaging Host",
        "path": str(native_host_bat),
        "type": "stdio",
        "allowed_origins": [
            f"chrome-extension://{EXTENSION_ID}/"
        ]
    }
    with open(manifest_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)
    print(f"[+] Manifiesto JSON generado: {manifest_json_path.name}")

    # 3. Registrar en Windows Registry (HKCU)
    print("\n[*] Registrando en el Registro de Windows (HKCU)...")
    success_count = 0
    for subkey in REGISTRY_PATHS:
        full_key_path = f"{subkey}\\{HOST_NAME}"
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, full_key_path)
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest_json_path))
            winreg.CloseKey(key)
            print(f"  [OK] HKCU\\{full_key_path}")
            success_count += 1
        except Exception as e:
            print(f"  [SKIP] No se pudo registrar en HKCU\\{full_key_path}: {e}")

    print("\n==========================================================")
    if success_count > 0:
        print("  ✅ Instalación completada con éxito.")
        print("  Los navegadores Chromium ya pueden comunicarse")
        print("  directamente con BRO-Downloads.")
    else:
        print("  ⚠️ No se pudo registrar en ninguna clave del registro.")
    print("==========================================================\n")


if __name__ == "__main__":
    install()
