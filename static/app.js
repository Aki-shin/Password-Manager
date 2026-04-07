(function () {
  // Приложение теперь на корне / (прозрачный TCP-прокси), поэтому
  // API_BASE — просто корень сайта.
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

    // Копировать произвольный текст
    if (target.dataset.copyText !== undefined) {
      const ok = await copyToClipboard(target.dataset.copyText);
      flash(target, ok ? "Скопировано" : "Ошибка");
      return;
    }

    // Копировать пароль
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

    // Копировать become-пароль
    if (target.dataset.copyBecome) {
      try {
        const data = await fetchSecret(target.dataset.copyBecome);
        const ok = await copyToClipboard(data.become_password || "");
        flash(target, ok ? "Скопировано" : "Ошибка");
      } catch (e) {
        flash(target, "Ошибка");
      }
      return;
    }

    // Показать пароль
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

    // Показать become-пароль
    if (target.dataset.revealBecome) {
      const field = document.getElementById("become-password-field");
      if (!field) return;
      if (field.dataset.revealed === "1") {
        field.textContent = "••••••••";
        field.dataset.revealed = "0";
        target.textContent = "Показать";
        return;
      }
      try {
        const data = await fetchSecret(target.dataset.revealBecome);
        field.textContent = data.become_password || "(пусто)";
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
