(function () {
  // Авто-скрытие раскрытого секрета и авто-очистка clipboard.
  const REVEAL_MS = 30000;
  const CLIPBOARD_CLEAR_MS = 30000;

  let hideTimer = null;
  let activeField = null;
  let activeButton = null;

  let clipboardClearTimer = null;
  let lastCopied = "";

  // === Theme toggle ===

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    // Сохраняем выбор в куку, чтобы сервер мог отдать правильный data-theme
    // и не было FOUC при следующем заходе.
    const oneYear = 60 * 60 * 24 * 365;
    document.cookie = `theme=${theme}; path=/; max-age=${oneYear}; SameSite=Lax`;
  }

  function toggleTheme() {
    const cur = document.documentElement.dataset.theme || "light";
    applyTheme(cur === "dark" ? "light" : "dark");
  }

  // === Secret API ===

  async function fetchSecret(entryId, action) {
    // Приложение всегда на корне сайта (см. app.py docstring).
    const url = `/api/entries/${entryId}/secret?action=${encodeURIComponent(action)}`;
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.value || "";
  }

  // === Clipboard ===

  async function copyToClipboard(text) {
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch (e) {
      // Fallback для старых браузеров / не-HTTPS контекстов.
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      ok = document.execCommand("copy");
      document.body.removeChild(ta);
    }
    if (ok) {
      lastCopied = text;
      scheduleClipboardClear();
    }
    return ok;
  }

  function scheduleClipboardClear() {
    if (clipboardClearTimer) clearTimeout(clipboardClearTimer);
    clipboardClearTimer = setTimeout(async () => {
      // Пытаемся затереть. Если страница потеряла фокус — writeText
      // может бросить; молча игнорируем.
      try {
        await navigator.clipboard.writeText("");
      } catch (e) {
        /* nop */
      }
      clipboardClearTimer = null;
      lastCopied = "";
    }, CLIPBOARD_CLEAR_MS);
  }

  // === Reveal / hide ===

  function hideField(field, button) {
    if (!field) return;
    field.textContent = "••••••••";
    field.dataset.revealed = "0";
    if (button) button.classList.remove("is-revealed");
  }

  function clearHideTimer() {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
  }

  function armAutoHide(field, button) {
    clearHideTimer();
    activeField = field;
    activeButton = button;
    hideTimer = setTimeout(() => {
      hideField(field, button);
      activeField = null;
      activeButton = null;
      hideTimer = null;
    }, REVEAL_MS);
  }

  function revealField(field, button, value) {
    if (activeField && activeField !== field) {
      hideField(activeField, activeButton);
    }
    field.textContent = value || "(пусто)";
    field.dataset.revealed = "1";
    button.classList.add("is-revealed");
    armAutoHide(field, button);
  }

  async function toggleReveal(button, fieldId, action, entryId) {
    const field = document.getElementById(fieldId);
    if (!field) return;
    if (field.dataset.revealed === "1") {
      hideField(field, button);
      clearHideTimer();
      activeField = null;
      activeButton = null;
      return;
    }
    try {
      const value = await fetchSecret(entryId, action);
      revealField(field, button, value);
    } catch (e) {
      flashBtn(button, "Ошибка", false);
    }
  }

  // === UI helpers ===

  function flashBtn(btn, label, success = true) {
    const original = btn.innerHTML;
    btn.innerHTML = label;
    btn.disabled = true;
    btn.classList.add(success ? "btn-flash-ok" : "btn-flash-err");
    setTimeout(() => {
      btn.innerHTML = original;
      btn.disabled = false;
      btn.classList.remove("btn-flash-ok", "btn-flash-err");
    }, 1500);
  }

  // === Event handling ===

  document.addEventListener("click", async (ev) => {
    // Theme toggle
    const themeBtn = ev.target.closest("[data-theme-toggle]");
    if (themeBtn) {
      toggleTheme();
      return;
    }

    const target = ev.target.closest("button");
    if (!target) return;

    // Копировать произвольный текст
    if (target.dataset.copyText !== undefined) {
      const ok = await copyToClipboard(target.dataset.copyText);
      flashBtn(target, ok ? "Скопировано" : "Ошибка", ok);
      return;
    }

    // Копировать пароль
    if (target.dataset.copyPassword) {
      try {
        const value = await fetchSecret(target.dataset.copyPassword, "copy_password");
        const ok = await copyToClipboard(value);
        flashBtn(target, ok ? "Скопировано" : "Ошибка", ok);
      } catch (e) {
        flashBtn(target, "Ошибка", false);
      }
      return;
    }

    // Копировать become-пароль
    if (target.dataset.copyBecome) {
      try {
        const value = await fetchSecret(target.dataset.copyBecome, "copy_become");
        const ok = await copyToClipboard(value);
        flashBtn(target, ok ? "Скопировано" : "Ошибка", ok);
      } catch (e) {
        flashBtn(target, "Ошибка", false);
      }
      return;
    }

    // Показать/скрыть пароль
    if (target.dataset.revealPassword) {
      await toggleReveal(target, "password-field", "view_password", target.dataset.revealPassword);
      return;
    }

    // Показать/скрыть become-пароль
    if (target.dataset.revealBecome) {
      await toggleReveal(target, "become-password-field", "view_become", target.dataset.revealBecome);
    }
  });

  // Подтверждение submit (вместо inline onsubmit — CSP-совместимо).
  document.addEventListener("submit", (ev) => {
    const form = ev.target;
    if (form && form.dataset && form.dataset.confirm) {
      if (!window.confirm(form.dataset.confirm)) {
        ev.preventDefault();
      }
    }
  });

  // Авто-сабмит формы при изменении (для селектов фильтра и file-input).
  document.addEventListener("change", (ev) => {
    const el = ev.target;
    if (el && el.dataset && el.dataset.autoSubmit !== undefined && el.form) {
      el.form.submit();
    }
  });

  // При уходе со страницы — спрятать активный секрет.
  window.addEventListener("beforeunload", () => {
    if (activeField) hideField(activeField, activeButton);
  });
})();
