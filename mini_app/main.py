import os
import random
import requests
import logging
import re
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse
import asyncpg
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# Импорты для нумерологии: при rootDir=mini_app на Render есть только mini_app/numerology
import sys
_base = Path(__file__).resolve().parent
_numerology = _base / "numerology"
if _numerology.exists():
    sys.path.insert(0, str(_numerology))
else:
    sys.path.insert(0, str(_base.parent / "numerology"))

from report_generator import (
    calculate_action_number,
    calculate_character_number,
    calculate_consciousness_number,
    calculate_destiny_number,
    calculate_energy_number,
    generate_numerology_report_pdf,
)

# Пути
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Создаем директории
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

load_dotenv()

# Настройки PostgreSQL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/mini_app_db"
)

# Настройки
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL_SONNIK = "@preset/sonnik"
MODEL_SOVMESTIMOST = "@preset/sovmestimost"

STARTING_SPARKS = 100
SPARK_COST = 5

# --- Совместимость: числа экспрессии и жизненного пути ---
RUSSIAN_LETTERS = {
    'А': 1, 'Б': 2, 'В': 3, 'Г': 4, 'Д': 5, 'Е': 6, 'Ё': 7, 'Ж': 8, 'З': 9,
    'И': 1, 'Й': 2, 'К': 3, 'Л': 4, 'М': 5, 'Н': 6, 'О': 7, 'П': 8, 'Р': 9,
    'С': 1, 'Т': 2, 'У': 3, 'Ф': 4, 'Х': 5, 'Ц': 6, 'Ч': 7, 'Ш': 8, 'Щ': 9,
    'Ъ': 1, 'Ы': 2, 'Ь': 3, 'Э': 4, 'Ю': 5, 'Я': 6
}
LATIN_LETTERS = {
    'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8, 'I': 9,
    'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'O': 6, 'P': 7, 'Q': 8, 'R': 9,
    'S': 1, 'T': 2, 'U': 3, 'V': 4, 'W': 5, 'X': 6, 'Y': 7, 'Z': 8
}

def calculate_expression_number(name: str) -> int:
    name_upper = name.upper().strip()
    total = sum(
        RUSSIAN_LETTERS.get(c) or LATIN_LETTERS.get(c) or 0
        for c in name_upper
    )
    while total > 9 and total not in (11, 22, 33):
        total = sum(int(d) for d in str(total))
    return total

def calculate_life_path_number(birth_date: date) -> int:
    s = f"{birth_date.day:02d}{birth_date.month:02d}{birth_date.year}"
    total = sum(int(d) for d in s)
    while total > 9 and total not in (11, 22, 33):
        total = sum(int(d) for d in str(total))
    return total

def analyze_compatibility(expr1: int, expr2: int, path1: int, path2: int) -> dict:
    harmonious = [(1, 2), (2, 4), (3, 6), (4, 8), (5, 7)]
    conflict = [(1, 1), (3, 4)]
    def tag(a: int, b: int) -> str:
        if (a, b) in harmonious or (b, a) in harmonious:
            return "гармоничная"
        if (a, b) in conflict or (b, a) in conflict:
            return "конфликтная"
        if abs(a - b) >= 5:
            return "кармическая"
        return "нейтральная"
    return {
        "expr_compatibility": tag(expr1, expr2),
        "path_compatibility": tag(path1, path2),
    }

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальный пул соединений PostgreSQL
db_pool: Optional[asyncpg.Pool] = None

async def get_db_pool() -> asyncpg.Pool:
    """Получить пул соединений с БД. Если БД недоступна при старте — вернёт ошибку 503 при первом обращении."""
    global db_pool
    if db_pool is None:
        raise HTTPException(
            status_code=503,
            detail="База данных недоступна. Убедитесь, что PostgreSQL запущен и DATABASE_URL указан верно."
        )
    return db_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения. БД и таблицы создаются при старте, если их нет."""
    global db_pool
    try:
        try:
            db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
        except asyncpg.InvalidCatalogNameError:
            # База данных не существует — создаём
            parsed = urlparse(DATABASE_URL)
            db_name = (parsed.path or "/").lstrip("/")
            if db_name:
                postgres_url = urlunparse((parsed.scheme or "postgresql", parsed.netloc, "/postgres", parsed.params or "", parsed.query or "", parsed.fragment or ""))
                conn = await asyncpg.connect(postgres_url)
                try:
                    await conn.execute(f'CREATE DATABASE "{db_name}"')
                    logger.info("Database %s created", db_name)
                except asyncpg.DuplicateDatabaseError:
                    pass
                finally:
                    await conn.close()
            db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
        await init_db(db_pool)
        logger.info("Database pool created, tables initialized")
    except Exception as e:
        logger.warning("Database unavailable at startup: %s. App will run; API will return 503 until DB is available.", e)
        db_pool = None
    yield
    if db_pool:
        await db_pool.close()
        db_pool = None

app = FastAPI(title="Telegram Mini App", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Инициализация БД
async def init_db(pool: asyncpg.Pool):
    """Создание таблиц в PostgreSQL"""
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                credits INTEGER DEFAULT 100,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                language VARCHAR(10) DEFAULT 'ru'
            )
        """)

async def get_or_create_user(telegram_id: int, username: str = None) -> int:
    """Получить или создать пользователя"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT credits FROM users WHERE telegram_id = $1",
            telegram_id
        )
        if row:
            return row['credits']
        
        await conn.execute(
            "INSERT INTO users (telegram_id, username, credits, created_at) VALUES ($1, $2, $3, $4)",
            telegram_id,
            username or f"user_{telegram_id}",
            STARTING_SPARKS,
            datetime.utcnow()
        )
        return STARTING_SPARKS

async def deduct_sparks(telegram_id: int, amount: int) -> int:
    """Списать искры у пользователя"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT credits FROM users WHERE telegram_id = $1",
            telegram_id
        )
        if not row:
            return 0
        
        new_balance = max(row['credits'] - amount, 0)
        await conn.execute(
            "UPDATE users SET credits = $1 WHERE telegram_id = $2",
            new_balance,
            telegram_id
        )
        return new_balance

async def get_user_balance(telegram_id: int) -> int:
    """Получить баланс пользователя"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT credits FROM users WHERE telegram_id = $1",
            telegram_id
        )
        return row['credits'] if row else STARTING_SPARKS

# Роуты
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/numerology", response_class=HTMLResponse)
async def numerology_page(request: Request):
    return templates.TemplateResponse("numerology.html", {"request": request})

@app.get("/sonnik", response_class=HTMLResponse)
async def sonnik_page(request: Request):
    return templates.TemplateResponse("sonnik.html", {"request": request})

@app.get("/compatibility", response_class=HTMLResponse)
async def compatibility_page(request: Request):
    return templates.TemplateResponse("compatibility.html", {"request": request})

@app.post("/api/balance")
async def get_balance(telegram_id: int = Form(...)):
    balance = await get_user_balance(telegram_id)
    return JSONResponse({"balance": balance})

@app.post("/api/numerology/generate")
async def generate_numerology_report(
    telegram_id: int = Form(...),
    full_name: str = Form(...),
    birth_date: str = Form(...)
):
    try:
        # Проверка баланса
        balance = await get_user_balance(telegram_id)
        if balance < SPARK_COST:
            return JSONResponse(
                {"error": "Недостаточно искр", "balance": balance},
                status_code=400
            )
        
        # Парсинг даты
        try:
            birth_date_obj = datetime.strptime(birth_date, "%d.%m.%Y").date()
        except ValueError:
            return JSONResponse({"error": "Неверный формат даты. Используйте ДД.ММ.ГГГГ"}, status_code=400)
        
        # Списываем искры
        new_balance = await deduct_sparks(telegram_id, SPARK_COST)
        
        # Генерируем отчет
        pdf_path = generate_numerology_report_pdf(telegram_id, full_name, birth_date_obj)
        
        return JSONResponse({
            "success": True,
            "pdf_url": f"/api/download/{pdf_path.name}",
            "balance": new_balance
        })
    except Exception as e:
        logger.error(f"Error generating numerology report: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/sonnik/interpret")
async def interpret_dream(
    telegram_id: int = Form(...),
    dream_text: str = Form(...)
):
    try:
        # Проверка баланса
        balance = await get_user_balance(telegram_id)
        if balance < SPARK_COST:
            return JSONResponse(
                {"error": "Недостаточно искр", "balance": balance},
                status_code=400
            )
        
        # Списываем искры
        new_balance = await deduct_sparks(telegram_id, SPARK_COST)
        
        # Отправляем запрос в OpenRouter
        thinking_messages = [
            "🌙 Прислушиваюсь к шепоту вашего сна...",
            "✨ Читаю лунные письма вашей души...",
            "🕯️ Вглядываюсь в узоры ночного видения...",
            "🌌 Слежу за нитями сновидения...",
            "🌀 Расшифровываю символы подсознания...",
        ]
        
        thinking_message = random.choice(thinking_messages)
        
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={
                    "model": MODEL_SONNIK,
                    "messages": [{"role": "user", "content": dream_text}]
                },
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            interpretation = result['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            interpretation = "🌀 Ошибка связи с ИИ. Попробуйте позже."
        
        return JSONResponse({
            "success": True,
            "interpretation": interpretation,
            "thinking": thinking_message,
            "balance": new_balance
        })
    except Exception as e:
        logger.error(f"Error interpreting dream: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# Промпты для совместимости (как в боте)
PROMPT_NAMES_DATES_AI = """Проведи углубленный разбор совместимости двух людей на основе их имен, дат рождения, чисел экспрессии и чисел жизненного пути.

{compatibility_data}

Учти гармоничные пары (1 и 2, 2 и 4, 3 и 6, 4 и 8, 5 и 7), конфликтные пары (1 и 1, 3 и 4) и кармические связи (разница в числах 5 или больше). Дай подробный анализ совместимости."""

PROMPT_NAMES_ONLY_AI = """Проанализируй совместимость двух людей на основе их имен.

{expression_data}

Учти числа экспрессии при анализе совместимости. Исходный текст пользователя: {user_input}"""

@app.post("/api/compatibility/names_dates")
async def compatibility_names_dates(
    telegram_id: int = Form(...),
    name1: str = Form(...),
    date1: str = Form(...),
    name2: str = Form(...),
    date2: str = Form(...),
):
    try:
        balance = await get_user_balance(telegram_id)
        if balance < SPARK_COST:
            return JSONResponse({"error": "Недостаточно искр", "balance": balance}, status_code=400)
        try:
            d1 = datetime.strptime(date1.strip(), "%d.%m.%Y").date()
            d2 = datetime.strptime(date2.strip(), "%d.%m.%Y").date()
        except ValueError:
            return JSONResponse({"error": "Неверный формат даты. Используйте ДД.ММ.ГГГГ"}, status_code=400)
        n1, n2 = name1.strip(), name2.strip()
        if not n1 or not n2:
            return JSONResponse({"error": "Введите оба имени"}, status_code=400)
        new_balance = await deduct_sparks(telegram_id, SPARK_COST)
        expr1 = calculate_expression_number(n1)
        expr2 = calculate_expression_number(n2)
        path1 = calculate_life_path_number(d1)
        path2 = calculate_life_path_number(d2)
        comp = analyze_compatibility(expr1, expr2, path1, path2)
        date1_str = d1.strftime("%d.%m.%Y")
        date2_str = d2.strftime("%d.%m.%Y")
        prompt_data = f"""Имя1: {n1}
др1: {date1_str}
Число экспрессии1: {expr1}
Число жизненного пути1: {path1}
Имя2: {n2}
др2: {date2_str}
Число экспрессии2: {expr2}
Число жизненного пути2: {path2}
Оценка совместимости по экспрессии: {comp['expr_compatibility']}
Оценка совместимости по жизненному пути: {comp['path_compatibility']}"""
        prompt = PROMPT_NAMES_DATES_AI.format(compatibility_data=prompt_data)
        resp = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={"model": MODEL_SOVMESTIMOST, "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        resp.raise_for_status()
        interpretation = resp.json()["choices"][0]["message"]["content"]
        return JSONResponse({
            "success": True,
            "interpretation": interpretation,
            "balance": new_balance,
        })
    except requests.RequestException as e:
        logger.error(f"OpenRouter compatibility error: {e}")
        return JSONResponse({"error": "Ошибка связи с ИИ. Попробуйте позже."}, status_code=500)
    except Exception as e:
        logger.error(f"Error compatibility names_dates: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/compatibility/names_only")
async def compatibility_names_only(
    telegram_id: int = Form(...),
    name1: str = Form(...),
    name2: str = Form(...),
):
    try:
        balance = await get_user_balance(telegram_id)
        if balance < SPARK_COST:
            return JSONResponse({"error": "Недостаточно искр", "balance": balance}, status_code=400)
        n1, n2 = name1.strip(), name2.strip()
        if not n1 or not n2:
            return JSONResponse({"error": "Введите оба имени"}, status_code=400)
        new_balance = await deduct_sparks(telegram_id, SPARK_COST)
        expr1 = calculate_expression_number(n1)
        expr2 = calculate_expression_number(n2)
        prompt_data = f"Имя 1: {n1}\nЧисло экспрессии: {expr1}\nИмя 2: {n2}\nЧисло экспрессии: {expr2}"
        prompt = PROMPT_NAMES_ONLY_AI.format(user_input=f"{n1} и {n2}", expression_data=prompt_data)
        resp = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={"model": MODEL_SOVMESTIMOST, "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        resp.raise_for_status()
        interpretation = resp.json()["choices"][0]["message"]["content"]
        return JSONResponse({
            "success": True,
            "interpretation": interpretation,
            "balance": new_balance,
        })
    except requests.RequestException as e:
        logger.error(f"OpenRouter compatibility error: {e}")
        return JSONResponse({"error": "Ошибка связи с ИИ. Попробуйте позже."}, status_code=500)
    except Exception as e:
        logger.error(f"Error compatibility names_only: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    # Проверяем несколько возможных путей
    possible_paths = [
        ROOT_DIR / "numerology" / "reports" / filename,
        BASE_DIR / "reports" / filename,
    ]
    
    for file_path in possible_paths:
        if file_path.exists():
            return FileResponse(file_path, media_type="application/pdf", filename=filename)
    
    raise HTTPException(status_code=404, detail="File not found")

if __name__ == "__main__":
    import uvicorn
    # Amvera использует порт из переменной окружения PORT или 8080 по умолчанию
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
