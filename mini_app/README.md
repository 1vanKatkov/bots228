# Telegram Mini App - Мистические услуги

Веб-приложение для Telegram Mini App с функционалом нумерологии и толкования снов.

## Возможности

- 🔮 **Нумерология**: Генерация персональных нумерологических отчетов в формате PDF
- 🌙 **Толкование снов**: Интерпретация снов с помощью AI через OpenRouter API
- 💎 **Система искр**: Встроенная система виртуальной валюты
- 📱 **Адаптивный дизайн**: Полностью оптимизировано для мобильных устройств

## Установка

### Предварительные требования

- Python 3.8+
- PostgreSQL 12+ (см. [POSTGRES_SETUP.md](POSTGRES_SETUP.md) для инструкций по установке)

### Шаги установки

1. Установите PostgreSQL (см. [POSTGRES_SETUP.md](POSTGRES_SETUP.md))

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` в директории `mini_app`:
```env
# PostgreSQL connection string
DATABASE_URL=postgresql://mini_app_user:your_password@localhost:5432/mini_app_db

# OpenRouter API
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

4. Создайте базу данных и пользователя (см. [POSTGRES_SETUP.md](POSTGRES_SETUP.md))

5. Запустите миграцию (если есть данные в SQLite):
```bash
python migrate_to_postgres.py
```

6. Проверьте подключение:
```bash
python test_connection.py
```

## Запуск

### Локальный запуск

```bash
python main.py
```

Приложение будет доступно по адресу: `http://localhost:8001`

### Запуск через Docker Compose

```bash
docker-compose up -d
```

Это запустит PostgreSQL и приложение в контейнерах.

## Деплой на хостинг

### 🚀 Amvera (Рекомендуется)

Подробные инструкции по деплою на Amvera см. в [AMVERA_DEPLOY.md](AMVERA_DEPLOY.md)

**Быстрый старт:**
1. Создайте проект на https://amvera.ru
2. Подключите репозиторий GitHub
3. Добавьте PostgreSQL базу данных
4. Настройте переменные окружения (`OPENROUTER_API_KEY`)
5. Нажмите "Деплой"

Amvera автоматически определит конфигурацию из `amvera.yml` или `Dockerfile`.

### Другие платформы

Подробные инструкции по деплою на другие платформы см. в [DEPLOY.md](DEPLOY.md)

## Использование в Telegram

1. Создайте бота через [@BotFather](https://t.me/BotFather)
2. Используйте команду `/newapp` для создания Mini App
3. Укажите URL вашего приложения (например, `https://yourdomain.com`)
4. Приложение автоматически определит пользователя через Telegram Web App API

## Структура проекта

```
mini_app/
├── main.py                  # Основное FastAPI приложение (точка входа)
├── templates/               # HTML шаблоны
│   ├── index.html          # Главная страница
│   ├── numerology.html     # Страница нумерологии
│   └── sonnik.html         # Страница толкования снов
├── static/                 # Статические файлы
│   └── style.css          # Стили для мобильной адаптации
├── requirements.txt        # Зависимости Python
├── Procfile                # Команда запуска для Heroku
├── Dockerfile              # Docker образ для контейнеризации
├── docker-compose.yml      # Docker Compose конфигурация
├── migrate_to_postgres.py  # Скрипт миграции данных
├── test_connection.py      # Скрипт проверки подключения
├── .gitignore              # Игнорируемые файлы для Git
├── README.md               # Документация проекта
├── DEPLOY.md               # Инструкции по деплою
├── POSTGRES_SETUP.md       # Инструкции по установке PostgreSQL
└── MIGRATION.md            # Инструкции по миграции БД
```

## Точка входа приложения

**Главный файл**: `main.py`

Приложение запускается командой:
```bash
uvicorn main:app --host 0.0.0.0 --port 8001
```

Или через Python:
```bash
python main.py
```

На хостингах используется `Procfile` или команда из настроек деплоя.

## API Endpoints

### GET `/`
Главная страница с выбором услуг

### GET `/numerology`
Страница нумерологии

### GET `/sonnik`
Страница толкования снов

### POST `/api/balance`
Получить баланс пользователя
- `telegram_id` (int): ID пользователя Telegram

### POST `/api/numerology/generate`
Сгенерировать нумерологический отчет
- `telegram_id` (int): ID пользователя Telegram
- `full_name` (str): Полное имя пользователя
- `birth_date` (str): Дата рождения в формате ДД.ММ.ГГГГ

### POST `/api/sonnik/interpret`
Интерпретировать сон
- `telegram_id` (int): ID пользователя Telegram
- `dream_text` (str): Текст описания сна

### GET `/api/download/{filename}`
Скачать сгенерированный PDF отчет

## Особенности

- **Telegram Web App API**: Автоматическое определение пользователя через `window.Telegram.WebApp`
- **Адаптивный дизайн**: Оптимизировано для всех размеров экранов
- **Haptic Feedback**: Тактильная обратная связь при действиях пользователя
- **Система искр**: Встроенная валюта для оплаты услуг
- **Безопасность**: Проверка баланса перед выполнением операций

## Требования

- Python 3.8+
- Доступ к OpenRouter API для толкования снов
- Модуль `report_generator` из директории `numerology` для генерации отчетов

## База данных

Приложение использует PostgreSQL для хранения данных пользователей.

- **Миграция с SQLite**: Если у вас есть данные в SQLite, используйте `migrate_to_postgres.py`
- **Новая установка**: База данных создается автоматически при первом запуске
- **Тестирование подключения**: Используйте `test_connection.py` для проверки

Подробные инструкции по установке PostgreSQL см. в [POSTGRES_SETUP.md](POSTGRES_SETUP.md)

## Примечания

- PDF отчеты сохраняются в директории `numerology/reports/`
- Начальный баланс новых пользователей: 5 искр
- Стоимость каждой услуги: 5 искр
