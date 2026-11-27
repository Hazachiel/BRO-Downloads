import os
import sys
import json
import secrets
import fnmatch
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from core.constants import MAIN_SCRIPT, DEFAULT_SETTINGS_FILE

# En Windows importamos winreg de forma segura
try:
    import winreg
    IS_WINDOWS = True
except ImportError:
    IS_WINDOWS = False


@dataclass
class CategoryRule:
    """Regla de categoría con extensiones asociadas, carpeta de descarga dedicada e icono."""
    name: str
    extensions: List[str]
    default_folder: str
    icon: str = "📁"

    def matches_extension(self, ext: str) -> bool:
        clean_ext = ext.lstrip(".").lower()
        return clean_ext in [e.lower() for e in self.extensions]


@dataclass
class AppSettings:
    """Estructura completa de configuración de la aplicación."""
    # 1. General & Integración
    start_with_windows: bool = False
    start_minimized: bool = False
    browser_integration: bool = True
    default_save_path: str = field(default_factory=lambda: str(Path.home() / "Downloads"))
    ffmpeg_path: Optional[str] = None   # Ruta personalizada o portátil de FFmpeg

    # 2. Servidor Local API para Extensión de Navegador
    server_port: int = 9876
    server_token: str = ""
    server_enabled: bool = True

    # 3. Tipos de archivo & Exclusiones
    monitored_extensions: List[str] = field(default_factory=lambda: [
        "zip", "rar", "7z", "tar", "gz", "iso", "exe", "msi",
        "mp4", "mkv", "avi", "mov", "mp3", "flac", "pdf", "docx"
    ])
    excluded_sites: List[str] = field(default_factory=lambda: [
        "*.banco*.com*",
        "*login*",
        "*signin*",
        "*.gov.*"
    ])

    # 4. Categorías dinámicas
    categories: List[CategoryRule] = field(default_factory=lambda: [
        CategoryRule(
            name="Comprimidos",
            extensions=["zip", "rar", "7z", "tar", "gz", "bz2", "iso"],
            default_folder=str(Path.home() / "Downloads" / "Comprimidos"),
            icon="🗜️"
        ),
        CategoryRule(
            name="Documentos",
            extensions=["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "epub"],
            default_folder=str(Path.home() / "Downloads" / "Documentos"),
            icon="📄"
        ),
        CategoryRule(
            name="Música",
            extensions=["mp3", "wav", "flac", "aac", "ogg", "m4a"],
            default_folder=str(Path.home() / "Downloads" / "Música"),
            icon="🎵"
        ),
        CategoryRule(
            name="Programas",
            extensions=["exe", "msi", "dmg", "pkg", "deb", "rpm", "appimage", "apk"],
            default_folder=str(Path.home() / "Downloads" / "Programas"),
            icon="📦"
        ),
        CategoryRule(
            name="Video",
            extensions=["mp4", "mkv", "avi", "mov", "webm", "flv"],
            default_folder=str(Path.home() / "Downloads" / "Video"),
            icon="🎬"
        ),
    ])

    # 5. Opciones de Descarga y Duplicados
    notify_on_start: bool = False
    notify_on_finish: bool = True
    play_sound_on_finish: bool = False
    speculative_download: bool = True   # Descarga anticipada en segundo plano al capturar enlace
    duplicate_action: str = "smart"     # "smart", "numbered", "overwrite"

    # 6. Gestor de Conexiones
    default_connections: int = 8
    max_global_connections: int = 32
    global_speed_limit_kb: int = 0      # 0 = sin límite
    domain_limits: Dict[str, int] = field(default_factory=lambda: {
        "rapidgator.net": 1,
        "mega.nz": 4,
        "drive.google.com": 4
    })

    # 7. Personalización de Columnas de Tablas
    main_table_visible_columns: List[str] = field(default_factory=lambda: [
        "Nombre de archivo", "Cola", "Estado", "Velocidad"
    ])
    main_table_column_widths: Dict[str, int] = field(default_factory=lambda: {
        "Nombre de archivo": 300,
        "Tamaño": 100,
        "Estado": 110,
        "Progreso": 150,
        "Velocidad": 110,
        "Tiempo Restante": 120,
        "Cola": 130,
        "Fecha": 140
    })
    scheduler_table_visible_columns: List[str] = field(default_factory=lambda: [
        "Prioridad", "Nombre de Archivo", "Servidor", "Tamaño", "Estado"
    ])
    scheduler_table_column_widths: Dict[str, int] = field(default_factory=lambda: {
        "Prioridad": 75,
        "Nombre de Archivo": 300,
        "Servidor": 130,
        "Tamaño": 100,
        "Estado": 110
    })


class SettingsManager:
    """
    Gestor centralizado de configuración (Singleton).
    Carga, persiste y aplica la configuración de BRO-Downloads.
    """

    _instance: Optional["SettingsManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_dir: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return

        self._config_dir = Path(config_dir) if config_dir else Path.home() / ".brodownloads"
        self._config_file = self._config_dir / "settings.json"
        self.settings: AppSettings = AppSettings()

        self.load()
        self._initialized = True

    def _load_from_defaults(self) -> AppSettings:
        """Carga la configuración base desde config/default_settings.json expandiendo rutas."""
        if DEFAULT_SETTINGS_FILE.exists():
            try:
                with open(DEFAULT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Expandir rutas relativas al usuario (~/Downloads)
                if "default_save_path" in data and data["default_save_path"]:
                    data["default_save_path"] = os.path.expanduser(data["default_save_path"])

                categories_data = data.pop("categories", [])
                categories = []
                for c in categories_data:
                    folder = c.get("default_folder", "~/Downloads")
                    categories.append(CategoryRule(
                        name=c["name"],
                        extensions=c.get("extensions", []),
                        default_folder=os.path.expanduser(folder),
                        icon=c.get("icon", "📁")
                    ))
                return AppSettings(**data, categories=categories)
            except Exception as e:
                print(f"[SettingsManager] Error al leer {DEFAULT_SETTINGS_FILE}: {e}")

        # Respaldo secundario si default_settings.json no estuviera disponible
        return AppSettings()

    def load(self):
        """
        Carga la configuración. Si ~/.brodownloads/settings.json no existe,
        se crea a partir de config/default_settings.json, se genera el server_token
        y se guarda inmediatamente como archivo de usuario.
        """
        if not self._config_file.exists():
            print("[SettingsManager] Archivo de usuario no encontrado. Inicializando con config/default_settings.json...")
            self.settings = self._load_from_defaults()
            self.settings.server_token = secrets.token_hex(16)
            self.save()
            return

        try:
            with open(self._config_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Reconstruir categorías como objetos CategoryRule
            categories_data = data.pop("categories", [])
            categories = []
            for c in categories_data:
                categories.append(CategoryRule(
                    name=c["name"],
                    extensions=c.get("extensions", []),
                    default_folder=os.path.expanduser(c.get("default_folder", str(Path.home() / "Downloads"))),
                    icon=c.get("icon", "📁")
                ))

            self.settings = AppSettings(**data, categories=categories)

            # Si no tenía token generado, crear uno
            if not self.settings.server_token:
                self.settings.server_token = secrets.token_hex(16)
                self.save()

        except Exception as e:
            print(f"[SettingsManager] Error al cargar configuración: {e}. Usando valores por defecto.")
            self.settings = self._load_from_defaults()
            self.settings.server_token = secrets.token_hex(16)
            self.save()

    def reset_to_defaults(self):
        """Restaura la configuración a los valores de fábrica desde config/default_settings.json."""
        current_token = self.settings.server_token
        self.settings = self._load_from_defaults()
        self.settings.server_token = current_token or secrets.token_hex(16)
        self.save()

    def save(self):
        """Persiste la configuración actual a disco."""
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            data = asdict(self.settings)
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[SettingsManager] Error al guardar configuración: {e}")

    # --- Métodos de Ayuda de Lógica de Negocio ---

    def is_site_excluded(self, url: str) -> bool:
        """Determina si una URL coincide con alguno de los patrones wildcards excluidos."""
        clean_url = url.lower()
        for pattern in self.settings.excluded_sites:
            if fnmatch.fnmatch(clean_url, pattern.lower()):
                return True
        return False

    def is_extension_monitored(self, filename_or_url: str) -> bool:
        """Determina si la extensión está en la lista de captura automática."""
        clean = filename_or_url.split("?")[0].split("#")[0].rstrip("/")
        if "." in clean:
            ext = clean.split(".")[-1].lower()
            return ext in [e.lower() for e in self.settings.monitored_extensions]
        return False

    def get_category_and_folder_for_file(self, filename: str) -> tuple[Optional[str], str]:
        """
        Retorna (nombre_categoria, carpeta_destino) para un archivo dado.
        Si coincide con una categoría personalizada, la devuelve y asegura que la carpeta exista.
        """
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        for cat in self.settings.categories:
            if cat.matches_extension(ext):
                folder = cat.default_folder
                try:
                    Path(folder).mkdir(parents=True, exist_ok=True)
                except Exception:
                    folder = self.settings.default_save_path
                return cat.name, folder

        return "Otros", self.settings.default_save_path

    def get_connections_for_url(self, url: str) -> int:
        """Retorna el número de conexiones permitidas para un dominio o el valor por defecto."""
        clean_url = url.lower()
        for domain, limit in self.settings.domain_limits.items():
            if domain.lower() in clean_url:
                return limit
        return self.settings.default_connections

    # --- Integración con Windows (Registro) ---

    def apply_windows_startup(self, enable: bool) -> bool:
        """Agrega o quita la clave de inicio automático en el registro de Windows."""
        if not IS_WINDOWS:
            return False

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "BRO-Downloads"

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if enable:
                if getattr(sys, "frozen", False):
                    cmd = f'"{sys.executable}" --minimized'
                else:
                    python_exe = sys.executable
                    if "python.exe" in python_exe.lower():
                        pythonw = python_exe.lower().replace("python.exe", "pythonw.exe")
                        if os.path.exists(pythonw):
                            python_exe = pythonw
                    cmd = f'"{python_exe}" "{MAIN_SCRIPT}" --minimized'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            return True
        except Exception as e:
            print(f"[SettingsManager] Error configurando inicio en Windows: {e}")
            return False
