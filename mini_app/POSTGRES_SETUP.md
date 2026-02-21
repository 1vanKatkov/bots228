# Установка PostgreSQL на Windows для тестирования

Пошаговая инструкция по установке и настройке PostgreSQL на Windows.

## Способ 1: Установка через официальный установщик (рекомендуется)

### Шаг 1: Скачивание PostgreSQL

1. Перейдите на официальный сайт: https://www.postgresql.org/download/windows/
2. Нажмите "Download the installer"
3. Выберите версию (рекомендуется 15 или 16)
4. Скачайте установщик для Windows x86-64

### Шаг 2: Установка

1. Запустите скачанный установщик (например, `postgresql-16.x-windows-x64.exe`)
2. Нажмите "Next" на экране приветствия
3. Выберите директорию установки (по умолчанию `C:\Program Files\PostgreSQL\16`)
4. Выберите компоненты:
   - ✅ PostgreSQL Server (обязательно)
   - ✅ pgAdmin 4 (графический интерфейс - рекомендуется)
   - ✅ Stack Builder (опционально)
   - ✅ Command Line Tools (рекомендуется)
5. Выберите директорию для данных (по умолчанию `C:\Program Files\PostgreSQL\16\data`)
6. **ВАЖНО**: Запомните пароль для пользователя `postgres` (суперпользователь)
   - Рекомендуется использовать надежный пароль
   - Запишите его в безопасном месте
7. Выберите порт (по умолчанию 5432) - оставьте как есть
8. Выберите локаль (Locale) - можно оставить "Default locale"
9. Дождитесь завершения установки

### Шаг 3: Проверка установки

Откройте командную строку (CMD) или PowerShell и выполните:

```bash
psql --version
```

Должна отобразиться версия PostgreSQL.

### Шаг 4: Запуск службы PostgreSQL

PostgreSQL должен автоматически запуститься как служба Windows. Проверить можно:

1. Нажмите `Win + R`
2. Введите `services.msc` и нажмите Enter
3. Найдите службу "postgresql-x64-16" (или похожую)
4. Убедитесь, что статус "Выполняется"

Если служба не запущена:
- Правый клик → "Запустить"

## Способ 2: Установка через Docker (альтернативный)

Если у вас установлен Docker Desktop:

### Шаг 1: Запуск PostgreSQL в Docker

```bash
docker run --name postgres-miniapp `
  -e POSTGRES_PASSWORD=your_password `
  -e POSTGRES_DB=mini_app_db `
  -p 5432:5432 `
  -d postgres:16
```

### Шаг 2: Проверка

```bash
docker ps
```

Должен отображаться контейнер `postgres-miniapp`.

## Создание базы данных и пользователя

### Вариант 1: Через командную строку (psql)

1. Откройте командную строку или PowerShell
2. Подключитесь к PostgreSQL:

```bash
psql -U postgres
```

Введите пароль, который вы указали при установке.

3. Создайте базу данных:

```sql
CREATE DATABASE mini_app_db;
```

4. Создайте пользователя:

```sql
CREATE USER mini_app_user WITH PASSWORD 'your_secure_password';
```

5. Выдайте права:

```sql
GRANT ALL PRIVILEGES ON DATABASE mini_app_db TO mini_app_user;
```

6. Подключитесь к новой базе данных:

```sql
\c mini_app_db
```

7. Выдайте права на схему:

```sql
GRANT ALL ON SCHEMA public TO mini_app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO mini_app_user;
```

8. Выйдите:

```sql
\q
```

### Вариант 2: Через pgAdmin 4 (графический интерфейс)

1. Запустите pgAdmin 4 из меню Пуск
2. При первом запуске введите мастер-пароль (запомните его)
3. В левой панели разверните "Servers" → "PostgreSQL 16"
4. При запросе введите пароль пользователя `postgres`
5. Правый клик на "Databases" → "Create" → "Database"
   - Name: `mini_app_db`
   - Owner: `postgres`
   - Нажмите "Save"
6. Правый клик на "Login/Group Roles" → "Create" → "Login/Group Role"
   - General → Name: `mini_app_user`
   - Definition → Password: `your_secure_password`
   - Privileges → отметьте нужные права
   - Нажмите "Save"

## Настройка для вашего приложения

### 1. Создайте файл `.env` в директории `mini_app`:

```env
# PostgreSQL connection string
DATABASE_URL=postgresql://mini_app_user:your_secure_password@localhost:5432/mini_app_db

# OpenRouter API
OPENROUTER_API_KEY=your_api_key_here
```

**ВАЖНО**: Замените `your_secure_password` на пароль, который вы создали для пользователя `mini_app_user`.

### 2. Установите зависимости Python:

```bash
cd mini_app
pip install -r requirements.txt
```

### 3. Запустите миграцию:

```bash
python migrate_to_postgres.py
```

### 4. Запустите приложение:

```bash
python main.py
```

## Проверка подключения

### Тест через Python:

Создайте файл `test_connection.py`:

```python
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def test():
    DATABASE_URL = os.getenv("DATABASE_URL")
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        version = await conn.fetchval("SELECT version()")
        print("✅ Подключение успешно!")
        print(f"Версия PostgreSQL: {version}")
        await conn.close()
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")

asyncio.run(test())
```

Запустите:
```bash
python test_connection.py
```

## Устранение проблем

### Ошибка: "psql: command not found"

**Решение**: Добавьте PostgreSQL в PATH:
1. Найдите путь установки (обычно `C:\Program Files\PostgreSQL\16\bin`)
2. Добавьте его в системную переменную PATH:
   - Win + R → `sysdm.cpl` → "Дополнительно" → "Переменные среды"
   - В "Системные переменные" найдите `Path` → "Изменить"
   - "Создать" → вставьте путь к `bin`
   - Перезапустите командную строку

### Ошибка: "password authentication failed"

**Решение**: 
1. Проверьте правильность пароля в `.env`
2. Убедитесь, что пользователь существует:
   ```sql
   SELECT usename FROM pg_user;
   ```

### Ошибка: "could not connect to server"

**Решение**:
1. Проверьте, запущена ли служба PostgreSQL:
   ```bash
   # В PowerShell
   Get-Service postgresql*
   ```
2. Если не запущена:
   ```bash
   Start-Service postgresql-x64-16
   ```

### Ошибка: "database does not exist"

**Решение**: Создайте базу данных (см. раздел выше).

### Ошибка порта: "port 5432 is already in use"

**Решение**: 
1. Найдите процесс, использующий порт:
   ```bash
   netstat -ano | findstr :5432
   ```
2. Остановите другой экземпляр PostgreSQL или измените порт в настройках

## Полезные команды

### Остановка/запуск службы PostgreSQL:

```bash
# Остановить
Stop-Service postgresql-x64-16

# Запустить
Start-Service postgresql-x64-16

# Перезапустить
Restart-Service postgresql-x64-16
```

### Подключение к базе данных:

```bash
psql -U mini_app_user -d mini_app_db
```

### Просмотр всех баз данных:

```sql
\l
```

### Просмотр всех таблиц:

```sql
\dt
```

### Выход из psql:

```sql
\q
```

## Дополнительные настройки безопасности

Для продакшена рекомендуется:

1. Изменить порт по умолчанию
2. Настроить файрвол
3. Использовать SSL соединения
4. Ограничить доступ по IP

Для локального тестирования эти настройки не обязательны.

## Быстрый старт (краткая версия)

```bash
# 1. Установите PostgreSQL через официальный установщик
# 2. Запомните пароль для пользователя postgres

# 3. Создайте БД и пользователя:
psql -U postgres
CREATE DATABASE mini_app_db;
CREATE USER mini_app_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE mini_app_db TO mini_app_user;
\q

# 4. Создайте .env файл с DATABASE_URL
# 5. Установите зависимости и запустите миграцию
pip install -r requirements.txt
python migrate_to_postgres.py
```

## Готово!

После выполнения всех шагов PostgreSQL будет готов к использованию с вашим приложением.
