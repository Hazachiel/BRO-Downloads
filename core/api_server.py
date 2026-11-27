import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from typing import Optional

from PySide6.QtCore import QThread, Signal
from core.settings_manager import SettingsManager

logger = logging.getLogger("ApiServer")


class SecureApiRequestHandler(BaseHTTPRequestHandler):
    """
    Manejador HTTP seguro para la comunicación con la extensión del navegador.
    Aplica defensas estrictas contra CSRF, ataques de origen cruzado (CORS) y fuerza bruta.
    """

    def log_message(self, format, *args):
        # Desactivar logs ruidosos en la consola estándar
        pass

    def _is_client_allowed(self) -> bool:
        """Solo permite conexiones estrictamente originadas desde la máquina local (localhost)."""
        client_ip = self.client_address[0]
        return client_ip in ("127.0.0.1", "::1", "localhost")

    def _is_origin_allowed(self) -> bool:
        """
        Medida anti-CSRF: Si hay cabecera Origin, DEBE provenir de una extensión del navegador.
        Cualquier página web regular (https://sitio.com) será rechazada inmediatamente con 403.
        """
        origin = self.headers.get("Origin", "")
        if not origin:
            # Peticiones directas sin origin (ej: curl local o inspección)
            return True
        return origin.startswith("chrome-extension://") or origin.startswith("moz-extension://")

    def _is_token_valid(self) -> bool:
        """Verifica el token criptográfico pre-compartido enviado en la cabecera X-BRODownload-Token."""
        token = self.headers.get("X-BRODownload-Token", "")
        expected = self.server.api_token
        if not expected:
            return True
        return token == expected

    def _send_cors_headers(self):
        """Emite cabeceras CORS seguras restringidas al origen de la extensión."""
        origin = self.headers.get("Origin", "")
        if origin and (origin.startswith("chrome-extension://") or origin.startswith("moz-extension://")):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "X-BRODownload-Token, Content-Type, Content-Length")
            self.send_header("Access-Control-Max-Age", "86400")

    def _send_json_response(self, status_code: int, data: dict):
        response_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self):
        """Maneja el preflight de CORS de los navegadores."""
        if not self._is_client_allowed() or not self._is_origin_allowed():
            self.send_error(403, "Forbidden Origin")
            return

        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Endpoint de verificación de estado y sincronización de reglas."""
        if not self._is_client_allowed():
            self.send_error(403, "Forbidden Client")
            return

        if not self._is_origin_allowed():
            self.send_error(403, "Forbidden Origin")
            return

        if not self._is_token_valid():
            self._send_json_response(401, {"error": "Token de autenticación inválido o ausente"})
            return

        parsed_path = urlparse(self.path).path
        if parsed_path in ("/status", "/health"):
            settings = SettingsManager().settings
            self._send_json_response(200, {
                "status": "online",
                "app": "BRO-Downloads",
                "version": "1.0",
                "monitored_extensions": settings.monitored_extensions,
                "excluded_sites": settings.excluded_sites
            })
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        """Recibe una descarga interceptada por la extensión."""
        if not self._is_client_allowed():
            self.send_error(403, "Forbidden Client")
            return

        if not self._is_origin_allowed():
            self.send_error(403, "Forbidden Origin")
            return

        if not self._is_token_valid():
            self._send_json_response(401, {"error": "Token de autenticación inválido o ausente"})
            return

        parsed_path = urlparse(self.path).path
        if parsed_path != "/download":
            self.send_error(404, "Not Found")
            return

        # Limitar tamaño máximo del cuerpo a 1 MB para prevenir desbordes de memoria
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 1024 * 1024:
            self._send_json_response(413, {"error": "Payload demasiado grande"})
            return

        try:
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
        except Exception:
            self._send_json_response(400, {"error": "Formato JSON inválido"})
            return

        # Validar URL
        url = data.get("url", "").strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            self._send_json_response(400, {"error": "Protocolo de URL no soportado"})
            return

        # Emitir la señal hacia Qt en el hilo principal
        self.server.qt_server.download_received.emit(data)

        self._send_json_response(200, {
            "success": True,
            "message": "Descarga enviada a BRO-Downloads correctamente"
        })


class ApiServer(QThread):
    """
    Servidor local HTTP montado en un hilo de PySide6.
    Comunica la extensión del navegador con BRO-Downloads de forma asíncrona y segura.
    """

    download_received = Signal(dict)
    server_started = Signal(int)
    server_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings_manager = SettingsManager()
        self._httpd: Optional[HTTPServer] = None
        self._is_running = False

    def run(self):
        port = self.settings_manager.settings.server_port
        token = self.settings_manager.settings.server_token

        # Si el token aún no existe, crearlo y guardarlo
        if not token:
            import secrets
            token = secrets.token_hex(16)
            self.settings_manager.settings.server_token = token
            self.settings_manager.save()

        try:
            # Enlazar exclusivamente a 127.0.0.1 (Loopback local, inaccesible desde la red externa)
            server_address = ("127.0.0.1", port)
            self._httpd = HTTPServer(server_address, SecureApiRequestHandler)
            self._httpd.api_token = token
            self._httpd.qt_server = self
            self._is_running = True

            self.server_started.emit(port)
            self._httpd.serve_forever()
        except OSError as e:
            self._is_running = False
            self.server_error.emit(f"Puerto {port} no disponible: {e}")
        except Exception as e:
            self._is_running = False
            self.server_error.emit(str(e))

    def stop(self):
        """Detiene limpiamente el servidor HTTP y libera el puerto."""
        if self._httpd and self._is_running:
            self._is_running = False
            self._httpd.shutdown()
            self._httpd.server_close()
        self.wait(1500)
