// background.js - Service Worker de BRO-Downloads (Manifest V3)
// 1. Interceptación limpia de descargas mediante onDeterminingFilename
// 2. Media Sniffer en tiempo real con webRequest para detectar videos y audios web

const HOST_NAME = "com.brodownloads.host";
const DEFAULT_PORT = 9876;

// Cache en memoria para respuestas ultra-rápidas sincrónicas
let localConfig = {
  enabled: true,
  port: DEFAULT_PORT,
  token: "",
  excludedSites: ["*banco*", "*login*", "*signin*"]
};

// Mapa para rastrear medios detectados por pestaña: tabId -> Array<mediaItem>
const tabMedia = new Map();

// Cargar configuración inicial
chrome.storage.local.get(null).then((cfg) => {
  if (cfg) Object.assign(localConfig, cfg);
});

// Sincronizar cambios en tiempo real
chrome.storage.onChanged.addListener((changes) => {
  for (const [key, change] of Object.entries(changes)) {
    localConfig[key] = change.newValue;
  }
});

// Limpiar medios de pestañas cerradas o recargadas
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading") {
    tabMedia.delete(tabId);
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  tabMedia.delete(tabId);
});

// Inicialización de valores predeterminados y menú contextual
chrome.runtime.onInstalled.addListener(async () => {
  const config = await chrome.storage.local.get([
    "enabled", "port", "token", "excludedSites"
  ]);

  if (config.enabled === undefined) {
    await chrome.storage.local.set(localConfig);
  }

  chrome.contextMenus.create({
    id: "brodownloads-context-download",
    title: "⚡ Descargar con BRO-Downloads",
    contexts: ["link", "image", "video", "audio"]
  });
});

// Manejador del menú contextual
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "brodownloads-context-download") {
    const targetUrl = info.linkUrl || info.srcUrl;
    if (targetUrl) {
      await processAndDispatchDownload({
        url: targetUrl,
        referer: tab ? tab.url : "",
        filename: ""
      });
    }
  }
});

// =========================================================================
// 1. MEDIA SNIFFER EN TIEMPO REAL (webRequest)
// =========================================================================

chrome.webRequest.onHeadersReceived.addListener(
  (details) => {
    if (details.tabId < 0 || !details.url) return;
    const url = details.url;
    const lowerUrl = url.toLowerCase();

    // Ignorar recursos internos o datos locales en memoria
    if (
      lowerUrl.startsWith("data:") ||
      lowerUrl.startsWith("blob:") ||
      lowerUrl.startsWith("chrome:") ||
      lowerUrl.startsWith("edge:") ||
      lowerUrl.startsWith("chrome-extension:")
    ) {
      return;
    }

    // Extraer cabeceras clave
    let contentType = "";
    let contentLength = 0;
    if (details.responseHeaders) {
      for (const h of details.responseHeaders) {
        const name = h.name.toLowerCase();
        if (name === "content-type") contentType = (h.value || "").toLowerCase();
        if (name === "content-length") contentLength = parseInt(h.value, 10) || 0;
      }
    }

    // Filtrar fragmentos individuales minúsculos de HLS (.ts, .m4s) para no saturar la lista
    const isSegment = /\.ts(\?|$)/i.test(lowerUrl) || /\.m4s(\?|$)/i.test(lowerUrl);
    if (isSegment) return;

    // Detectar si es un video, audio o stream de media
    const isMediaMime = (
      contentType.startsWith("video/") ||
      contentType.startsWith("audio/") ||
      contentType.includes("vnd.apple.mpegurl") ||
      contentType.includes("x-mpegurl") ||
      contentType.includes("dash+xml")
    );

    const isMediaExt = /\.(mp4|webm|mkv|mov|flv|avi|m3u8|mpd|mp3|m4a|aac|flac|ogg|opus)(\?|$)/i.test(lowerUrl);

    if (!isMediaMime && !isMediaExt) return;

    // Clasificar tipo y formato
    let label = "Video MP4";
    let ext = "mp4";
    if (lowerUrl.includes("googlevideo.com/videoplayback")) {
      label = "Video de YouTube (HD)";
      ext = "mp4";
    } else if (lowerUrl.includes(".m3u8") || contentType.includes("mpegurl")) {
      label = "Stream HLS (.m3u8)";
      ext = "m3u8";
    } else if (lowerUrl.includes(".mpd") || contentType.includes("dash")) {
      label = "Stream DASH (.mpd)";
      ext = "mpd";
    } else if (contentType.startsWith("audio/") || /\.(mp3|m4a|aac|flac|ogg)/i.test(lowerUrl)) {
      label = "Audio";
      ext = "mp3";
    } else if (lowerUrl.includes(".webm") || contentType.includes("webm")) {
      label = "Video WebM";
      ext = "webm";
    } else if (lowerUrl.includes(".mkv")) {
      label = "Video MKV";
      ext = "mkv";
    }

    let list = tabMedia.get(details.tabId);
    if (!list) {
      list = [];
      tabMedia.set(details.tabId, list);
    }

    // Evitar URLs duplicadas
    const exists = list.some((it) => it.url === url);
    if (!exists) {
      const mediaItem = {
        id: "media_" + Math.random().toString(36).substr(2, 9),
        url: url,
        mime: contentType,
        size: contentLength,
        formattedSize: formatBytes(contentLength),
        label: label,
        ext: ext,
        detectedAt: Date.now()
      };
      list.unshift(mediaItem);
      if (list.length > 25) list.pop();

      // Notificar al content script en la pestaña para actualizar el botón flotante
      chrome.tabs.sendMessage(details.tabId, {
        action: "media_detected",
        mediaList: list
      }).catch(() => { });
    }
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"]
);

// Manejador de mensajes entre Content Script y Background
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // 1. Obtener lista de medios de la pestaña activa
  if (msg.action === "get_tab_media") {
    const list = (sender.tab && sender.tab.id) ? (tabMedia.get(sender.tab.id) || []) : [];
    sendResponse({ mediaList: list });
    return true;
  }

  // 2. Descargar un medio seleccionado en el botón flotante
  if (msg.action === "download_media") {
    const media = msg.media;
    if (!media || !media.url) {
      sendResponse({ success: false, error: "URL inválida" });
      return true;
    }

    // Generar un nombre limpio basado en el título de la página
    let pageTitle = (msg.pageTitle || "video").trim();
    pageTitle = pageTitle.replace(/[<>:"/\\|?*]/g, "_").substring(0, 100);
    const filename = `${pageTitle}.${media.ext || "mp4"}`;

    processAndDispatchDownload({
      url: media.url,
      filename: filename,
      referer: (sender.tab ? sender.tab.url : "") || "",
      mime: media.mime || "",
      fileSize: media.size || 0
    }).then(() => {
      sendResponse({ success: true });
    }).catch((err) => {
      sendResponse({ success: false, error: String(err) });
    });
    return true;
  }
});

// =========================================================================
// 2. INTERCEPTOR DE DESCARGAS NATIVAS (onDeterminingFilename)
// =========================================================================

chrome.downloads.onDeterminingFilename.addListener((downloadItem, suggest) => {
  if (localConfig.enabled === false) return;

  const url = downloadItem.finalUrl || downloadItem.url;
  if (!url) return;

  const lowerUrl = url.toLowerCase();
  if (
    lowerUrl.startsWith("blob:") ||
    lowerUrl.startsWith("data:") ||
    lowerUrl.startsWith("chrome:") ||
    lowerUrl.startsWith("edge:") ||
    lowerUrl.startsWith("chrome-extension:") ||
    lowerUrl.startsWith("about:") ||
    lowerUrl.startsWith("filesystem:")
  ) {
    return;
  }

  if (isSiteExcluded(url, localConfig.excludedSites || [])) {
    return;
  }

  try {
    chrome.downloads.cancel(downloadItem.id, () => {
      chrome.downloads.erase({ id: downloadItem.id });
    });
  } catch (err) {
    console.warn("[BRO-Downloads] Error al cancelar descarga:", err);
  }

  let suggestedFilename = downloadItem.filename || "";
  if (suggestedFilename) {
    suggestedFilename = suggestedFilename.replace(/^.*[\\\/]/, "");
  }

  processAndDispatchDownload({
    url: url,
    filename: suggestedFilename,
    referer: downloadItem.referrer || "",
    mime: downloadItem.mime || "",
    fileSize: downloadItem.fileSize || 0
  });

  return false;
});

// =========================================================================
// 3. ENVÍO DE DATOS A PYTHON (Native Messaging + Fallback HTTP)
// =========================================================================

async function processAndDispatchDownload(data) {
  const cookiesStr = await getCookiesForUrl(data.url);

  const payload = {
    action: "download",
    url: data.url,
    filename: data.filename || "",
    referer: data.referer || "",
    cookies: cookiesStr,
    userAgent: navigator.userAgent,
    mime: data.mime || "",
    fileSize: data.fileSize || 0
  };

  try {
    chrome.runtime.sendNativeMessage(HOST_NAME, payload, (response) => {
      if (chrome.runtime.lastError) {
        console.warn("[BRO-Downloads] Native host no disponible, usando HTTP...", chrome.runtime.lastError.message);
        sendViaHttpFallback(payload);
      } else {
        console.log("[BRO-Downloads] Descarga enviada por Native Messaging:", response);
      }
    });
  } catch (err) {
    sendViaHttpFallback(payload);
  }
}

async function sendViaHttpFallback(data) {
  const port = localConfig.port || DEFAULT_PORT;
  const token = localConfig.token || "";

  try {
    const response = await fetch(`http://127.0.0.1:${port}/download`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-BRODownload-Token": token
      },
      body: JSON.stringify(data)
    });
    if (response.ok) {
      console.log("[BRO-Downloads] Descarga enviada mediante fallback HTTP.");
    }
  } catch (err) { }
}

async function getCookiesForUrl(url) {
  try {
    const cookies = await chrome.cookies.getAll({ url: url });
    return cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch (err) {
    return "";
  }
}

function isSiteExcluded(url, excludedPatterns) {
  const lowerUrl = url.toLowerCase();
  for (const pattern of excludedPatterns) {
    const regexPattern = "^" + pattern.toLowerCase().replace(/\*/g, ".*") + "$";
    try {
      if (new RegExp(regexPattern).test(lowerUrl)) {
        return true;
      }
    } catch (e) { }
  }
  return false;
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return "";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}
