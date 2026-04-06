"""Password Manager — веб-интерфейс для системных администраторов.

Разворачивается как приложение внутри Lab Manager:
  * слушает 127.0.0.1:$PORT
  * живёт под префиксом /proxy/<name>/
  * использует ProxyFix, чтобы Flask корректно строил URL
  * авторизация доступа делается на уровне Lab Manager —
    внутри самого приложения никакого логина нет

Ключ шифрования создаётся автоматически при первом запуске
(instance/master.key). Бэкап базы и ключа доступен через UI —
кнопка «Бэкап» отдаёт zip с vault.db + master.key. Восстановление
через «Импорт бэкапа» — zip с теми же файлами.
"""
import io
import os
import secrets
import shutil
import zipfile
from datetime import datetime

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from sqlalchemy import or_
from werkzeug.middleware.proxy_fix import ProxyFix

from crypto import Vault
from models import CATEGORIES, CATEGORY_KEYS, Entry, db


class ScriptNameMiddleware:
    """Прослойка для работы под reverse-proxy Lab Manager.

    Lab Manager прокидывает префикс в заголовке X-Script-Name
    (например, /proxy/password-manager). Werkzeug ProxyFix читает
    только X-Forwarded-Prefix, поэтому без этой прослойки Flask
    строит url_for('static', ...) без префикса, и CSS/JS отдаются
    панелью Lab Manager вместо нашего приложения.

    Второй нюанс: Lab Manager к Location-заголовкам в редиректах
    всегда добавляет префикс /proxy/<name>, не проверяя, нет ли его
    там уже. Если мы выставили SCRIPT_NAME, Flask сам построит
    Location: /proxy/password-manager/entries/3 → после переписывания
    Lab Manager получится дублирование префикса и редирект в
    несуществующий URL (а затем на /login панели). Поэтому перед
    отдачей ответа мы срезаем префикс из Location — Lab Manager
    добавит его обратно сам.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = (environ.get("HTTP_X_SCRIPT_NAME", "") or "").rstrip("/")
        if script_name:
            environ["SCRIPT_NAME"] = script_name
            path_info = environ.get("PATH_INFO", "")
            if path_info.startswith(script_name):
                environ["PATH_INFO"] = path_info[len(script_name):] or "/"

        def custom_start_response(status, headers, exc_info=None):
            if script_name:
                fixed = []
                for name, value in headers:
                    if name.lower() == "location" and value:
                        value = _strip_prefix(value, script_name)
                    fixed.append((name, value))
                headers = fixed
            return start_response(status, headers, exc_info)

        return self.app(environ, custom_start_response)


def _strip_prefix(location: str, prefix: str) -> str:
    """Убрать префикс из абсолютного или относительного Location.

    Поддерживает оба варианта, которые может выдать Flask:
      * относительный: /proxy/password-manager/entries/3
      * абсолютный:    http://host/proxy/password-manager/entries/3
    """
    # Абсолютный URL: вырезаем префикс из path-части, схему/хост не трогаем.
    if "://" in location:
        scheme_sep = location.find("://") + 3
        path_start = location.find("/", scheme_sep)
        if path_start == -1:
            return location
        host_part = location[:path_start]
        path_part = location[path_start:]
        if path_part.startswith(prefix + "/") or path_part == prefix:
            path_part = path_part[len(prefix):] or "/"
        return host_part + path_part
    # Относительный path.
    if location.startswith(prefix + "/") or location == prefix:
        return location[len(prefix):] or "/"
    return location


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)

DB_FILENAME = "vault.db"
KEY_FILENAME = "master.key"
DB_PATH = os.path.join(INSTANCE_DIR, DB_FILENAME)
KEY_PATH = os.path.join(INSTANCE_DIR, KEY_FILENAME)


def create_app() -> Flask:
    app = Flask(__name__, instance_path=INSTANCE_DIR)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # SECRET_KEY нужен только под flash-сообщения; сессий у нас нет.
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    # Лимит на импорт бэкапа: 64 МБ — с запасом.
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

    # Приложение живёт за reverse-proxy Lab Manager.
    # Порядок обёрток важен: сначала ProxyFix разбирает X-Forwarded-*
    # (IP клиента, схема, хост), затем наша прослойка выставляет
    # SCRIPT_NAME из X-Script-Name — url_for() начинает строить
    # ссылки с префиксом /proxy/<name>/.
    app.wsgi_app = ScriptNameMiddleware(
        ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    )

    db.init_app(app)
    app.vault = Vault(key_path=KEY_PATH)

    with app.app_context():
        db.create_all()

    register_routes(app)
    return app


def register_routes(app: Flask) -> None:
    # ---------- список записей ----------
    @app.route("/")
    def index():
        q = (request.args.get("q") or "").strip()
        category = request.args.get("category") or ""
        query = Entry.query
        if category and category in CATEGORY_KEYS:
            query = query.filter(Entry.category == category)
        if q:
            like = f"%{q}%"
            query = query.filter(
                or_(
                    Entry.title.ilike(like),
                    Entry.host.ilike(like),
                    Entry.username.ilike(like),
                    Entry.tags.ilike(like),
                    Entry.url.ilike(like),
                )
            )
        entries = query.order_by(Entry.category, Entry.title).all()
        stats = {key: Entry.query.filter_by(category=key).count() for key, _ in CATEGORIES}
        return render_template(
            "index.html",
            entries=entries,
            categories=CATEGORIES,
            stats=stats,
            q=q,
            category=category,
        )

    # ---------- CRUD записей ----------
    @app.route("/entries/new", methods=["GET", "POST"])
    def entry_new():
        if request.method == "POST":
            entry = Entry()
            apply_entry_form(entry, request.form, app.vault)
            db.session.add(entry)
            db.session.commit()
            flash("Запись создана.", "success")
            return redirect(url_for("entry_view", entry_id=entry.id))
        return render_template(
            "entry_form.html",
            entry=None,
            categories=CATEGORIES,
            password_value="",
            notes_value="",
        )

    @app.route("/entries/<int:entry_id>")
    def entry_view(entry_id):
        entry = db.session.get(Entry, entry_id) or abort(404)
        return render_template("entry_view.html", entry=entry)

    @app.route("/entries/<int:entry_id>/edit", methods=["GET", "POST"])
    def entry_edit(entry_id):
        entry = db.session.get(Entry, entry_id) or abort(404)
        if request.method == "POST":
            apply_entry_form(entry, request.form, app.vault)
            db.session.commit()
            flash("Запись обновлена.", "success")
            return redirect(url_for("entry_view", entry_id=entry.id))
        return render_template(
            "entry_form.html",
            entry=entry,
            categories=CATEGORIES,
            password_value=app.vault.decrypt(entry.password_enc),
            notes_value=app.vault.decrypt(entry.notes_enc),
        )

    @app.route("/entries/<int:entry_id>/delete", methods=["POST"])
    def entry_delete(entry_id):
        entry = db.session.get(Entry, entry_id) or abort(404)
        db.session.delete(entry)
        db.session.commit()
        flash("Запись удалена.", "success")
        return redirect(url_for("index"))

    @app.route("/api/entries/<int:entry_id>/secret")
    def api_secret(entry_id):
        """Возвращает расшифрованные пароль и заметки — для кнопки
        «показать/скопировать» на фронте."""
        entry = db.session.get(Entry, entry_id) or abort(404)
        return jsonify(
            password=app.vault.decrypt(entry.password_enc),
            notes=app.vault.decrypt(entry.notes_enc),
        )

    # ---------- бэкап / восстановление ----------
    @app.route("/backup")
    def backup_download():
        """Отдаёт zip с vault.db и master.key.

        SQLite VACUUM INTO делает консистентный снапшот базы без
        блокировки активных соединений — безопаснее, чем просто
        копировать файл.
        """
        tmp_db = os.path.join(INSTANCE_DIR, f".backup-{secrets.token_hex(6)}.db")
        try:
            # VACUUM INTO требует, чтобы файл не существовал.
            from sqlalchemy import text
            with db.engine.connect() as conn:
                conn.exec_driver_sql(f"VACUUM INTO '{tmp_db}'")

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(tmp_db, arcname=DB_FILENAME)
                zf.write(KEY_PATH, arcname=KEY_FILENAME)
            buf.seek(0)
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

        stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return send_file(
            buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"password-manager-backup-{stamp}.zip",
        )

    @app.route("/backup/restore", methods=["POST"])
    def backup_restore():
        """Принимает zip с vault.db и master.key и заменяет текущие.

        Перед заменой закрываем пул соединений SQLAlchemy, иначе на
        Windows файл базы держится открытым. После восстановления
        перечитываем ключ и убеждаемся, что схема совместима.
        """
        file = request.files.get("backup")
        if not file or not file.filename:
            flash("Файл бэкапа не выбран.", "error")
            return redirect(url_for("index"))

        try:
            data = file.read()
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
                if DB_FILENAME not in names or KEY_FILENAME not in names:
                    flash(
                        f"В архиве должны быть {DB_FILENAME} и {KEY_FILENAME}.",
                        "error",
                    )
                    return redirect(url_for("index"))
                db_bytes = zf.read(DB_FILENAME)
                key_bytes = zf.read(KEY_FILENAME)

            # Отпускаем соединения, чтобы можно было перезаписать файл.
            db.session.remove()
            db.engine.dispose()

            # Резервные копии текущих файлов на случай провала импорта.
            stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            db_backup = f"{DB_PATH}.pre-restore-{stamp}"
            key_backup = f"{KEY_PATH}.pre-restore-{stamp}"
            if os.path.exists(DB_PATH):
                shutil.copy2(DB_PATH, db_backup)
            if os.path.exists(KEY_PATH):
                shutil.copy2(KEY_PATH, key_backup)

            try:
                with open(DB_PATH, "wb") as f:
                    f.write(db_bytes)
                with open(KEY_PATH, "wb") as f:
                    f.write(key_bytes)
                try:
                    os.chmod(KEY_PATH, 0o600)
                except OSError:
                    pass

                app.vault.reload()
                with app.app_context():
                    db.create_all()  # на случай если бэкап из старой версии
                    _ = Entry.query.count()  # sanity-check схемы
            except Exception as e:
                # Откат.
                if os.path.exists(db_backup):
                    shutil.copy2(db_backup, DB_PATH)
                if os.path.exists(key_backup):
                    shutil.copy2(key_backup, KEY_PATH)
                app.vault.reload()
                flash(f"Импорт не удался, откат. Ошибка: {e}", "error")
                return redirect(url_for("index"))

            flash("Бэкап восстановлен.", "success")
        except zipfile.BadZipFile:
            flash("Это не zip-архив.", "error")
        except Exception as e:
            flash(f"Ошибка импорта: {e}", "error")

        return redirect(url_for("index"))

    # ---------- служебное ----------
    @app.route("/api/ping")
    def ping():
        return jsonify(ok=True)


def apply_entry_form(entry: Entry, form, vault: Vault) -> None:
    entry.title = (form.get("title") or "").strip() or "без названия"
    category = form.get("category") or "other"
    entry.category = category if category in CATEGORY_KEYS else "other"
    entry.host = (form.get("host") or "").strip()
    entry.port = (form.get("port") or "").strip()
    entry.protocol = (form.get("protocol") or "").strip()
    entry.username = (form.get("username") or "").strip()
    entry.url = (form.get("url") or "").strip()
    entry.tags = (form.get("tags") or "").strip()
    password = form.get("password") or ""
    notes = form.get("notes") or ""
    entry.password_enc = vault.encrypt(password)
    entry.notes_enc = vault.encrypt(notes)


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ["PORT"]),
        debug=False,
        use_reloader=False,
    )
