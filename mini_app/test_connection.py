"""
Скрипт для проверки подключения к PostgreSQL
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def test_connection():
    """Тест подключения к PostgreSQL"""
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://mini_app_user:password@localhost:5432/mini_app_db"
    )
    
    print("=" * 50)
    print("Тест подключения к PostgreSQL")
    print("=" * 50)
    print(f"URL: {DATABASE_URL.replace(DATABASE_URL.split('@')[0].split('//')[1], '***')}")
    print()
    
    try:
        print("Подключение к базе данных...")
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Проверка версии
        version = await conn.fetchval("SELECT version()")
        print("✅ Подключение успешно!")
        print(f"Версия PostgreSQL: {version.split(',')[0]}")
        print()
        
        # Проверка базы данных
        db_name = await conn.fetchval("SELECT current_database()")
        print(f"Текущая база данных: {db_name}")
        
        # Проверка пользователя
        user = await conn.fetchval("SELECT current_user")
        print(f"Текущий пользователь: {user}")
        print()
        
        # Проверка таблицы users
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'users'
            )
        """)
        
        if table_exists:
            print("✅ Таблица 'users' существует")
            count = await conn.fetchval("SELECT COUNT(*) FROM users")
            print(f"   Количество пользователей: {count}")
        else:
            print("⚠️ Таблица 'users' не найдена")
            print("   Запустите приложение для создания таблицы")
        
        await conn.close()
        print()
        print("=" * 50)
        print("Тест завершен успешно!")
        print("=" * 50)
        
    except asyncpg.exceptions.InvalidPasswordError:
        print("❌ Ошибка: Неверный пароль")
        print("Проверьте DATABASE_URL в файле .env")
    except asyncpg.exceptions.InvalidCatalogNameError:
        print("❌ Ошибка: База данных не найдена")
        print("Создайте базу данных:")
        print("  psql -U postgres")
        print("  CREATE DATABASE mini_app_db;")
    except asyncpg.exceptions.ConnectionDoesNotExistError:
        print("❌ Ошибка: Не удалось подключиться к серверу")
        print("Проверьте:")
        print("  1. Запущена ли служба PostgreSQL")
        print("  2. Правильность хоста и порта в DATABASE_URL")
        print("  3. Доступность порта 5432")
    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        print("\nПроверьте:")
        print("  1. Установлен ли PostgreSQL")
        print("  2. Правильность DATABASE_URL в .env")
        print("  3. Запущена ли служба PostgreSQL")

if __name__ == "__main__":
    asyncio.run(test_connection())
