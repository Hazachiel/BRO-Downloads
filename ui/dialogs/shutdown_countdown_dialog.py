import os
import subprocess
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, QTimer


class ShutdownCountdownDialog(QDialog):
    """
    Diálogo con cuenta regresiva sonora y visible de 30 segundos
    antes de apagar o suspender el equipo, permitiendo al usuario cancelar la acción.
    """

    def __init__(self, action: str = "shutdown", countdown_seconds: int = 30, parent=None):
        super().__init__(parent)
        self.action = action
        self.remaining = countdown_seconds

        action_title = "Apagado del Sistema" if action == "shutdown" else "Suspensión del Sistema"
        self.setWindowTitle(f"BRO-Downloads - {action_title}")
        self.resize(460, 200)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        self._init_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        action_name = "apagar" if self.action == "shutdown" else "suspender"
        self.lbl_info = QLabel(
            f"<h3>Todas las descargas de la cola han finalizado.</h3>"
            f"<p>El equipo se va a <b>{action_name}</b> en:</p>"
        )
        layout.addWidget(self.lbl_info)

        self.lbl_countdown = QLabel(f"<h1>{self.remaining} segundos</h1>")
        self.lbl_countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_countdown.setStyleSheet("color: #ef4444; font-size: 26px; font-weight: bold;")
        layout.addWidget(self.lbl_countdown)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("🛑 Cancelar Apagado", self)
        self.btn_cancel.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold; padding: 10px 20px;")
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_now = QPushButton("Apagar Ahora", self)
        self.btn_now.clicked.connect(self._execute_action)
        btn_layout.addWidget(self.btn_now)

        layout.addLayout(btn_layout)

    def _tick(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self._timer.stop()
            self._execute_action()
        else:
            self.lbl_countdown.setText(f"<h1>{self.remaining} segundos</h1>")

    def _on_cancel(self):
        self._timer.stop()
        self.reject()

    def _execute_action(self):
        self._timer.stop()
        self.accept()
        if self.action == "shutdown":
            if os.name == "nt":
                subprocess.run(["shutdown", "/s", "/t", "0"])
            else:
                subprocess.run(["shutdown", "-h", "now"])
        elif self.action == "sleep":
            if os.name == "nt":
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            else:
                subprocess.run(["systemctl", "suspend"])
