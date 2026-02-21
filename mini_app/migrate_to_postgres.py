"""
Скрипт миграции данных из SQLite в PostgreSQL
"""
import os
import sqlite3
import asyncio
import asyncpg
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# Пути
BASE_DIR = Path(__file__).resolve().parent
SQLITE_DB_PATH = BASE_DIR / "users.db"

# Настройки PostgreSQL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/mini_app_db"
)


async def migrate_data():
    """Миграция данных из SQLite в PostgreSQL"""
    
    # Подключение к PostgreSQL
    print("Подключение к PostgreSQL...")
    conn_pg = await asyncpg.connect(DATABASE_URL)
    
    try:
        # Создание таблицы в PostgreSQL
        print("Создание таблицы users в PostgreSQL...")
        await conn_pg.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                credits INTEGER DEFAULT 5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                language VARCHAR(10) DEFAULT 'ru'
            )
        """)
        
        # Подключение к SQLite
        if not SQLITE_DB_PATH.exists():
            print(f"SQLite база данных не найдена: {SQLITE_DB_PATH}")
            print("Миграция не требуется - база данных пуста")
            return
        
        print(f"Чтение данных из SQLite: {SQLITE_DB_PATH}")
        sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
        sqlite_conn.row_factory = sqlite3.Row
        
        # Получение всех пользователей из SQLite
        cursor = sqlite_conn.execute("SELECT * FROM users")
        users = cursor.fetchall()
        
        if not users:
            print("Нет данных для миграции")
            return
        
        print(f"Найдено {len(users)} пользователей для миграции")
        
        # Миграция данных
        migrated_count = 0
        skipped_count = 0
        
        for user in users:
            telegram_id = user['telegram_id']
            username = user['username']
            credits = user['credits']
            
            # Парсинг даты создания
            created_at_str = user.get('created_at')
            if created_at_str:
                try:
                    if 'T' in created_at_str:
                        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    else:
                        created_at = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
                except:
                    created_at = datetime.utcnow()
            else:
                created_at = datetime.utcnow()
            
            language = user.get('language', 'ru')
            
            # Проверка существования пользователя в PostgreSQL
            exists = await conn_pg.fetchval(
                "SELECT EXISTS(SELECT 1 FROM users WHERE telegram_id = $1)",
                telegram_id
            )
            
            if exists:
                print(f"Пользователь {telegram_id} уже существует, пропускаем...")
                skipped_count += 1
                continue
            
            # Вставка данных
            await conn_pg.execute("""
                INSERT INTO users (telegram_id, username, credits, created_at, language)
                VALUES ($1, $2, $3, $4, $5)
            """, telegram_id, username, credits, created_at, language)
            
            migrated_count += 1
            print(f"Мигрирован пользователь: {telegram_id} ({username}) - {credits} искр")
        
        print(f"\nМиграция завершена!")
        print(f"Мигрировано: {migrated_count} пользователей")
        print(f"Пропущено (уже существуют): {skipped_count} пользователей")
        
        # Проверка данных
        total_pg = await conn_pg.fetchval("SELECT COUNT(*) FROM users")
        print(f"\nВсего пользователей в PostgreSQL: {total_pg}")
        
    except Exception as e:
        print(f"Ошибка при миграции: {e}")
        raise
    finally:
        await conn_pg.close()
        sqlite_conn.close()


async def verify_migration():
    """Проверка корректности миграции"""
    print("\nПроверка миграции...")
    
    # Подключение к обеим БД
    conn_pg = await asyncpg.connect(DATABASE_URL)
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    
    try:
        # Подсчет пользователей
        sqlite_count = sqlite_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        pg_count = await conn_pg.fetchval("SELECT COUNT(*) FROM users")
        
        print(f"SQLite: {sqlite_count} пользователей")
        print(f"PostgreSQL: {pg_count} пользователей")
        
        if sqlite_count == pg_count:
            print("✅ Количество пользователей совпадает")
        else:
            print("⚠️ Количество пользователей не совпадает!")
        
        # Проверка нескольких пользователей
        sqlite_users = sqlite_conn.execute("SELECT * FROM users LIMIT 5").fetchall()
        for user in sqlite_users:
            pg_user = await conn_pg.fetchrow(
                "SELECT * FROM users WHERE telegram_id = $1",
                user['telegram_id']
            )
            
            if pg_user:
                if (pg_user['credits'] == user['credits'] and 
                    pg_user['username'] == user['username']):
                    print(f"✅ Пользователь {user['telegram_id']} проверен")
                else:
                    print(f"⚠️ Несоответствие данных для пользователя {user['telegram_id']}")
            else:
                print(f"❌ Пользователь {user['telegram_id']} не найден в PostgreSQL")
    
    finally:
        await conn_pg.close()
        sqlite_conn.close()


if __name__ == "__main__":
    print("=" * 50)
    print("Миграция данных из SQLite в PostgreSQL")
    print("=" * 50)
    
    # Проверка переменных окружения
    if DATABASE_URL == "postgresql://user:password@localhost:5432/mini_app_db":
        print("\n⚠️ ВНИМАНИЕ: Используются значения по умолчанию для DATABASE_URL")
        print("Убедитесь, что вы установили правильные значения в .env файле:")
        print("DATABASE_URL=postgresql://username:password@host:port/database")
        print()
        response = input("Продолжить? (y/n): ")
        if response.lower() != 'y':
            print("Миграция отменена")
            exit(0)
    
    # Запуск миграции
    asyncio.run(migrate_data())
    
    # Проверка
    if SQLITE_DB_PATH.exists():
        asyncio.run(verify_migration())
    
    print("\n" + "=" * 50)
    print("Готово!")
    print("=" * 50)
