"""
Скрипт для добавления искр пользователю по username.
Использование: python add_sparks_to_user.py <username> <amount>
Пример: python add_sparks_to_user.py gr88887 1000
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# Пробуем найти базу данных в текущей директории
USER_DB_PATH = BASE_DIR / "sonnik_users.db"
if not USER_DB_PATH.exists():
    USER_DB_PATH = BASE_DIR / "sovmestimost_users.db"

def add_sparks_by_username(username: str, amount: int):
    """Добавляет искры пользователю по username"""
    if not USER_DB_PATH.exists():
        print(f"❌ База данных не найдена: {USER_DB_PATH}")
        print("Проверьте путь к базе данных")
        return False
    
    with sqlite3.connect(USER_DB_PATH) as conn:
        # Ищем пользователя по username (может быть с префиксом user_ или без @)
        search_username = username.replace('@', '').lower()
        rows = conn.execute(
            "SELECT telegram_id, username, credits FROM users WHERE LOWER(REPLACE(username, '@', '')) LIKE ? OR LOWER(REPLACE(username, '@', '')) = ?",
            (f"%{search_username}%", search_username)
        ).fetchall()
        
        if not rows:
            print(f"❌ Пользователь с username '{username}' не найден в базе данных")
            print(f"   Путь к БД: {USER_DB_PATH}")
            # Показываем всех пользователей для отладки
            all_users = conn.execute("SELECT telegram_id, username, credits FROM users LIMIT 10").fetchall()
            if all_users:
                print("\nПервые 10 пользователей в базе:")
                for row in all_users:
                    print(f"  - telegram_id: {row[0]}, username: {row[1]}, credits: {row[2]}")
            return False
        
        if len(rows) > 1:
            print(f"⚠️ Найдено несколько пользователей с username '{username}':")
            for row in rows:
                print(f"  - telegram_id: {row[0]}, username: {row[1]}, credits: {row[2]}")
            print("Используйте telegram_id напрямую или уточните username")
            return False
        
        telegram_id, db_username, current_credits = rows[0]
        new_credits = current_credits + amount
        
        conn.execute(
            "UPDATE users SET credits = ? WHERE telegram_id = ?",
            (new_credits, telegram_id)
        )
        
        print(f"✅ Добавлено {amount} искр пользователю {db_username} (telegram_id: {telegram_id})")
        print(f"   Было: {current_credits}, Стало: {new_credits}")
        return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование: python add_sparks_to_user.py <username> <amount>")
        print("Пример: python add_sparks_to_user.py gr88887 1000")
        sys.exit(1)
    
    username = sys.argv[1]
    try:
        amount = int(sys.argv[2])
    except ValueError:
        print("❌ Ошибка: количество искр должно быть числом")
        sys.exit(1)
    
    add_sparks_by_username(username, amount)
