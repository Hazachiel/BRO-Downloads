#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uninstall_host.py - Elimina las claves del Host de Native Messaging en Windows.
"""

import winreg
from pathlib import Path

HOST_NAME = "com.brodownloads.host"

REGISTRY_PATHS = [
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
    r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
    r"Software\Chromium\NativeMessagingHosts",
    r"Software\Opera Software\Opera Stable\NativeMessagingHosts",
    r"Software\Vivaldi\NativeMessagingHosts",
]


def uninstall():
    print("==========================================================")
    print("  BRO-Downloads - Desinstalador de Puente Nativo      ")
    print("==========================================================")
    for subkey in REGISTRY_PATHS:
        full_key_path = f"{subkey}\\{HOST_NAME}"
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, full_key_path)
            print(f"  [BORRADO] HKCU\\{full_key_path}")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"  [ERROR] No se pudo borrar HKCU\\{full_key_path}: {e}")

    print("\n  ✅ Desinstalación del registro completada.")
    print("==========================================================\n")


if __name__ == "__main__":
    uninstall()
