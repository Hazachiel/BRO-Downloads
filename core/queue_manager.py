import os
import sys
import json
import socket
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, Signal, QTimer


@dataclass
class QueueScheduleConfig:
    """Configuración integral de programación, concurrencia y prioridad para una cola."""
    queue_name: str
    # 1. Limitadores de Concurrencia
    max_concurrent_downloads: int = 2       # Límite simultáneo en esta cola
    max_concurrent_per_server: int = 1      # Límite simultáneo por servidor / host

    # 2. Automatización al Finalizar
    action_on_finish: str = "none"          # "none", "exit_app", "sleep", "shutdown"
    shutdown_countdown_seconds: int = 30

    # 3. Horarios de Ejecución
    enable_start_time: bool = False
    start_time: str = "02:00"
    enable_stop_time: bool = False
    stop_time: str = "08:00"
    stop_behavior: str = "wait_active"      # "wait_active" (esperar a que terminen), "pause_immediate" (pausar ya)
    days_of_week: List[str] = field(default_factory=lambda: [
        "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"
    ])

    # 4. Conectividad y Reintentos
    check_internet_before_retry: bool = True
    internet_check_interval_seconds: int = 30
    max_retries: int = 3
    retry_interval_seconds: int = 30
    move_failed_to_end_on_auth_error: bool = True  # Mover al final en estado 'Requiere actualización'

    # 5. Prioridad de Descargas (IDs ordenados FIFO / prioridad)
    ordered_download_ids: List[str] = field(default_factory=list)


def check_internet_connectivity(host: str = "1.1.1.1", port: int = 53, timeout: float = 2.0) -> bool:
    """
    Comprueba de forma ultrarrápida si hay conexión real a Internet
    abriendo un socket efímero al DNS público de Cloudflare o Google.
    No descarga datos ni satura la red.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except OSError:
        return False


class QueueManager(QObject):
    """
    Administrador central de Colas y Programación (Scheduler).
    Controla los límites simultáneos (cola + por servidor), reordenamiento de prioridad,
    monitoreo de horarios y reanudación automática tras pérdida de conexión.
    """

    _instance: Optional["QueueManager"] = None
    queue_started = Signal(str)
    queue_stopped = Signal(str)
    internet_status_changed = Signal(bool)

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_dir: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return
        super().__init__()

        self._config_dir = Path(config_dir) if config_dir else Path.home() / ".brodownloads"
        self._queues_file = self._config_dir / "queues.json"
        self.queues: Dict[str, QueueScheduleConfig] = {}

        self.has_internet: bool = True
        self._active_queues: set[str] = set()

        self.load()

        # Timer para verificación periódica de conexión a internet
        self._internet_timer = QTimer(self)
        self._internet_timer.timeout.connect(self._check_internet_tick)
        self._internet_timer.start(15000)  # Cada 15 segundos

        self._initialized = True

    def get_or_create_queue(self, queue_name: str) -> QueueScheduleConfig:
        """Obtiene la configuración de la cola o crea una por defecto."""
        clean_name = queue_name.strip()
        if clean_name not in self.queues:
            self.queues[clean_name] = QueueScheduleConfig(queue_name=clean_name)
            self.save()
        return self.queues[clean_name]

    def remove_queue(self, queue_name: str):
        """Elimina la configuración de una cola."""
        if queue_name in self.queues and queue_name != "Cola Principal":
            del self.queues[queue_name]
            self.save()

    def load(self):
        """Carga las configuraciones de colas desde JSON."""
        # Asegurar cola principal por defecto
        self.queues = {
            "Cola Principal": QueueScheduleConfig(queue_name="Cola Principal")
        }

        if not self._queues_file.exists():
            self.save()
            return

        try:
            with open(self._queues_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for name, q_data in data.items():
                self.queues[name] = QueueScheduleConfig(**q_data)
        except Exception as e:
            print(f"[QueueManager] Error al cargar colas: {e}. Usando valores base.")
            self.save()

    def save(self):
        """Persiste las configuraciones de colas a disco."""
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            data = {name: asdict(cfg) for name, cfg in self.queues.items()}
            with open(self._queues_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[QueueManager] Error al guardar colas: {e}")

    def _check_internet_tick(self):
        """Monitorea el estado de la conexión a internet."""
        online = check_internet_connectivity()
        if online != self.has_internet:
            self.has_internet = online
            self.internet_status_changed.emit(online)

    def is_queue_running(self, queue_name: str) -> bool:
        return queue_name in self._active_queues

    def start_queue(self, queue_name: str):
        self._active_queues.add(queue_name)
        self.queue_started.emit(queue_name)

    def stop_queue(self, queue_name: str):
        if queue_name in self._active_queues:
            self._active_queues.remove(queue_name)
            self.queue_stopped.emit(queue_name)
