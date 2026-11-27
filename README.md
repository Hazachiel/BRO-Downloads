# BRO-Downloads ⚡

> *Parte de la suite **BroTools** — utilidades nativas, rápidas y sin vueltas.*

¿Cansado de gestores de descargas pesados, llenos de publicidad, suscripciones o que te comen medio gigabyte de RAM solo por estar abiertos? 
**BRO-Downloads** nació para resolver eso: un gestor de descargas gratuito, liviano y directo al grano para Windows, pensado para que tengas el control total de tus descargas de archivos y multimedia.

### 🤝 ¿Qué te ofrece, bro?

* **Descargas a máxima velocidad:** Divide los archivos en múltiples conexiones concurrentes para exprimir tu ancho de banda sin ahogar el sistema.
* **Captura videos en páginas web:** Añade un botón de "Descargar video" a todos los videos que veas en internet.
* **Capturador automático desde el navegador:** Incluye extensión para Chrome, Edge y Brave (Manifest V3) que intercepta tus descargas y te las manda directo a la app.
* **Pausa, reanudación y rescate de enlaces:** Si se corta internet o se vence el link de descarga (típico de servidores como MediaFire o Drive), podés actualizar la URL y seguir bajando desde donde quedaste sin perder ni un byte.
* **Colas inteligentes y horarios:** Armá tus listas de descarga, limitá cuántas bajan por servidor y programá que la PC se suspenda o apague sola cuando termine todo.
* **Interfaz limpia y oscura:** Estética moderna estilo Windows 11 Fluent UI que no te quema los ojos ni te llena la pantalla de botones inútiles.

---

## 🛠️ Instalación y Puesta en Marcha

### 1. Ejecutar la aplicación
Cloná el repositorio, instalá las dependencias y lanzá el programa:

```powershell
git clone https://github.com/Hazachiel/BRO-Downloads.git
cd BRO-Downloads
pip install -r requirements.txt
python main.py
```

### 2. Conectar el navegador (Opcional, pero recomendado)
* Ejecutá install_native_host.bat para registrar el puente de comunicación en Windows.
* Abrí tu navegador Chromium (Chrome, Edge, Brave) y entrá a chrome://extensions/.
* Activá el Modo de desarrollador arriba a la derecha.
* Hacé clic en Cargar descomprimida y seleccioná la carpeta extension/ del proyecto.

---

## 🚀 Arquitectura y Organización del Proyecto

El código está completamente desacoplado entre modelos de datos, lógica central persistente y capa de presentación visual:

```text
BRO-Downloads/
│
├── config/
│   ├── default_settings.json       # Configuración inicial
├── core/                           # Motor y Gestores de Negocio
│   ├── constants.py                # Parámetros y valones iniciales de la app
│   ├── download_engine.py          # Orquestador del ciclo de vida y colas concurrentes
│   ├── download_task.py            # Tarea individual, multi-hilos y detección de streaming
│   ├── download_worker.py          # Worker de descarga segmentada con HTTP Range y seek
│   ├── stream_worker.py            # Ensamblado de HLS (.m3u8), DASH y plataformas de video
│   ├── media_tools.py              # Detección y descargador automático de FFmpeg portátil
│   ├── download_storage.py         # Persistencia de descargas en ~/.brodownloads/downloads.json
│   ├── settings_manager.py         # Configuración centralizada JSON (~/.brodownloads/settings.json)
│   ├── queue_manager.py            # Gestor de Colas, Horarios, Prioridad y Monitoreo de Red
│   ├── api_server.py               # Micro-servidor HTTP local para navegadores
│   └── __init__.py
│
├── models/                         # Capa de datos y Modelos Qt
│   ├── download_item.py            # Objeto de datos puro (DownloadItem, estados, dominios y categorías)
│   ├── table_model.py              # QAbstractTableModel (renderizado virtual de bajo consumo de CPU/RAM)
│   ├── filter_proxy_model.py       # QSortFilterProxyModel (filtros y ordenamiento en tiempo real)
│   └── __init__.py
│
├── ui/                             # Capa visual (PySide6)
│   ├── styles.py                   # Tema oscuro moderno estilo Windows 11 Fluent UI
│   ├── main_window.py              # Ventana principal que orquesta todos los módulos
│   ├── components/                 # Widgets modulares y reutilizables
│   │   ├── menu_bar.py             # Menú superior
│   │   ├── tool_bar.py             # Barra rápida con botones de acción directa
│   │   ├── sidebar.py              # Árbol lateral izquierdo (Categorías, Tipos de archivo y Colas)
│   │   ├── filter_bar.py           # Campo de búsqueda en vivo y selector de estado
│   │   ├── download_table.py       # Tabla central con menú contextual (clic derecho)
│   │   └── progress_delegate.py    # Dibujado nativo de la barra de progreso en celda
│   ├── dialogs/
│   │   ├── add_download_dialog.py  # Diálogo emergente para ingresar URL
│   │   ├── options_dialog.py       # Ventana de Opciones y Preferencias (5 pestañas)
│   │   ├── scheduler_dialog.py     # Programador de Descargas y Gestor de Colas
│   │   ├── shutdown_countdown_dialog.py # Cuenta regresiva para apagar o suspender el equipo
│   │   └── __init__.py
│   └── __init__.py
│
├── native_host/                    # Puente Native Messaging (Windows / Chromium)
│   ├── native_host.py              # Host nativo stdio con framing de 4 bytes little-endian
│   ├── install_host.py             # Instalador en Registro de Windows (HKCU) para Chrome/Edge/Brave
│   ├── uninstall_host.py           # Limpiador de registro
│   └── com.brodownloads.host.json # Manifiesto del Host Nativo
│
├── extension/                      # Extensión Chromium MV3 para navegadores
│   ├── manifest.json               # Configuración Manifest V3 con ID determinista fijo
│   ├── background.js               # Service Worker interceptor de descargas
│   ├── popup.html / popup.js       # Interfaz dark Fluent con estado de Native Messaging
│   └── icons/                      # Íconos PNG de la extensión
│
├── install_native_host.bat         # Instalador de 1-clic para registrar el puente en Windows
├── requirements.txt                # Dependencias (PySide6, requests)
├── README.md                       # Documentación del proyecto
└── main.py                         # Punto de entrada de la aplicación
```

---

## 🌟 Características Implementadas

### 1. Interfaz Gráfica en Modo Oscuro Fluent
* Distribución estándar: Menú superior, barra rápida de acciones, panel lateral tipo árbol con colas y categorías dinámicas, barra de búsqueda en vivo y tabla de alto rendimiento.
* Barra de progreso nativa dibujada por celda con degradados de color según estado (azul descargando, verde completado, naranja pausado, rojo error).
* Búsqueda por texto y filtrado instantáneo por estado y tipo de archivo con `QSortFilterProxyModel`.

### 2. Ventana de Opciones y Preferencias (5 Secciones)
* **General:** Inicio con Windows (`winreg` sin consola), iniciar minimizado en bandeja del sistema, integración de navegadores y carpeta predeterminada.
* **Tipos y Exclusiones:** Extensiones capturadas automáticamente y reglas de exclusión con comodines `*` (wildcards).
* **Gestor de Categorías:** Creación de categorías personalizadas, extensiones asociadas y asignación de carpetas de descarga dedicadas.
* **Opciones de Descarga:** Notificaciones del sistema, sonido y tratamiento inteligente de duplicados (detectar archivo completo vs reanudar).
* **Gestor de Conexiones:** Selector de conexiones concurrentes por descarga (1 a 32 con alerta si > 16) y tabla de límites por servidor.

### 3. Programador de Descargas y Gestor de Colas (Scheduler)
* **Panel lateral de colas:** Permite seleccionar y configurar cada cola de forma independiente.
* **Horarios y Automatización:**
  * Inicio y detención programados por hora (`HH:mm`).
  * Opción de esperar a que terminen las descargas activas antes de detener la cola.
  * Automatización al finalizar: Salir, Suspender o Apagar el equipo con cuenta regresiva sonora de 30 segundos y botón para cancelar.
* **Resiliencia de Red y Enlaces Expirados:**
  * Comprobación rápida del estado de conexión a Internet para no agotar reintentos si la red se corta.
  * Reanudación automática al recuperar la conexión.
  * Desplazamiento al final de la cola en modo *"Requiere actualización"* si el enlace o token de descarga expira, con opción de renovar la URL (`RefreshUrlDialog`) sin perder el progreso.
* **Doble Limitador de Concurrencia:**
  * Descargas simultáneas en la cola (ej. 2 a la vez).
  * Descargas simultáneas por servidor (ej. máximo 1 por servidor) para evitar saturación de hosts como MediaFire o Google Drive.
* **Orden de Prioridad Independiente:**
  * Reordenamiento de prioridad mediante Drag & Drop o botones `[🔼 Subir]` y `[🔽 Bajar]`. El orden de procesamiento es independiente de la vista de la tabla principal.

