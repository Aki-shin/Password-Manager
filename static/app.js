// Относительные URL: приложение живёт под /proxy/<name>/, поэтому
// все запросы строим от текущего location без ведущего слэша.
(function () {
  const API_BASE = (function () {
    // убираем последний сегмент пути (файл или пустую строку после /)
    let path = window.location.pathname;
    // всегда обрезаем до ближайшего /, чтобы получить базовый префикс
    if (!path.endsWith("/")) {
      path = path.substring(0, path.lastIndexOf("/") + 1);
    }
    // пытаемся определить префикс /proxy/<name>/ по <link href=".../static/...">
    const link = document.querySelector('link[rel="stylesheet"][href*="static/"]');
    if (link) {
      const href = link.getAttribute("href");
      const idx = href.indexOf("static/");
      if (idx >= 0) {
        // resolved URL даст абсолютный путь до static/
        const abs = new URL(link.href).pathname;
        const staticIdx = abs.indexOf("/static/");
        if (staticIdx >= 0) return abs.substring(0, staticIdx + 1);
      }
    }
    return path;
  })();

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
      // fallback для старых браузеров / http
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

  function flash(btn, text) {
    const original = btn.textContent;
    btn.textContent = text;
    btn.disabled = true;
    setTimeout(() => {
      btn.textContent = original;
      btn.disabled = false;
    }, 1500);
  }

  document.addEventListener("click", async (ev) => {
    const target = ev.target.closest("button");
    if (!target) return;

    // Копировать произвольный текст из data-copy-text
    if (target.dataset.copyText !== undefined) {
      const ok = await copyToClipboard(target.dataset.copyText);
      flash(target, ok ? "Скопировано" : "Ошибка");
      return;
    }

    // Копировать пароль по id
    if (target.dataset.copyPassword) {
      try {
        const data = await fetchSecret(target.dataset.copyPassword);
        const ok = await copyToClipboard(data.password || "");
        flash(target, ok ? "Скопировано" : "Ошибка");
      } catch (e) {
        flash(target, "Ошибка");
      }
      return;
    }

    // Показать пароль в <code id="password-field">
    if (target.dataset.revealPassword) {
      const field = document.getElementById("password-field");
      if (!field) return;
      if (field.dataset.revealed === "1") {
        field.textContent = "••••••••";
        field.dataset.revealed = "0";
        target.textContent = "Показать";
        return;
      }
      try {
        const data = await fetchSecret(target.dataset.revealPassword);
        field.textContent = data.password || "(пусто)";
        field.dataset.revealed = "1";
        target.textContent = "Скрыть";
      } catch (e) {
        flash(target, "Ошибка");
      }
      return;
    }

    // Показать заметки
    if (target.dataset.revealNotes) {
      const field = document.getElementById("notes-field");
      if (!field) return;
      if (field.dataset.revealed === "1") {
        field.textContent = "••••••••";
        field.dataset.revealed = "0";
        target.textContent = "Показать заметки";
        return;
      }
      try {
        const data = await fetchSecret(target.dataset.revealNotes);
        field.textContent = data.notes || "(пусто)";
        field.dataset.revealed = "1";
        target.textContent = "Скрыть заметки";
      } catch (e) {
        flash(target, "Ошибка");
      }
    }
  });
})();
