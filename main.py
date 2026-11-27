import sys
import json
import base64
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from ui.main_window import MainWindow


def main():
    # Asegurar renderizado correcto en pantallas de alta resolución (High DPI)
    app = QApplication(sys.argv)
    app.setApplicationName("BRO-Downloads")
    app.setApplicationDisplayName("BRO-Downloads")
    app.setOrganizationName("BRO-Team")

    window = MainWindow()
    window.show()

    # Procesar descarga si fue invocado desde Native Messaging
    if "--add-download" in sys.argv:
        try:
            idx = sys.argv.index("--add-download")
            if idx + 1 < len(sys.argv):
                raw_payload = sys.argv[idx + 1]
                # Decodificar payload (soporta base64 o json directo)
                if raw_payload.startswith("{"):
                    data = json.loads(raw_payload)
                else:
                    data = json.loads(base64.b64decode(raw_payload.encode("utf-8")).decode("utf-8"))
                QTimer.singleShot(250, lambda: window._on_browser_download_received(data))
        except Exception as e:
            print(f"[Main] Error al procesar --add-download: {e}")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
