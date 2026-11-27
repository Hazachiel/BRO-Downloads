import os
import time
import requests
from typing import Optional
from PySide6.QtCore import QThread, Signal


class DownloadWorker(QThread):
    """
    Worker individual que descarga un segmento (rango de bytes) específico de un archivo.
    Escribe directamente en el offset correspondiente del archivo destino final (seek).
    """

    bytes_received = Signal(int, int)       # (segment_id, bytes_count)
    segment_finished = Signal(int)          # (segment_id)
    segment_error = Signal(int, str)        # (segment_id, error_message)

    CHUNK_SIZE = 64 * 1024  # 64 KB por lectura de socket

    def __init__(
        self,
        segment_id: int,
        url: str,
        target_path: str,
        start_byte: int,
        end_byte: int,
        current_byte: int,
        cookies: Optional[str] = None,
        referer: Optional[str] = None,
        user_agent: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.segment_id = segment_id
        self.url = url
        self.target_path = target_path
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.current_byte = current_byte
        self.cookies = cookies
        self.referer = referer
        self.user_agent = user_agent

        self._stop_requested = False
        self.is_completed = (self.current_byte > self.end_byte)

    def request_stop(self):
        """Solicita la detención ordenada del worker sin corromper el archivo."""
        self._stop_requested = True

    def run(self):
        # Si este chunk ya estaba completado de una sesión previa, notificar y salir
        if self.current_byte > self.end_byte:
            self.is_completed = True
            self.segment_finished.emit(self.segment_id)
            return

        headers = {
            "User-Agent": self.user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BRO-Downloads/1.0",
            "Range": f"bytes={self.current_byte}-{self.end_byte}",
            "Connection": "keep-alive"
        }
        if self.referer:
            headers["Referer"] = self.referer
        if self.cookies:
            headers["Cookie"] = self.cookies

        file_handle = None
        response = None

        try:
            # Petición HTTP en modo streaming
            response = requests.get(
                self.url,
                headers=headers,
                stream=True,
                timeout=(10, 30)  # 10s connect, 30s read
            )

            # Verificar respuesta: 206 Partial Content (o 200 si el servidor ignora Range en archivo completo)
            if response.status_code not in (200, 206):
                if response.status_code in (401, 403, 410):
                    self.segment_error.emit(self.segment_id, f"AUTH_EXPIRED_{response.status_code}")
                else:
                    self.segment_error.emit(self.segment_id, f"HTTP Error {response.status_code}")
                return

            # Abrir archivo en modo lectura/escritura binaria
            file_handle = open(self.target_path, "r+b")
            file_handle.seek(self.current_byte)

            # Descarga por bloques de 64 KB
            for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                if self._stop_requested:
                    break

                if chunk:
                    chunk_len = len(chunk)

                    # Asegurar no sobrepasar el end_byte asignado a este chunk
                    if self.current_byte + chunk_len - 1 > self.end_byte:
                        chunk_len = self.end_byte - self.current_byte + 1
                        chunk = chunk[:chunk_len]

                    file_handle.write(chunk)
                    self.current_byte += chunk_len
                    self.bytes_received.emit(self.segment_id, chunk_len)

                    if self.current_byte > self.end_byte:
                        break

            file_handle.flush()

            if self.current_byte > self.end_byte:
                self.is_completed = True
                self.segment_finished.emit(self.segment_id)

        except requests.exceptions.RequestException as e:
            if not self._stop_requested:
                self.segment_error.emit(self.segment_id, str(e))
        except Exception as e:
            if not self._stop_requested:
                self.segment_error.emit(self.segment_id, f"File IO Error: {e}")
        finally:
            if file_handle:
                try:
                    file_handle.close()
                except Exception:
                    pass
            if response:
                try:
                    response.close()
                except Exception:
                    pass
