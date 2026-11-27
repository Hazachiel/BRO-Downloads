import sys
from pathlib import Path


def _detect_app_dir() -> Path:
    """
    Detecta la raíz del proyecto BRO-Downloads de forma dinámica y portable.
    - Si la aplicación está compilada (ej. PyInstaller o cx_Freeze), utiliza la ruta de sys.executable.
    - Si se ejecuta como script (.py), resuelve la raíz a partir de la ubicación de este archivo.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # Este archivo se encuentra en <APP_DIR>/core/constants.py
    return Path(__file__).resolve().parent.parent


def _detect_temp_dir() -> Path:
    """
    Obtiene el directorio de descargas temporales.
    Usa ~/.brodownloads/temp por defecto y recurre al directorio temporal
    del sistema si no se cuenta con permisos de escritura.
    """
    import tempfile
    primary = Path.home() / ".brodownloads" / "temp"
    try:
        primary.mkdir(parents=True, exist_ok=True)
        return primary
    except Exception:
        fallback = Path(tempfile.gettempdir()) / "brodownloads" / "temp"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


# =========================================================================
# RUTAS BASE GLOBALES DEL PROYECTO
# =========================================================================
APP_DIR: Path = _detect_app_dir()
CONFIG_DIR: Path = APP_DIR / "config"
DEFAULT_SETTINGS_FILE: Path = CONFIG_DIR / "default_settings.json"
EXTENSION_DIR: Path = APP_DIR / "extension"
NATIVE_HOST_DIR: Path = APP_DIR / "native_host"
MAIN_SCRIPT: Path = APP_DIR / "main.py"
TEMP_DOWNLOAD_DIR: Path = _detect_temp_dir()
