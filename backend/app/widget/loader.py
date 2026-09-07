import json
import os
from urllib.parse import urlsplit


DEFAULT_WIDGET_CHAT_URL = "http://localhost:3000/widget/chat"


def get_widget_chat_url() -> str:
    candidate = os.environ.get(
        "AGENTDESK_WIDGET_CHAT_URL",
        DEFAULT_WIDGET_CHAT_URL,
    ).strip()

    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return DEFAULT_WIDGET_CHAT_URL

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        return DEFAULT_WIDGET_CHAT_URL

    return candidate.rstrip("/")


def build_widget_loader_script() -> str:
    chat_url = json.dumps(get_widget_chat_url())
    template = r"""(function () {
  "use strict";

  var currentScript = document.currentScript;
  if (!currentScript || !(currentScript instanceof HTMLScriptElement)) {
    return;
  }

  var projectId = (currentScript.getAttribute("data-project") ||
    "local-default").trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(projectId)) {
    return;
  }

  var registryKey = "__agentdesk_widget_projects__";
  var registry = window[registryKey] || (window[registryKey] = {});
  if (registry[projectId]) {
    return;
  }
  registry[projectId] = true;

  var apiOrigin;
  try {
    apiOrigin = new URL(currentScript.src, window.location.href).origin;
  } catch (_error) {
    return;
  }

  var defaultChatUrl = __AGENTDESK_CHAT_URL__;
  var chatUrlValue = currentScript.getAttribute("data-chat-url") ||
    defaultChatUrl;
  var chatUrl;
  try {
    chatUrl = new URL(chatUrlValue, window.location.href);
  } catch (_error) {
    return;
  }
  if (chatUrl.protocol !== "http:" && chatUrl.protocol !== "https:") {
    return;
  }

  var storageKey = "agentdesk:" + projectId + ":session";
  var sessionId = null;
  var sessionRequest = null;
  var sending = false;
  var frame = null;
  var launcher = null;

  function isSessionId(value) {
    return typeof value === "string" &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
        .test(value);
  }

  function readStoredSession() {
    try {
      var value = window.localStorage.getItem(storageKey);
      return isSessionId(value) ? value : null;
    } catch (_error) {
      return null;
    }
  }

  function storeSession(value) {
    if (!isSessionId(value)) {
      return;
    }
    sessionId = value;
    try {
      window.localStorage.setItem(storageKey, value);
    } catch (_error) {
      // Private browsing or storage restrictions should not break the chat.
    }
  }

  function removeStoredSession() {
    sessionId = null;
    try {
      window.localStorage.removeItem(storageKey);
    } catch (_error) {
      // Ignore storage cleanup failures.
    }
  }

  function apiUrl(path) {
    return apiOrigin + path;
  }

  async function requestJson(path, options) {
    var response = await fetch(apiUrl(path), Object.assign({
      credentials: "omit",
    }, options || {}));
    var payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (!response.ok) {
      throw new Error("Widget request failed.");
    }
    return payload;
  }

  function isConversation(payload) {
    return payload && isSessionId(payload.session_id) &&
      typeof payload.status === "string" && Array.isArray(payload.messages);
  }

  function postToFrame(message) {
    if (frame && frame.contentWindow) {
      frame.contentWindow.postMessage(message, chatUrl.origin);
    }
  }

  function sendConversation(payload) {
    if (isConversation(payload)) {
      postToFrame({
        type: "agentdesk:conversation",
        conversation: payload,
      });
    } else {
      postToFrame({
        type: "agentdesk:error",
        message: "The conversation could not be loaded.",
      });
    }
  }

  async function ensureSession() {
    if (sessionRequest) {
      return sessionRequest;
    }

    sessionRequest = (async function () {
      var storedSession = sessionId || readStoredSession();
      if (storedSession) {
        try {
          var existing = await requestJson(
            "/api/widget/sessions/" + encodeURIComponent(storedSession) +
              "?project_id=" + encodeURIComponent(projectId),
            { headers: { Accept: "application/json" } }
          );
          storeSession(existing.session_id);
          sendConversation(existing);
          return;
        } catch (_error) {
          removeStoredSession();
        }
      }

      try {
        var created = await requestJson(
          "/api/widget/sessions?project_id=" + encodeURIComponent(projectId),
          { method: "POST", headers: { Accept: "application/json" } }
        );
        storeSession(created.session_id);
        sendConversation(created);
      } catch (_error) {
        postToFrame({
          type: "agentdesk:error",
          message: "The chat is temporarily unavailable.",
        });
      }
    })();

    try {
      await sessionRequest;
    } finally {
      sessionRequest = null;
    }
  }

  async function sendMessage(content) {
    if (sending || !sessionId) {
      return;
    }

    var normalized = typeof content === "string" ? content.trim() : "";
    if (!normalized || normalized.length > 10000) {
      postToFrame({
        type: "agentdesk:error",
        message: "Enter a message of 10,000 characters or fewer.",
      });
      return;
    }

    sending = true;
    postToFrame({ type: "agentdesk:sending" });
    try {
      var response = await requestJson(
        "/api/widget/sessions/" + encodeURIComponent(sessionId) +
          "/messages?project_id=" + encodeURIComponent(projectId),
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ content: normalized }),
        }
      );
      sendConversation(response);
    } catch (_error) {
      postToFrame({
        type: "agentdesk:error",
        message: "We could not complete that message. Please try again.",
      });
    } finally {
      sending = false;
      postToFrame({ type: "agentdesk:send-complete" });
    }
  }

  function setOpen(open) {
    if (!frame || !launcher) {
      return;
    }
    frame.hidden = !open;
    launcher.textContent = open ? "Close" : "Need help?";
    launcher.setAttribute("aria-expanded", open ? "true" : "false");
    if (open && !frame.src) {
      var frameUrl = new URL(chatUrl.href);
      frameUrl.searchParams.set("project", projectId);
      frame.src = frameUrl.href;
    }
  }

  function mount(config) {
    if (!config || config.enabled !== true ||
      (config.position !== "bottom-left" &&
        config.position !== "bottom-right")) {
      return;
    }

    var root = document.createElement("div");
    root.id = "agentdesk-widget-" + projectId;
    root.setAttribute("data-agentdesk-widget", projectId);
    root.style.position = "fixed";
    root.style.bottom = "20px";
    root.style.zIndex = "2147483000";
    if (config.position === "bottom-left") {
      root.style.left = "20px";
    } else {
      root.style.right = "20px";
    }

    var shadow = root.attachShadow({ mode: "closed" });
    var style = document.createElement("style");
    style.textContent = ""
      + ":host { all: initial; }"
      + "button, iframe { box-sizing: border-box; }"
      + "button { border: 0; border-radius: 999px; cursor: pointer; "
      + "font: 600 14px/1.2 Arial, sans-serif; padding: 13px 18px; "
      + "background: #18181b; color: #fff; box-shadow: 0 8px 24px "
      + "rgba(0,0,0,.25); }"
      + "button:hover { background: #27272a; }"
      + "button:focus-visible { outline: 2px solid #fff; outline-offset: 3px; }"
      + "iframe { background: #09090b; border: 0; border-radius: 16px; "
      + "box-shadow: 0 16px 50px rgba(0,0,0,.32); display: block; "
      + "height: min(600px, calc(100vh - 100px)); margin-bottom: 12px; "
      + "width: min(360px, calc(100vw - 40px)); }"
      + "iframe[hidden] { display: none; }";
    shadow.appendChild(style);

    launcher = document.createElement("button");
    launcher.type = "button";
    launcher.textContent = "Need help?";
    launcher.setAttribute("aria-label", "Open AgentDesk support chat");
    launcher.setAttribute("aria-expanded", "false");

    frame = document.createElement("iframe");
    frame.title = config.display_name || "AgentDesk Support";
    frame.hidden = true;
    frame.loading = "lazy";
    frame.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");

    launcher.addEventListener("click", function () {
      setOpen(frame.hidden);
    });
    shadow.appendChild(frame);
    shadow.appendChild(launcher);
    document.body.appendChild(root);
  }

  function handleFrameMessage(event) {
    if (!frame || event.source !== frame.contentWindow ||
      event.origin !== chatUrl.origin || !event.data ||
      typeof event.data.type !== "string") {
      return;
    }

    if (event.data.type === "agentdesk:ready") {
      postToFrame({
        type: "agentdesk:init",
        config: config,
      });
      void ensureSession();
    } else if (event.data.type === "agentdesk:send") {
      void sendMessage(event.data.content);
    } else if (event.data.type === "agentdesk:close") {
      setOpen(false);
    }
  }

  var config = null;
  window.addEventListener("message", handleFrameMessage);
  fetch(apiUrl("/api/widget/config/" + encodeURIComponent(projectId)), {
    credentials: "omit",
    headers: { Accept: "application/json" },
  }).then(function (response) {
    if (!response.ok) {
      throw new Error("Widget configuration unavailable.");
    }
    return response.json();
  }).then(function (payload) {
    config = payload;
    mount(payload);
  }).catch(function () {
    // A disabled, unconfigured, or disallowed widget stays invisible.
  });
})();
"""
    return template.replace("__AGENTDESK_CHAT_URL__", chat_url)
