#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
native_host.py - Host de Native Messaging para BRO-Downloads (Windows / Chromium).
Recibe mensajes por stdin/stdout usando el protocolo oficial de Chromium:
[4 bytes unsigned int en little-endian con la longitud del mensaje] + [JSON en UTF-8].
"""

import sys
import os
import json
import struct
import base64
import subprocess
import urllib.request
import urllib.error
from pathlib import Path


def read_message():
    """Lee un mensaje entrante desde stdin según el framing de Chromium."""
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length or len(raw_length) < 4:
        return None
    message_length = struct.unpack('<I', raw_length)[0]
    message_bytes = sys.stdin.buffer.read(message_length)
    if len(message_bytes) < message_length:
        return None
    return json.loads(message_bytes.decode('utf-8'))


def send_message(message):
    """Envía un mensaje saliente a Chromium por stdout con el framing de 4 bytes."""
    encoded = json.dumps(message, ensure_ascii=False).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('<I', len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def get_app_settings():
    """Lee el puerto y token de settings.json en ~/.brodownloads/ si existen."""
    settings_file = Path.home() / ".brodownloads" / "settings.json"
    port = 9876
    token = ""
    if settings_file.exists():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                port = data.get("server_port", 9876)
                token = data.get("server_token", "")
        except Exception:
            pass
    return port, token


def forward_to_running_app(payload, port, token):
    """Intenta enviar el payload al servidor HTTP local de la app en ejecución."""
    url = f"http://127.0.0.1:{port}/download"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-BRODownload-Token": token,
            "Origin": "chrome-extension://aigjjkapingeecjkmcpcebopkjfikhcl"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            resp_body = resp.read().decode("utf-8")
            return True, json.loads(resp_body) if resp_body else {}
    except Exception as e:
        return False, str(e)


def launch_app_with_download(payload):
    """Si la app no está corriendo, la inicia en un proceso independiente pasándole la descarga."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    main_py = project_root / "main.py"

    if not main_py.exists():
        return False, f"No se encontró main.py en {project_root}"

    b64_payload = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

    python_exe = sys.executable
    cmd = [python_exe, str(main_py), "--add-download", b64_payload]

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    try:
        subprocess.Popen(
            cmd,
            cwd=str(project_root),
            creationflags=creationflags,
            close_fds=True
        )
        return True, "App iniciada exitosamente"
    except Exception as e:
        return False, str(e)


def main():
    while True:
        try:
            msg = read_message()
            if msg is None:
                break

            action = msg.get("action", "")

            # 1. Ping / Test de conexión
            if action == "ping":
                send_message({
                    "status": "ok",
                    "app": "BRO-Downloads Native Host",
                    "version": "1.1"
                })
                continue

            # 2. Descarga interceptada
            if action == "download":
                port, token = get_app_settings()
                success, details = forward_to_running_app(msg, port, token)

                if success:
                    send_message({
                        "status": "ok",
                        "delivered": "running_instance",
                        "details": details
                    })
                else:
                    # La app estaba cerrada: la lanzamos
                    launched, err = launch_app_with_download(msg)
                    if launched:
                        send_message({
                            "status": "ok",
                            "delivered": "cold_start",
                            "details": "BRO-Downloads iniciado en segundo plano"
                        })
                    else:
                        send_message({
                            "status": "error",
                            "error": f"Fallo al abrir app: {err}"
                        })
                continue

            # Acción no reconocida
            send_message({"status": "unknown_action", "action": action})

        except Exception as e:
            send_message({"status": "error", "error": str(e)})
            break


if __name__ == "__main__":
    main()
