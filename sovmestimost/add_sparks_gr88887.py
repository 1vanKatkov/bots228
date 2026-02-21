"""Скрипт для добавления 1000 искр пользователю gr88887"""
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
USER_DB_PATH = BASE_DIR / "sonnik_users.db"

if not USER_DB_PATH.exists():
    print(f"❌ База данных не найдена: {USER_DB_PATH}")
    exit(1)

with sqlite3.connect(USER_DB_PATH) as conn:
    # Ищем пользователя по username
    rows = conn.execute(
        "SELECT telegram_id, username, credits FROM users WHERE LOWER(REPLACE(username, '@', '')) LIKE ? OR LOWER(REPLACE(username, '@', '')) = ?",
        ('%gr88887%', 'gr88887')
    ).fetchall()
    
    if not rows:
        print(f"❌ Пользователь gr88887 не найден")
        # Показываем всех пользователей для отладки
        all_users = conn.execute("SELECT telegram_id, username, credits FROM users LIMIT 20").fetchall()
        if all_users:
            print("\nПервые 20 пользователей в базе:")
            for row in all_users:
                print(f"  - telegram_id: {row[0]}, username: {row[1]}, credits: {row[2]}")
        exit(1)
    
    if len(rows) > 1:
        print(f"⚠️ Найдено несколько пользователей:")
        for row in rows:
            print(f"  - telegram_id: {row[0]}, username: {row[1]}, credits: {row[2]}")
        exit(1)
    
    telegram_id, db_username, current_credits = rows[0]
    new_credits = current_credits + 1000
    
    conn.execute(
        "UPDATE users SET credits = ? WHERE telegram_id = ?",
        (new_credits, telegram_id)
    )
    
    print(f"✅ Добавлено 1000 искр пользователю {db_username} (telegram_id: {telegram_id})")
    print(f"   Было: {current_credits}, Стало: {new_credits}")
