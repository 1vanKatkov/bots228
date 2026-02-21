# Миграция на PostgreSQL

Инструкция по миграции базы данных с SQLite на PostgreSQL для mini_app.

## Предварительные требования

1. Установленный PostgreSQL (версия 12+)
2. Созданная база данных PostgreSQL
3. Установленные зависимости Python

## Шаги миграции

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Создание базы данных PostgreSQL

Подключитесь к PostgreSQL и создайте базу данных:

```sql
CREATE DATABASE mini_app_db;
CREATE USER mini_app_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE mini_app_db TO mini_app_user;
```

### 3. Настройка переменных окружения

Создайте или обновите файл `.env` в директории `mini_app`:

```env
# PostgreSQL connection string
DATABASE_URL=postgresql://mini_app_user:your_password@localhost:5432/mini_app_db

# Другие переменные
OPENROUTER_API_KEY=your_api_key_here
```

Формат DATABASE_URL:
```
postgresql://username:password@host:port/database
```

### 4. Резервное копирование SQLite базы данных (рекомендуется)

```bash
cp users.db users.db.backup
```

### 5. Запуск миграции

```bash
python migrate_to_postgres.py
```

Скрипт выполнит:
- Создание таблицы `users` в PostgreSQL
- Копирование всех данных из SQLite
- Проверку корректности миграции

### 6. Проверка миграции

После миграции проверьте данные:

```python
import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect("postgresql://user:password@localhost:5432/mini_app_db")
    count = await conn.fetchval("SELECT COUNT(*) FROM users")
    print(f"Всего пользователей: {count}")
    await conn.close()

asyncio.run(check())
```

### 7. Запуск приложения

После успешной миграции запустите приложение:

```bash
python main.py
```

Приложение автоматически подключится к PostgreSQL.

## Откат миграции (если необходимо)

Если нужно вернуться к SQLite:

1. Остановите приложение
2. Удалите или переименуйте файл `.env` с DATABASE_URL
3. Восстановите SQLite базу из резервной копии:
   ```bash
   cp users.db.backup users.db
   ```
4. Откатите изменения в `main.py` (используйте git)

## Различия между SQLite и PostgreSQL

### Типы данных

- `INTEGER` → `BIGINT` (для telegram_id)
- `TEXT` → `VARCHAR(255)` или `TEXT`
- `TEXT` (дата) → `TIMESTAMP`

### Синтаксис SQL

- Параметры: `?` → `$1, $2, ...`
- Булевы значения: `0/1` → `TRUE/FALSE`
- Имена таблиц/колонок чувствительны к регистру (используйте кавычки при необходимости)

## Устранение проблем

### Ошибка подключения к PostgreSQL

```
asyncpg.exceptions.InvalidPasswordError: password authentication failed
```

**Решение**: Проверьте правильность DATABASE_URL в `.env`

### Таблица уже существует

```
asyncpg.exceptions.DuplicateTableError: relation "users" already exists
```

**Решение**: Это нормально, таблица будет пропущена. Если нужно пересоздать:
```sql
DROP TABLE users;
```

### Ошибка при миграции данных

Если миграция прервалась:
1. Проверьте логи ошибок
2. Убедитесь, что все данные в SQLite корректны
3. Запустите миграцию снова (дубликаты будут пропущены)

## Производительность

PostgreSQL обеспечивает:
- Лучшую производительность при большом количестве пользователей
- Поддержку транзакций и конкурентного доступа
- Возможность масштабирования
- Резервное копирование и репликацию

## Дополнительные настройки PostgreSQL

Для оптимизации производительности можно создать индексы:

```sql
CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_username ON users(username);
```

## Поддержка

При возникновении проблем:
1. Проверьте логи приложения
2. Убедитесь, что PostgreSQL запущен
3. Проверьте права доступа пользователя БД
4. Убедитесь, что порт 5432 доступен
