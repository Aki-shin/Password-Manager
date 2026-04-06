from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


CATEGORIES = [
    ("infrastructure", "Инфраструктура"),
    ("server", "Серверы"),
    ("network", "Сетевое оборудование"),
    ("workstation", "Пользовательские машины"),
    ("service", "Сервисные аккаунты"),
    ("other", "Прочее"),
]
CATEGORY_KEYS = {k for k, _ in CATEGORIES}


class Entry(db.Model):
    __tablename__ = "entries"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(32), nullable=False, default="other")
    host = db.Column(db.String(255), default="")
    port = db.Column(db.String(16), default="")
    protocol = db.Column(db.String(32), default="")  # ssh, rdp, https, winrm...
    username = db.Column(db.String(255), default="")
    password_enc = db.Column(db.Text, default="")
    url = db.Column(db.String(500), default="")
    tags = db.Column(db.String(255), default="")  # через запятую
    notes_enc = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def tag_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    def category_label(self):
        return dict(CATEGORIES).get(self.category, self.category)
