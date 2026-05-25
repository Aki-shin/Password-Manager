(function () {
  // Авто-скрытие раскрытого секрета через 30 секунд.
  const REVEAL_MS = 30000;
  let hideTimer = null;
  let activeField = null;
  let activeButton = null;

  function apiBase() {
    let path = window.location.pathname;
    if (!path.endsWith("/")) {
      path = path.substring(0, path.lastIndexOf("/") + 1);
    }
    return path;
  }
  const API_BASE = apiBase();

  async function fetchSecret(entryId) {
    const res = await fetch(`${API_BASE}api/entries/${entryId}/secret`, {
      credentials: "same-origin",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async function copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    }
  }

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

  function hideField(field, button) {
    if (!field) return;
    field.textContent = "••••••••";
    field.dataset.revealed = "0";
    if (button) button.classList.remove("is-revealed");
  }

  function clearTimer() {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
  }

  function armAutoHide(field, button) {
    clearTimer();
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
    // Если что-то ещё раскрыто — спрятать.
    if (activeField && activeField !== field) {
      hideField(activeField, activeButton);
    }
    field.textContent = value || "(пусто)";
    field.dataset.revealed = "1";
    button.classList.add("is-revealed");
    armAutoHide(field, button);
  }

  async function toggleReveal(button, fieldId, secretKey, entryId) {
    const field = document.getElementById(fieldId);
    if (!field) return;
    if (field.dataset.revealed === "1") {
      hideField(field, button);
      clearTimer();
      activeField = null;
      activeButton = null;
      return;
    }
    try {
      const data = await fetchSecret(entryId);
      revealField(field, button, data[secretKey]);
    } catch (e) {
      flashBtn(button, "Ошибка", false);
    }
  }

  document.addEventListener("click", async (ev) => {
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
        const data = await fetchSecret(target.dataset.copyPassword);
        const ok = await copyToClipboard(data.password || "");
        flashBtn(target, ok ? "Скопировано" : "Ошибка", ok);
      } catch (e) {
        flashBtn(target, "Ошибка", false);
      }
      return;
    }

    // Копировать become-пароль
    if (target.dataset.copyBecome) {
      try {
        const data = await fetchSecret(target.dataset.copyBecome);
        const ok = await copyToClipboard(data.become_password || "");
        flashBtn(target, ok ? "Скопировано" : "Ошибка", ok);
      } catch (e) {
        flashBtn(target, "Ошибка", false);
      }
      return;
    }

    // Показать/скрыть пароль
    if (target.dataset.revealPassword) {
      await toggleReveal(target, "password-field", "password", target.dataset.revealPassword);
      return;
    }

    // Показать/скрыть become-пароль
    if (target.dataset.revealBecome) {
      await toggleReveal(target, "become-password-field", "become_password", target.dataset.revealBecome);
      return;
    }

    // Показать/скрыть заметки
    if (target.dataset.revealNotes) {
      await toggleReveal(target, "notes-field", "notes", target.dataset.revealNotes);
    }
  });

  // При уходе со страницы — спрятать всё.
  window.addEventListener("beforeunload", () => {
    if (activeField) hideField(activeField, activeButton);
  });
})();
