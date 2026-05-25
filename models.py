from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


CATEGORIES = [
    ("infrastructure", "Инфраструктура"),
    ("server", "Серверы"),
    ("network", "Сетевое оборудование"),
    ("workstation", "Пользовательские машины"),
    ("service", "Сервисные аккаунты"),
    ("other", "Прочее"),
]
CATEGORY_KEYS = {k for k, _ in CATEGORIES}

BECOME_METHODS = [
    ("none", "Нет"),
    ("sudo", "sudo"),
    ("su", "su"),
]


# Журнал доступа: какие действия логируются и как они называются в UI.
AUDIT_LABELS = {
    "entry_created":     "запись создана",
    "entry_updated":     "запись обновлена",
    "entry_deleted":     "запись удалена",
    "password_viewed":   "пароль показан",
    "password_copied":   "пароль скопирован",
    "become_viewed":     "пароль sudo/su показан",
    "become_copied":     "пароль sudo/su скопирован",
    "notes_viewed":      "заметки показаны",
    "backup_downloaded": "бэкап скачан",
    "backup_restored":   "бэкап восстановлен",
}

# Тип действия для CSS-класса/цвета на странице журнала.
AUDIT_KIND = {
    "entry_created":     "create",
    "entry_updated":     "update",
    "entry_deleted":     "delete",
    "password_viewed":   "view",
    "password_copied":   "view",
    "become_viewed":     "view",
    "become_copied":     "view",
    "notes_viewed":      "view",
    "backup_downloaded": "backup",
    "backup_restored":   "backup",
}


class Entry(db.Model):
    __tablename__ = "entries"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(32), nullable=False, default="other")
    host = db.Column(db.String(255), default="")
    port = db.Column(db.String(16), default="")
    protocol = db.Column(db.String(32), default="")
    username = db.Column(db.String(255), default="")
    password_enc = db.Column(db.Text, default="")
    url = db.Column(db.String(500), default="")
    tags = db.Column(db.String(255), default="")
    notes_enc = db.Column(db.Text, default="")
    become_method = db.Column(db.String(16), default="none")
    become_password_enc = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(
        db.DateTime, default=_utcnow, onupdate=_utcnow
    )

    def tag_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    def category_label(self):
        return dict(CATEGORIES).get(self.category, self.category)

    def become_label(self):
        return dict(BECOME_METHODS).get(self.become_method, self.become_method)


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(
        db.DateTime, default=_utcnow, nullable=False, index=True
    )
    entry_id = db.Column(db.Integer, nullable=True)
    entry_title = db.Column(db.String(200), default="")
    action = db.Column(db.String(64), nullable=False)
    remote_addr = db.Column(db.String(64), default="")

    def label(self) -> str:
        return AUDIT_LABELS.get(self.action, self.action)

    def kind(self) -> str:
        return AUDIT_KIND.get(self.action, "other")
