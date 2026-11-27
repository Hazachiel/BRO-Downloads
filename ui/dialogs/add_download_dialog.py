import os
import re
import uuid
import shutil
import requests
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlparse

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QComboBox, QInputDialog, QMessageBox,
    QProgressBar
)
from PySide6.QtCore import Qt, Signal, QThread
from models.download_item import DownloadItem, DownloadStatus, DownloadCategory
from core.settings_manager import SettingsManager
from core.download_task import DownloadTask
from core.constants import TEMP_DOWNLOAD_DIR


class UrlProbeWorker(QThread):
    """
    Sonda en segundo plano para obtener el nombre real (Content-Disposition)
    y tamaño del archivo mientras el usuario tiene abierta la ventana de añadir descarga.
    """
    probe_finished = Signal(str, int)  # (real_filename, total_size_bytes)

    def __init__(
        self,
        url: str,
        cookies: str = "",
        referer: str = "",
        user_agent: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.url = url
        self.cookies = cookies
        self.referer = referer
        self.user_agent = user_agent

    def run(self):
        try:
            lower_url = self.url.lower()
            if ".m3u8" in lower_url or ".mpd" in lower_url or "youtube.com" in lower_url or "youtu.be" in lower_url:
                # Los streams dinámicos no exponen el tamaño final en HEAD
                self.probe_finished.emit("", 0)
                return

            headers = {
                "User-Agent": self.user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BRO-Downloads/1.0",
                "Range": "bytes=0-0"
            }
            if self.referer:
                headers["Referer"] = self.referer
            if self.cookies:
                headers["Cookie"] = self.cookies
            resp = requests.get(self.url, headers=headers, stream=True, timeout=4)

            total_size = 0
            content_range = resp.headers.get("Content-Range", "")
            if content_range and "/" in content_range:
                try:
                    total_size = int(content_range.split("/")[-1])
                except ValueError:
                    total_size = int(resp.headers.get("Content-Length", 0))
            else:
                total_size = int(resp.headers.get("Content-Length", 0))

            disposition = resp.headers.get("Content-Disposition", "")
            real_name = self._extract_filename(disposition)

            resp.close()

            if real_name or total_size > 0:
                self.probe_finished.emit(real_name or "", total_size)
        except Exception:
            pass

    def _extract_filename(self, disposition: str) -> Optional[str]:
        if not disposition:
            return None
        raw_name = None
        match_utf = re.search(r"filename\*\s*=\s*UTF-8''([^;\r\n]+)", disposition, re.IGNORECASE)
        if match_utf:
            raw_name = match_utf.group(1).strip("\"'")
        else:
            match_std = re.search(r'filename\s*=\s*"([^"]+)"', disposition, re.IGNORECASE)
            if match_std:
                raw_name = match_std.group(1)
            else:
                match_bare = re.search(r'filename\s*=\s*([^;\r\n]+)', disposition, re.IGNORECASE)
                if match_bare:
                    raw_name = match_bare.group(1).strip("\"'")

        if raw_name:
            decoded = unquote(raw_name)
            clean = re.sub(r'[<>:"/\\|?*]', '_', decoded).strip()
            return clean or None
        return None


class AddDownloadDialog(QDialog):
    """
    Diálogo para ingresar una nueva URL de descarga.
    Decodifica caracteres especiales de URLs, sondea el nombre real en la nube,
    soporta captura desde navegadores y respeta si el usuario edita el nombre a mano.
    """

    queue_created = Signal(str)

    def __init__(
        self,
        initial_url: str = "",
        initial_filename: str = "",
        existing_queues: Optional[List[str]] = None,
        default_save_path: str = None,
        initial_cookies: str = "",
        initial_referer: str = "",
        initial_user_agent: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Añadir nueva descarga")
        self.resize(580, 290)

        self.settings_manager = SettingsManager()
        self._save_path = default_save_path or self.settings_manager.settings.default_save_path
        self._existing_queues: List[str] = list(existing_queues) if existing_queues else ["Cola Principal"]
        if "Cola Principal" not in self._existing_queues:
            self._existing_queues.insert(0, "Cola Principal")

        self.created_item: Optional[DownloadItem] = None
        self.download_immediately: bool = True
        self._user_edited_filename: bool = False
        self._cookies = initial_cookies
        self._referer = initial_referer
        self._user_agent = initial_user_agent
        self._probe_worker: Optional[UrlProbeWorker] = None

        # Soporte para descarga anticipada en segundo plano (Pre-fetching)
        self._speculative_task: Optional[DownloadTask] = None
        self._speculative_item: Optional[DownloadItem] = None
        self._temp_folder: Optional[str] = None
        self.speculative_already_completed: bool = False

        self._init_ui()

        # Rellenar datos si vienen del navegador
        if initial_url:
            self.url_input.setText(initial_url)
        if initial_filename:
            self.filename_input.setText(initial_filename)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 1. Campo de URL
        layout.addWidget(QLabel("Dirección URL:"))
        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText("https://ejemplo.com/archivo.zip")
        self.url_input.textChanged.connect(self._on_url_changed)
        layout.addWidget(self.url_input)

        # 2. Nombre de archivo
        layout.addWidget(QLabel("Guardar como (Nombre de archivo):"))
        self.filename_input = QLineEdit(self)
        self.filename_input.textEdited.connect(self._on_filename_user_edited)
        self.filename_input.textChanged.connect(self._on_filename_changed)
        layout.addWidget(self.filename_input)

        # Etiqueta de información detectada (tamaño y servidor)
        self.lbl_server_info = QLabel("", self)
        self.lbl_server_info.setStyleSheet("color: #38bdf8; font-size: 11px;")
        layout.addWidget(self.lbl_server_info)

        # Barra de progreso anticipado en segundo plano
        self.progress_speculative = QProgressBar(self)
        self.progress_speculative.setFixedHeight(7)
        self.progress_speculative.setTextVisible(False)
        self.progress_speculative.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0ea5e9, stop:1 #38bdf8);
                border-radius: 2px;
            }
        """)
        self.progress_speculative.setVisible(False)
        layout.addWidget(self.progress_speculative)

        # 3. Carpeta de destino
        layout.addWidget(QLabel("Guardar en:"))
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit(self._save_path, self)
        self.path_input.setReadOnly(True)
        path_layout.addWidget(self.path_input)

        btn_browse = QPushButton("Examinar...", self)
        btn_browse.clicked.connect(self._browse_folder)
        path_layout.addWidget(btn_browse)
        layout.addLayout(path_layout)

        # 4. Cola y Categoría
        opts_layout = QHBoxLayout()

        # Selector de Colas con botón para crear nueva cola
        opts_layout.addWidget(QLabel("Cola:"))
        self.queue_combo = QComboBox(self)
        for q in self._existing_queues:
            self.queue_combo.addItem(q)
        opts_layout.addWidget(self.queue_combo, stretch=2)

        self.btn_new_queue = QPushButton("➕ Nueva...", self)
        self.btn_new_queue.setToolTip("Crear una nueva cola con número sugerido")
        self.btn_new_queue.clicked.connect(self._prompt_create_queue)
        opts_layout.addWidget(self.btn_new_queue)

        # Selector de Categoría Dinámico
        opts_layout.addWidget(QLabel("Categoría:"))
        self.category_combo = QComboBox(self)
        self._populate_categories()
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        opts_layout.addWidget(self.category_combo, stretch=2)

        layout.addLayout(opts_layout)

        # 5. Botones de Acción (Descargar Ahora vs Descargar Más Tarde)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_later = QPushButton("🕒 Descargar más tarde", self)
        self.btn_later.clicked.connect(self._on_download_later)
        btn_layout.addWidget(self.btn_later)

        self.btn_now = QPushButton("🚀 Descargar ahora", self)
        self.btn_now.setDefault(True)
        self.btn_now.clicked.connect(self._on_download_now)
        btn_layout.addWidget(self.btn_now)

        self.btn_cancel = QPushButton("Cancelar", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def _populate_categories(self):
        self.category_combo.clear()
        for cat in self.settings_manager.settings.categories:
            self.category_combo.addItem(f"{cat.icon} {cat.name}", cat)
        self.category_combo.addItem("📁 Otros", None)

    def _on_category_changed(self, index: int):
        cat_data = self.category_combo.currentData()
        if cat_data and hasattr(cat_data, "default_folder"):
            self._save_path = cat_data.default_folder
            self.path_input.setText(self._save_path)

    def _suggest_next_queue_name(self) -> str:
        """Calcula el nombre sugerido 'Cola #' con el siguiente número disponible."""
        used_numbers = set()
        pattern = re.compile(r"^Cola\s+(\d+)$", re.IGNORECASE)

        for i in range(self.queue_combo.count()):
            q_name = self.queue_combo.itemText(i).strip()
            match = pattern.match(q_name)
            if match:
                used_numbers.add(int(match.group(1)))

        next_num = 1
        while next_num in used_numbers:
            next_num += 1

        return f"Cola {next_num}"

    def _prompt_create_queue(self):
        suggested = self._suggest_next_queue_name()
        name, ok = QInputDialog.getText(
            self,
            "Nueva Cola de Descargas",
            "Introduce el nombre para la nueva cola:",
            text=suggested
        )
        if ok and name.strip():
            new_name = name.strip()
            for i in range(self.queue_combo.count()):
                if self.queue_combo.itemText(i).lower() == new_name.lower():
                    self.queue_combo.setCurrentIndex(i)
                    return

            self.queue_combo.addItem(new_name)
            self.queue_combo.setCurrentIndex(self.queue_combo.count() - 1)
            self._existing_queues.append(new_name)
            self.queue_created.emit(new_name)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de destino", self._save_path)
        if folder:
            self._save_path = folder
            self.path_input.setText(folder)

    def _on_filename_user_edited(self, text: str):
        self._user_edited_filename = True

    def _on_url_changed(self, text: str):
        url = text.strip()
        self._cleanup_speculative_download()

        if not url:
            self.lbl_server_info.setText("")
            self.progress_speculative.setVisible(False)
            return

        clean_url = url.split("?")[0].split("#")[0]
        raw_name = clean_url.rstrip("/").split("/")[-1]
        decoded_name = unquote(raw_name)
        sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', decoded_name).strip()

        if not self._user_edited_filename:
            if sanitized_name and "." in sanitized_name:
                self.filename_input.setText(sanitized_name)
            elif not self.filename_input.text():
                self.filename_input.setText("archivo_descarga")

        if url.startswith("http://") or url.startswith("https://"):
            speculative_enabled = getattr(self.settings_manager.settings, "speculative_download", True)
            lower_url = url.lower()
            is_stream = any(h in lower_url for h in ("youtube.com", "youtu.be", ".m3u8", ".mpd"))

            if speculative_enabled and not is_stream:
                self._start_speculative_download(url)
            else:
                self._start_probe_only(url)

    def _start_speculative_download(self, url: str):
        """Inicia la descarga anticipada en segundo plano en la carpeta temporal."""
        self.lbl_server_info.setText("⚡ Iniciando descarga anticipada en segundo plano...")
        self.progress_speculative.setValue(0)
        self.progress_speculative.setVisible(True)

        self._temp_id = str(uuid.uuid4())
        self._temp_folder = os.path.join(str(TEMP_DOWNLOAD_DIR), self._temp_id)
        try:
            os.makedirs(self._temp_folder, exist_ok=True)
        except Exception as e:
            print(f"[Speculative] No se pudo crear directorio temporal: {e}")
            self._start_probe_only(url)
            return

        initial_name = self.filename_input.text().strip() or "descarga.tmp"
        self._speculative_item = DownloadItem(
            id=self._temp_id,
            url=url,
            filename=initial_name,
            save_path=self._temp_folder,
            cookies=self._cookies or None,
            referer=self._referer or None,
            user_agent=self._user_agent or None,
            has_custom_filename=self._user_edited_filename
        )

        self._speculative_task = DownloadTask(self._speculative_item, parent=self)
        self._speculative_task.progress_updated.connect(self._on_speculative_progress)
        self._speculative_task.task_finished.connect(self._on_speculative_finished)
        self._speculative_task.task_error.connect(self._on_speculative_error)
        self._speculative_task.start()

    def _on_speculative_progress(self, item: DownloadItem):
        if item.filename and not self._user_edited_filename and item.filename != self.filename_input.text():
            self.filename_input.setText(item.filename)

        if item.total_size > 0:
            percent = int((item.downloaded_size / item.total_size) * 100)
            self.progress_speculative.setValue(percent)
            self.progress_speculative.setVisible(True)
            speed_str = DownloadItem._format_bytes(int(item.speed)) + "/s"
            down_str = DownloadItem._format_bytes(item.downloaded_size)
            tot_str = DownloadItem._format_bytes(item.total_size)
            self.lbl_server_info.setText(
                f"⚡ Descargando anticipadamente: {percent}% ({speed_str}) — {down_str} de {tot_str}"
            )
        elif item.downloaded_size > 0:
            down_str = DownloadItem._format_bytes(item.downloaded_size)
            speed_str = DownloadItem._format_bytes(int(item.speed)) + "/s"
            self.lbl_server_info.setText(f"⚡ Descargando anticipadamente: {down_str} ({speed_str})")

    def _on_speculative_finished(self, task_id: str):
        self.speculative_already_completed = True
        self.progress_speculative.setValue(100)
        self.progress_speculative.setVisible(True)
        tot_bytes = self._speculative_item.total_size if (self._speculative_item and self._speculative_item.total_size > 0) else (self._speculative_item.downloaded_size if self._speculative_item else 0)
        tot_str = DownloadItem._format_bytes(tot_bytes)
        self.lbl_server_info.setText(f"✅ ¡Descarga completada en segundo plano! ({tot_str}) — Listo para guardar")

    def _on_speculative_error(self, task_id: str, err: str):
        self.lbl_server_info.setText(f"⚠️ Nota de conexión: {err}")

    def _start_probe_only(self, url: str):
        self.lbl_server_info.setText("🔍 Consultando servidor...")
        self.progress_speculative.setVisible(False)
        if self._probe_worker and self._probe_worker.isRunning():
            self._probe_worker.terminate()

        self._probe_worker = UrlProbeWorker(
            url=url,
            cookies=self._cookies,
            referer=self._referer,
            user_agent=self._user_agent,
            parent=self
        )
        self._probe_worker.probe_finished.connect(self._on_probe_finished)
        self._probe_worker.start()

    def _cleanup_speculative_download(self):
        """Detiene y elimina cualquier tarea y archivo temporal de descarga anticipada."""
        if self._speculative_task:
            try:
                self._speculative_task.stop()
            except Exception:
                pass
            self._speculative_task = None

        if self._temp_folder and os.path.exists(self._temp_folder):
            try:
                shutil.rmtree(self._temp_folder, ignore_errors=True)
            except Exception:
                pass
            self._temp_folder = None
        self._speculative_item = None
        self.speculative_already_completed = False
        if hasattr(self, "progress_speculative"):
            self.progress_speculative.setVisible(False)

    def reject(self):
        self._cleanup_speculative_download()
        if self._probe_worker and self._probe_worker.isRunning():
            self._probe_worker.terminate()
        super().reject()

    def closeEvent(self, event):
        self._cleanup_speculative_download()
        if self._probe_worker and self._probe_worker.isRunning():
            self._probe_worker.terminate()
        super().closeEvent(event)

    def _on_probe_finished(self, real_filename: str, total_size: int):
        info_parts = []
        if total_size > 0:
            info_parts.append(f"Tamaño: {DownloadItem._format_bytes(total_size)}")

        if real_filename and not self._user_edited_filename:
            self.filename_input.setText(real_filename)
            info_parts.append(f"Nombre verificado por el servidor")

        if info_parts:
            self.lbl_server_info.setText(" | ".join(info_parts))
        else:
            self.lbl_server_info.setText("")

    def _on_filename_changed(self, filename: str):
        if not filename:
            return
        cat_name, folder = self.settings_manager.get_category_and_folder_for_file(filename)
        for i in range(self.category_combo.count()):
            if self.category_combo.itemText(i).lower() == cat_name.lower():
                self.category_combo.setCurrentIndex(i)
                break
        self._save_path = folder
        self.path_input.setText(folder)

    def _create_item(self, immediate: bool):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "URL requerida", "Por favor ingresa una URL válida.")
            return

        final_filename = self.filename_input.text().strip() or "descarga"
        final_save_path = self._save_path
        os.makedirs(final_save_path, exist_ok=True)

        cat_data = self.category_combo.currentData()
        queue_name = self.queue_combo.currentText()
        if cat_data and hasattr(cat_data, "name"):
            category_name = cat_data.name
        else:
            category_name = "Otros"

        try:
            cat_val = DownloadCategory(category_name)
        except ValueError:
            cat_val = category_name

        dest_file = os.path.join(final_save_path, final_filename)
        dest_meta = dest_file + ".brodownloads"

        # 1. Si la descarga anticipada ya se completó al 100%
        if self._speculative_task and self.speculative_already_completed and self._temp_folder:
            temp_file = os.path.join(self._temp_folder, self._speculative_item.filename)
            if not os.path.exists(temp_file):
                candidates = [f for f in os.listdir(self._temp_folder) if not f.endswith(".brodownloads")]
                if candidates:
                    temp_file = os.path.join(self._temp_folder, candidates[0])

            if os.path.exists(temp_file):
                try:
                    shutil.move(temp_file, dest_file)
                except Exception as e:
                    print(f"[Speculative] Error moviendo archivo completo: {e}")

            shutil.rmtree(self._temp_folder, ignore_errors=True)
            self._temp_folder = None
            self._speculative_task = None

            total_size = os.path.getsize(dest_file) if os.path.exists(dest_file) else (self._speculative_item.total_size if self._speculative_item else 0)

            self.created_item = DownloadItem(
                id=self._speculative_item.id if self._speculative_item else str(uuid.uuid4()),
                url=url,
                filename=final_filename,
                save_path=final_save_path,
                total_size=total_size,
                downloaded_size=total_size,
                speed=0.0,
                status=DownloadStatus.COMPLETED,
                category=cat_val,
                queue_name=queue_name,
                has_custom_filename=self._user_edited_filename,
                cookies=self._cookies or None,
                referer=self._referer or None,
                user_agent=self._user_agent or None
            )
            self.speculative_already_completed = True
            self.download_immediately = immediate
            self.accept()
            return

        # 2. Si la descarga anticipada está en progreso (parcial)
        if self._speculative_task and self._temp_folder and os.path.exists(self._temp_folder):
            self._speculative_task.pause()

            temp_file = os.path.join(self._temp_folder, self._speculative_item.filename)
            temp_meta = temp_file + ".brodownloads"

            if not os.path.exists(temp_file):
                candidates = [f for f in os.listdir(self._temp_folder) if not f.endswith(".brodownloads")]
                if candidates:
                    temp_file = os.path.join(self._temp_folder, candidates[0])
                    temp_meta = temp_file + ".brodownloads"

            if os.path.exists(temp_file):
                try:
                    shutil.move(temp_file, dest_file)
                except Exception as e:
                    print(f"[Speculative] Error moviendo archivo parcial: {e}")

            if os.path.exists(temp_meta):
                try:
                    shutil.move(temp_meta, dest_meta)
                except Exception as e:
                    print(f"[Speculative] Error moviendo metadatos parciales: {e}")

            shutil.rmtree(self._temp_folder, ignore_errors=True)
            self._temp_folder = None
            self._speculative_task = None

            downloaded_size = self._speculative_item.downloaded_size if self._speculative_item else 0
            total_size = self._speculative_item.total_size if self._speculative_item else 0

            self.created_item = DownloadItem(
                id=self._speculative_item.id if self._speculative_item else str(uuid.uuid4()),
                url=url,
                filename=final_filename,
                save_path=final_save_path,
                total_size=total_size,
                downloaded_size=downloaded_size,
                status=DownloadStatus.QUEUED if immediate else DownloadStatus.PAUSED,
                category=cat_val,
                queue_name=queue_name,
                has_custom_filename=self._user_edited_filename,
                cookies=self._cookies or None,
                referer=self._referer or None,
                user_agent=self._user_agent or None
            )
            self.speculative_already_completed = False
            self.download_immediately = immediate
            self.accept()
            return

        # 3. Descarga normal sin anticipación
        self._cleanup_speculative_download()
        self.created_item = DownloadItem(
            id=str(uuid.uuid4()),
            url=url,
            filename=final_filename,
            save_path=final_save_path,
            status=DownloadStatus.QUEUED if immediate else DownloadStatus.PAUSED,
            category=cat_val,
            queue_name=queue_name,
            has_custom_filename=self._user_edited_filename,
            cookies=self._cookies or None,
            referer=self._referer or None,
            user_agent=self._user_agent or None
        )
        self.speculative_already_completed = False
        self.download_immediately = immediate
        self.accept()

    def _on_download_now(self):
        self._create_item(immediate=True)

    def _on_download_later(self):
        self._create_item(immediate=False)
