// popup.js - Lógica visual del menú de la extensión con soporte de Native Messaging y HTTP

const HOST_NAME = "com.brodownloads.host";

document.addEventListener("DOMContentLoaded", async () => {
  const statusBadge = document.getElementById("status-badge");
  const nativeStatus = document.getElementById("native-status");
  const toggleIntercept = document.getElementById("toggle-intercept");
  const portInput = document.getElementById("port-input");
  const tokenInput = document.getElementById("token-input");
  const btnSave = document.getElementById("btn-save");
  const btnTestNative = document.getElementById("btn-test-native");
  const btnSendTab = document.getElementById("btn-send-tab");

  // Cargar configuración local
  const config = await chrome.storage.local.get(["enabled", "port", "token"]);
  toggleIntercept.checked = config.enabled !== false;
  if (portInput) portInput.value = config.port || 9876;
  if (tokenInput) tokenInput.value = config.token || "";

  // Probar puente nativo al abrir
  await checkStatus();

  // Switch de intercepción
  toggleIntercept.addEventListener("change", async () => {
    await chrome.storage.local.set({ enabled: toggleIntercept.checked });
  });

  // Botón para probar puente nativo
  btnTestNative.addEventListener("click", async () => {
    await checkStatus();
  });

  // Guardar configuración de fallback HTTP
  if (btnSave) {
    btnSave.addEventListener("click", async () => {
      const port = parseInt(portInput.value) || 9876;
      const token = tokenInput.value.trim();
      await chrome.storage.local.set({ port, token });
      await checkStatus();
    });
  }

  // Enviar URL de la pestaña activa
  btnSendTab.addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url) return;

    statusBadge.textContent = "Enviando...";
    statusBadge.className = "badge checking";

    const payload = {
      action: "download",
      url: tab.url,
      filename: tab.title || "",
      referer: tab.url,
      userAgent: navigator.userAgent
    };

    try {
      chrome.runtime.sendNativeMessage(HOST_NAME, payload, (response) => {
        if (chrome.runtime.lastError) {
          fallbackHttpSend(payload);
        } else {
          statusBadge.textContent = "¡Enviado!";
          statusBadge.className = "badge online";
          setTimeout(checkStatus, 2000);
        }
      });
    } catch (e) {
      fallbackHttpSend(payload);
    }
  });

  async function checkStatus() {
    statusBadge.textContent = "Comprobando...";
    statusBadge.className = "badge checking";
    nativeStatus.textContent = "Verificando puente nativo...";

    try {
      chrome.runtime.sendNativeMessage(HOST_NAME, { action: "ping" }, async (response) => {
        if (chrome.runtime.lastError) {
          nativeStatus.innerHTML = `<span style="color:#ff6b6b">❌ Host nativo no detectado</span><br><small style="color:#aaa">Ejecuta install_native_host.bat para registrarlo en Windows.</small>`;
          // Verificar fallback HTTP
          await checkHttpFallback();
        } else if (response && response.status === "ok") {
          statusBadge.textContent = "● Nativo Conectado";
          statusBadge.className = "badge online";
          nativeStatus.innerHTML = `<span style="color:#51cf66">✅ Puente Nativo Activo</span><br><small style="color:#aaa">Comunicaciones por Windows Stdio OK (Sin tokens requeridos).</small>`;
        } else {
          nativeStatus.textContent = "Respuesta inesperada del host nativo.";
          await checkHttpFallback();
        }
      });
    } catch (err) {
      await checkHttpFallback();
    }
  }

  async function checkHttpFallback() {
    const port = parseInt(portInput ? portInput.value : 9876) || 9876;
    const token = tokenInput ? tokenInput.value.trim() : "";

    try {
      const resp = await fetch(`http://127.0.0.1:${port}/status`, {
        headers: { "X-BRODownload-Token": token }
      });

      if (resp.ok) {
        statusBadge.textContent = "● HTTP Conectado";
        statusBadge.className = "badge online";
      } else {
        statusBadge.textContent = "● Desconectado";
        statusBadge.className = "badge offline";
      }
    } catch (e) {
      statusBadge.textContent = "● Desconectado";
      statusBadge.className = "badge offline";
    }
  }

  async function fallbackHttpSend(payload) {
    const port = parseInt(portInput ? portInput.value : 9876) || 9876;
    const token = tokenInput ? tokenInput.value.trim() : "";

    try {
      const resp = await fetch(`http://127.0.0.1:${port}/download`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-BRODownload-Token": token
        },
        body: JSON.stringify(payload)
      });
      if (resp.ok) {
        statusBadge.textContent = "¡Enviado!";
        statusBadge.className = "badge online";
      } else {
        alert("Error enviando por HTTP fallback.");
      }
    } catch (e) {
      alert("No se pudo conectar con BRO-Downloads.");
    }
  }
});
