"""Удаление пользователя из БД Mini App по username. Использование: python delete_user.py gr88887"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg2

# Загрузка .env с учётом кодировки (на Windows часто cp1251)
def _load_dotenv_safe(path: Path) -> None:
    if not path.exists():
        return
    for enc in ("utf-8", "cp1251", "utf-8-sig"):
        try:
            with open(path, encoding=enc) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")  # только первый =
                        k, v = k.strip(), v.strip()
                        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                            v = v[1:-1]
                        os.environ.setdefault(k, v)
            return
        except UnicodeDecodeError:
            continue


_root = Path(__file__).resolve().parent
_load_dotenv_safe(_root / ".env")
_load_dotenv_safe(_root.parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/mini_app_db")


def _ensure_ssl(url: str) -> str:
    """Для удалённого Postgres (Render и т.п.) добавляем sslmode=require, если не указан."""
    parsed = urlparse(url)
    if "localhost" in parsed.netloc or "127.0.0.1" in parsed.netloc:
        return url
    query = parsed.query or ""
    if "sslmode=" in query:
        return url
    new_query = f"{query}&sslmode=require" if query else "sslmode=require"
    return urlunparse(parsed._replace(query=new_query))


def delete_user(username: str) -> None:
    url = _ensure_ssl(DATABASE_URL)
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s", (username.strip(),))
            deleted = cur.rowcount
        conn.commit()
        print(f"Удалено записей: {deleted}")
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python delete_user.py <username>")
        sys.exit(1)
    delete_user(sys.argv[1])
