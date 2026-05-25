"""Password Manager — веб-интерфейс для системных администраторов.

Работает под Lab Manager (прозрачный TCP-прокси с авторизацией):
  * слушает 127.0.0.1:$PORT
  * приложение на корне / — никаких префиксов
  * авторизация на уровне Lab Manager

Ключ шифрования создаётся автоматически при первом запуске.
Бэкап базы и ключа — через UI.
"""
import io
import os
import secrets
import shutil
import zipfile
from datetime import datetime, timezone

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

from crypto import Vault
from models import BECOME_METHODS, CATEGORIES, CATEGORY_KEYS, Entry, db

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
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

    db.init_app(app)
    app.vault = Vault(key_path=KEY_PATH)

    with app.app_context():
        db.create_all()

    _register_routes(app)
    return app


def _register_routes(app):

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
        stats = {k: Entry.query.filter_by(category=k).count() for k, _ in CATEGORIES}
        return render_template(
            "index.html",
            entries=entries, categories=CATEGORIES,
            stats=stats, q=q, category=category,
        )

    @app.route("/entries/new", methods=["GET", "POST"])
    def entry_new():
        if request.method == "POST":
            entry = Entry()
            _apply_form(entry, request.form, app.vault)
            db.session.add(entry)
            db.session.commit()
            flash("Запись создана.", "success")
            return redirect(url_for("entry_view", entry_id=entry.id))
        return render_template(
            "entry_form.html", entry=None,
            categories=CATEGORIES, become_methods=BECOME_METHODS,
            password_value="", notes_value="", become_password_value="",
        )

    @app.route("/entries/<int:entry_id>")
    def entry_view(entry_id):
        entry = db.session.get(Entry, entry_id) or abort(404)
        return render_template("entry_view.html", entry=entry)

    @app.route("/entries/<int:entry_id>/edit", methods=["GET", "POST"])
    def entry_edit(entry_id):
        entry = db.session.get(Entry, entry_id) or abort(404)
        if request.method == "POST":
            _apply_form(entry, request.form, app.vault)
            db.session.commit()
            flash("Запись обновлена.", "success")
            return redirect(url_for("entry_view", entry_id=entry.id))
        return render_template(
            "entry_form.html", entry=entry,
            categories=CATEGORIES, become_methods=BECOME_METHODS,
            password_value=app.vault.decrypt(entry.password_enc),
            notes_value=app.vault.decrypt(entry.notes_enc),
            become_password_value=app.vault.decrypt(entry.become_password_enc),
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
        entry = db.session.get(Entry, entry_id) or abort(404)
        return jsonify(
            password=app.vault.decrypt(entry.password_enc),
            notes=app.vault.decrypt(entry.notes_enc),
            become_password=app.vault.decrypt(entry.become_password_enc),
        )

    # --- бэкап / восстановление ---

    @app.route("/backup")
    def backup_download():
        tmp_db = os.path.join(INSTANCE_DIR, f".backup-{secrets.token_hex(6)}.db")
        try:
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
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return send_file(
            buf, mimetype="application/zip", as_attachment=True,
            download_name=f"password-manager-backup-{stamp}.zip",
        )

    @app.route("/backup/restore", methods=["POST"])
    def backup_restore():
        file = request.files.get("backup")
        if not file or not file.filename:
            flash("Файл бэкапа не выбран.", "error")
            return redirect(url_for("index"))
        try:
            data = file.read()
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
                if DB_FILENAME not in names or KEY_FILENAME not in names:
                    flash(f"В архиве должны быть {DB_FILENAME} и {KEY_FILENAME}.", "error")
                    return redirect(url_for("index"))
                db_bytes = zf.read(DB_FILENAME)
                key_bytes = zf.read(KEY_FILENAME)
            db.session.remove()
            db.engine.dispose()
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            db_bak = f"{DB_PATH}.pre-restore-{stamp}"
            key_bak = f"{KEY_PATH}.pre-restore-{stamp}"
            if os.path.exists(DB_PATH):
                shutil.copy2(DB_PATH, db_bak)
            if os.path.exists(KEY_PATH):
                shutil.copy2(KEY_PATH, key_bak)
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
                    db.create_all()
                    _ = Entry.query.count()
            except Exception as e:
                if os.path.exists(db_bak):
                    shutil.copy2(db_bak, DB_PATH)
                if os.path.exists(key_bak):
                    shutil.copy2(key_bak, KEY_PATH)
                app.vault.reload()
                flash(f"Импорт не удался, откат. Ошибка: {e}", "error")
                return redirect(url_for("index"))
            flash("Бэкап восстановлен.", "success")
        except zipfile.BadZipFile:
            flash("Это не zip-архив.", "error")
        except Exception as e:
            flash(f"Ошибка импорта: {e}", "error")
        return redirect(url_for("index"))

    @app.route("/api/ping")
    def ping():
        return jsonify(ok=True)


def _apply_form(entry, form, vault):
    entry.title = (form.get("title") or "").strip() or "без названия"
    cat = form.get("category") or "other"
    entry.category = cat if cat in CATEGORY_KEYS else "other"
    entry.host = (form.get("host") or "").strip()
    entry.port = (form.get("port") or "").strip()
    entry.protocol = (form.get("protocol") or "").strip()
    entry.username = (form.get("username") or "").strip()
    entry.url = (form.get("url") or "").strip()
    entry.tags = (form.get("tags") or "").strip()
    entry.password_enc = vault.encrypt(form.get("password") or "")
    entry.notes_enc = vault.encrypt(form.get("notes") or "")
    become = form.get("become_method") or "none"
    entry.become_method = become if become in ("none", "sudo", "su") else "none"
    entry.become_password_enc = vault.encrypt(form.get("become_password") or "")


app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ["PORT"]),
        debug=False,
        use_reloader=False,
    )
