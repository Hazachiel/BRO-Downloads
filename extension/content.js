// content.js - Inyector del Botón Flotante de Descarga de Video
// Utiliza Shadow DOM para aislamiento de CSS absoluto e inmunidad al diseño de la página web.

(function () {
  // Evitar inyección múltiple
  if (window.__brodownloadsInjected) return;
  window.__brodownloadsInjected = true;

  let currentMediaList = [];
  let activeVideoElement = null;
  let activePlayerContainer = null;
  let hideTimeout = null;
  let isDropdownOpen = false;
  let lastKnownMousePos = { x: 0, y: 0 };

  // 1. Crear contenedor raíz aislado con Shadow DOM
  const hostContainer = document.createElement("div");
  hostContainer.id = "brodownloads-sniffer-host";
  hostContainer.style.all = "initial";
  document.documentElement.appendChild(hostContainer);

  const shadow = hostContainer.attachShadow({ mode: "open" });

  // 2. Inyectar estilos y estructura HTML dentro del Shadow DOM
  shadow.innerHTML = `
    <style>
      :host {
        all: initial;
      }
      .brodownloads-panel {
        position: fixed;
        z-index: 2147483647;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: 12px;
        color: #ffffff;
        user-select: none;
        display: none;
        pointer-events: auto;
        transition: opacity 0.18s ease, transform 0.18s ease;
        opacity: 0;
        transform: translateY(-4px);
      }
      .brodownloads-panel.visible {
        display: block;
        opacity: 1;
        transform: translateY(0);
      }
      .brodownloads-btn-group {
        display: inline-flex;
        align-items: center;
        background: rgba(22, 24, 30, 0.94);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 6px;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.65);
        overflow: hidden;
      }
      .brodownloads-main-btn {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 10px;
        background: transparent;
        color: #f1f3f9;
        border: none;
        cursor: pointer;
        font-weight: 500;
        font-size: 12px;
        transition: background 0.15s ease, color 0.15s ease;
      }
      .brodownloads-main-btn:hover {
        background: rgba(92, 133, 255, 0.3);
        color: #70a5ff;
      }
      .brodownloads-toggle-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 6px 8px;
        background: transparent;
        color: #a0a6b8;
        border: none;
        border-left: 1px solid rgba(255, 255, 255, 0.12);
        cursor: pointer;
        transition: background 0.15s ease, color 0.15s ease;
      }
      .brodownloads-toggle-btn:hover {
        background: rgba(255, 255, 255, 0.15);
        color: #ffffff;
      }
      .brodownloads-icon {
        width: 14px;
        height: 14px;
        stroke: #5c85ff;
      }
      .brodownloads-dropdown {
        position: absolute;
        top: 100%;
        right: 0;
        margin-top: 5px;
        background: #17181f;
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 7px;
        box-shadow: 0 8px 26px rgba(0, 0, 0, 0.75);
        min-width: 260px;
        max-width: 340px;
        max-height: 250px;
        overflow-y: auto;
        display: none;
        flex-direction: column;
      }
      .brodownloads-dropdown.open {
        display: flex;
      }
      .brodownloads-dropdown-header {
        padding: 7px 10px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #8890a5;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        background: #121318;
      }
      .brodownloads-media-item {
        padding: 8px 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        cursor: pointer;
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        transition: background 0.15s ease;
      }
      .brodownloads-media-item:last-child {
        border-bottom: none;
      }
      .brodownloads-media-item:hover {
        background: #232733;
      }
      .brodownloads-item-left {
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }
      .brodownloads-item-label {
        font-size: 12px;
        font-weight: 500;
        color: #e6e9f2;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .brodownloads-item-sub {
        font-size: 10px;
        color: #8c92a4;
      }
      .brodownloads-tag {
        font-size: 10px;
        font-weight: 600;
        padding: 2px 6px;
        border-radius: 4px;
        background: rgba(92, 133, 255, 0.2);
        color: #70a5ff;
        white-space: nowrap;
      }
      .brodownloads-tag.stream {
        background: rgba(255, 170, 0, 0.2);
        color: #ffbb33;
      }
      .brodownloads-badge-count {
        background: #5c85ff;
        color: #fff;
        font-size: 10px;
        font-weight: 700;
        border-radius: 10px;
        padding: 1px 5px;
        margin-left: 2px;
      }
      .brodownloads-feedback {
        color: #51cf66 !important;
        font-weight: 600 !important;
      }
    </style>

    <div id="brodownloads-panel" class="brodownloads-panel">
      <div class="brodownloads-btn-group">
        <button id="btn-main" class="brodownloads-main-btn" title="Descargar con BRO-Downloads">
          <svg class="brodownloads-icon" viewBox="0 0 24 24" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
          </svg>
          <span id="btn-text">Descargar este video</span>
          <span id="btn-count" class="brodownloads-badge-count" style="display:none">0</span>
        </button>
        <button id="btn-toggle" class="brodownloads-toggle-btn" title="Ver opciones y calidades">
          ▼
        </button>
      </div>

      <div id="dropdown-menu" class="brodownloads-dropdown">
        <div class="brodownloads-dropdown-header">Videos / Audios disponibles</div>
        <div id="items-container"></div>
      </div>
    </div>
  `;

  const panel = shadow.getElementById("brodownloads-panel");
  const btnMain = shadow.getElementById("btn-main");
  const btnText = shadow.getElementById("btn-text");
  const btnCount = shadow.getElementById("btn-count");
  const btnToggle = shadow.getElementById("btn-toggle");
  const dropdown = shadow.getElementById("dropdown-menu");
  const itemsContainer = shadow.getElementById("items-container");

  // 3. Manejadores de interacción del botón
  panel.addEventListener("mouseenter", () => {
    clearTimeout(hideTimeout);
  });

  panel.addEventListener("mouseleave", () => {
    if (!isDropdownOpen) {
      scheduleHide(500);
    }
  });

  btnMain.addEventListener("click", () => {
    if (currentMediaList.length === 1) {
      downloadItem(currentMediaList[0]);
    } else {
      toggleDropdown();
    }
  });

  btnToggle.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleDropdown();
  });

  document.addEventListener("click", (e) => {
    if (isDropdownOpen) {
      closeDropdown();
    }
  });

  function toggleDropdown() {
    isDropdownOpen = !isDropdownOpen;
    dropdown.classList.toggle("open", isDropdownOpen);
  }

  function closeDropdown() {
    isDropdownOpen = false;
    dropdown.classList.remove("open");
  }

  function scheduleHide(delay = 600) {
    clearTimeout(hideTimeout);
    hideTimeout = setTimeout(() => {
      // Verificar si el cursor aún está en la zona del video o del botón
      if (!isCursorNearActiveTarget() && !isDropdownOpen) {
        panel.classList.remove("visible");
      }
    }, delay);
  }

  // Comprueba si el cursor del mouse está dentro o cerca del video, player o botón
  function isCursorNearActiveTarget() {
    if (!activeVideoElement) return false;

    const targetEl = activePlayerContainer || activeVideoElement;
    const rect = targetEl.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();

    const mx = lastKnownMousePos.x;
    const my = lastKnownMousePos.y;

    // Margen de tolerancia de 35px alrededor del reproductor
    const BUFFER = 35;
    const isOverPlayer = (
      mx >= rect.left - BUFFER &&
      mx <= rect.right + BUFFER &&
      my >= rect.top - BUFFER &&
      my <= rect.bottom + BUFFER
    );

    const isOverPanel = (
      panelRect.width > 0 &&
      mx >= panelRect.left - 10 &&
      mx <= panelRect.right + 10 &&
      my >= panelRect.top - 10 &&
      my <= panelRect.bottom + 10
    );

    return isOverPlayer || isOverPanel;
  }

  // 4. Posicionamiento dinámico del panel sobre el reproductor
  function positionPanelOver(videoEl) {
    if (!videoEl) return;
    const targetEl = activePlayerContainer || videoEl;
    const rect = targetEl.getBoundingClientRect();

    // Ignorar si el elemento no tiene dimensiones visibles
    if (rect.width < 120 || rect.height < 70) return;

    // Asegurar que haya al menos una opción disponible (YouTube / página actual si aún no hay sniff)
    ensureDefaultMediaAvailable(videoEl);

    // Calcular posición en la esquina superior derecha
    const top = Math.max(10, rect.top + 10);
    const right = Math.max(10, window.innerWidth - rect.right + 10);

    panel.style.top = `${top}px`;
    panel.style.right = `${right}px`;
    panel.classList.add("visible");
  }

  // Encuentra el contenedor principal del reproductor (YouTube, Vimeo, VideoJS, etc.)
  function findParentPlayerContainer(video) {
    return (
      video.closest(
        "#movie_player, .html5-video-player, ytd-player, .video-stream, .player-container, .video-js, .jwplayer, [data-player]"
      ) ||
      video.parentElement ||
      video
    );
  }

  // 5. Monitoreo continuo de MouseMove para inmunidad a Tooltips y Overlays
  window.addEventListener(
    "mousemove",
    (e) => {
      lastKnownMousePos.x = e.clientX;
      lastKnownMousePos.y = e.clientY;

      if (!activeVideoElement) return;

      if (isCursorNearActiveTarget()) {
        clearTimeout(hideTimeout);
        if (!panel.classList.contains("visible")) {
          positionPanelOver(activeVideoElement);
        }
      } else {
        if (!isDropdownOpen && panel.classList.contains("visible")) {
          scheduleHide(500);
        }
      }
    },
    { passive: true }
  );

  // 6. Vinculación a elementos <video>
  function attachVideoListeners(video) {
    if (video.__brodownloadsAttached) return;
    video.__brodownloadsAttached = true;

    const container = findParentPlayerContainer(video);

    const onEnter = () => {
      clearTimeout(hideTimeout);
      activeVideoElement = video;
      activePlayerContainer = container;
      positionPanelOver(video);
    };

    video.addEventListener("mouseenter", onEnter);
    if (container && container !== video) {
      container.addEventListener("mouseenter", onEnter);
    }

    video.addEventListener("play", () => {
      activeVideoElement = video;
      activePlayerContainer = container;
      ensureDefaultMediaAvailable(video);
    });

    // Detectar si el video tiene source directo
    inspectDirectSrc(video);
  }

  function ensureDefaultMediaAvailable(video) {
    // Si la lista está vacía, proporcionar siempre una opción viable
    if (currentMediaList.length === 0) {
      const isYouTube = window.location.hostname.includes("youtube.com");
      const title = document.title || "Video";

      let defaultUrl = window.location.href;
      let label = isYouTube ? "Video de YouTube (Página actual)" : "Video detectado en la página";

      const src = video.currentSrc || video.src;
      if (src && (src.startsWith("http://") || src.startsWith("https://"))) {
        defaultUrl = src;
        label = "Video Directo";
      }

      currentMediaList.push({
        id: "default_" + Date.now(),
        url: defaultUrl,
        label: label,
        ext: "mp4",
        formattedSize: isYouTube ? "Stream HD" : "Video Web",
        mime: "video/mp4"
      });
      renderDropdownItems();
    }
  }

  function inspectDirectSrc(video) {
    const src = video.currentSrc || video.src;
    if (src && (src.startsWith("http://") || src.startsWith("https://"))) {
      const exists = currentMediaList.some((m) => m.url === src);
      if (!exists) {
        currentMediaList.unshift({
          id: "direct_" + Math.random().toString(36).substr(2, 7),
          url: src,
          label: "Video Directo",
          ext: src.split("?")[0].split(".").pop() || "mp4",
          formattedSize: "",
          mime: "video/mp4"
        });
        renderDropdownItems();
      }
    }
  }

  function scanExistingVideos() {
    const videos = document.querySelectorAll("video");
    videos.forEach(attachVideoListeners);

    // Detección especial para YouTube si el video ya está presente
    if (window.location.hostname.includes("youtube.com")) {
      const ytPlayer = document.getElementById("movie_player") || document.querySelector("ytd-player");
      const ytVideo = document.querySelector("video");
      if (ytVideo) {
        activeVideoElement = ytVideo;
        activePlayerContainer = ytPlayer || ytVideo.parentElement;
        ensureDefaultMediaAvailable(ytVideo);
      }
    }
  }

  // Observador de mutaciones para SPAs (YouTube, Twitter, Facebook, TikTok)
  const observer = new MutationObserver(() => {
    scanExistingVideos();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  // Eventos de navegación interna de YouTube (SPA)
  window.addEventListener("yt-navigate-finish", () => {
    setTimeout(scanExistingVideos, 500);
  });
  window.addEventListener("popstate", () => {
    setTimeout(scanExistingVideos, 500);
  });

  // Soporte para pantalla completa
  document.addEventListener("fullscreenchange", () => {
    const fsEl = document.fullscreenElement;
    if (fsEl) {
      fsEl.appendChild(hostContainer);
    } else {
      document.documentElement.appendChild(hostContainer);
    }
    if (activeVideoElement) {
      positionPanelOver(activeVideoElement);
    }
  });

  // 7. Renderizado del menú desplegable y descarga
  function updateMediaList(list) {
    if (!list || list.length === 0) return;
    currentMediaList = list;

    if (list.length > 1) {
      btnCount.style.display = "inline-block";
      btnCount.textContent = list.length;
    } else {
      btnCount.style.display = "none";
    }

    renderDropdownItems();

    if (activeVideoElement) {
      positionPanelOver(activeVideoElement);
    }
  }

  function renderDropdownItems() {
    itemsContainer.innerHTML = "";
    currentMediaList.forEach((media) => {
      const itemEl = document.createElement("div");
      itemEl.className = "brodownloads-media-item";

      const isStream = media.ext === "m3u8" || media.ext === "mpd";
      const tagClass = isStream ? "brodownloads-tag stream" : "brodownloads-tag";

      itemEl.innerHTML = `
        <div class="brodownloads-item-left">
          <span class="brodownloads-item-label">${escapeHtml(media.label)}</span>
          <span class="brodownloads-item-sub">${escapeHtml(media.formattedSize || media.mime || "Streaming")}</span>
        </div>
        <span class="${tagClass}">.${escapeHtml(media.ext)}</span>
      `;

      itemEl.addEventListener("click", (e) => {
        e.stopPropagation();
        downloadItem(media);
      });

      itemsContainer.appendChild(itemEl);
    });
  }

  function downloadItem(media) {
    const originalText = btnText.textContent;
    btnText.textContent = "✓ Enviando a BRO-Downloads...";
    btnText.classList.add("brodownloads-feedback");

    chrome.runtime.sendMessage(
      {
        action: "download_media",
        media: media,
        pageTitle: document.title
      },
      (response) => {
        setTimeout(() => {
          btnText.textContent = originalText;
          btnText.classList.remove("brodownloads-feedback");
          closeDropdown();
        }, 1800);
      }
    );
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // 8. Inicialización: pedir medios ya capturados por el Service Worker
  chrome.runtime.sendMessage({ action: "get_tab_media" }, (resp) => {
    if (resp && resp.mediaList && resp.mediaList.length > 0) {
      updateMediaList(resp.mediaList);
    }
  });

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === "media_detected") {
      updateMediaList(msg.mediaList);
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scanExistingVideos);
  } else {
    scanExistingVideos();
  }

  window.addEventListener("scroll", () => {
    if (activeVideoElement && panel.classList.contains("visible")) {
      positionPanelOver(activeVideoElement);
    }
  }, { passive: true });

  window.addEventListener("resize", () => {
    if (activeVideoElement && panel.classList.contains("visible")) {
      positionPanelOver(activeVideoElement);
    }
  }, { passive: true });
})();
