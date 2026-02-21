import os
import logging
import asyncio
import random
import re
import sqlite3
import uuid
import json
import argparse
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional, List

import requests
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    Update
)
from telegram.error import Forbidden, BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)

from dotenv import load_dotenv
from yookassa import Configuration, Payment

# --- Аргументы командной строки ---
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="Bot token")
    parser.add_argument("--messages", help="Path to messages.json")
    parser.add_argument("--test", action="store_true", help="Run in test mode (test DB and test Yookassa)")
    parser.add_argument("--lang", help="Force fixed language (ru, en, es)")
    return parser.parse_known_args()[0]

args = parse_args()

# Путь к директории бота
BASE_DIR = Path(__file__).resolve().parent

# Настройка логирования
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_file = BASE_DIR.parent / "logs" / ("sovmestimost_bot_test.log" if args.test else "sovmestimost_bot.log")
(BASE_DIR.parent / "logs").mkdir(exist_ok=True)

from logging.handlers import RotatingFileHandler
file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)

load_dotenv()

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID_TEST" if args.test else "YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY_TEST" if args.test else "YOOKASSA_SECRET_KEY")
YOOKASSA_ACCOUNT_ID = os.getenv("YOOKASSA_ACCOUNT_ID_TEST" if args.test else "YOOKASSA_ACCOUNT_ID")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "https://t.me/your_bot_username")
# Тестовый режим Юкассы: если передан флаг --test, принудительно ставим "1"
YOOKASSA_TEST_MODE = "1" if args.test else os.getenv("YOOKASSA_TEST_MODE", "1")

if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY and YOOKASSA_ACCOUNT_ID:
    Configuration.configure(
        shop_id=YOOKASSA_SHOP_ID,
        secret_key=YOOKASSA_SECRET_KEY,
        account_id=YOOKASSA_ACCOUNT_ID,
    )

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL = "@preset/sovmestimost"

# Токен: сначала из аргументов, потом из .env
TELEGRAM_BOT_TOKEN = args.token or os.getenv("TELEGRAM_BOT_TOKEN")

USER_DB_PATH = BASE_DIR / ("sonnik_users_test.db" if args.test else "sonnik_users.db")
STARTING_SPARKS = 100
SPARK_COST = 5

SUBSCRIPTION_PACKAGES = {
    "sub_150": {"sparks": 150, "amount": 149, "period_days": 30, "label": "150 искр (1 месяц) — 149₽"},
    "sub_450": {"sparks": 450, "amount": 399, "period_days": 90, "label": "450 искр (3 месяца) — 399₽"},
    "sub_900": {"sparks": 900, "amount": 749, "period_days": 180, "label": "900 искр (6 месяцев) — 749₽"},
}

TOP_UP_PACKAGES = {
    "topup_50": {"sparks": 50, "amount": 100, "label": "50 искр — 100₽"},
    "topup_100": {"sparks": 100, "amount": 200, "label": "100 искр — 200₽"},
}

# --- Локализация ---

def load_messages():
    messages_path = Path(args.messages or (BASE_DIR / "messages.json"))
    if not messages_path.exists():
        messages_path = BASE_DIR / "messages.json"
    if not messages_path.exists():
        return {}
    with open(messages_path, "r", encoding="utf-8") as f:
        return json.load(f)

MESSAGES = load_messages()

def get_user_lang(tid: int, update: Optional[Update] = None) -> str:
    if args.lang: return args.lang
    
    with sqlite3.connect(USER_DB_PATH) as conn:
        row = conn.execute("SELECT language FROM users WHERE telegram_id = ?", (tid,)).fetchone()
        if row and row[0]: return row[0]
    
    lang = "ru"
    user = None
    if update:
        if hasattr(update, "effective_user") and update.effective_user:
            user = update.effective_user
        elif hasattr(update, "from_user") and update.from_user:
            user = update.from_user
            
    if user and user.language_code:
        code = user.language_code.lower()
        if code.startswith("en"): lang = "en"
        elif code.startswith("es"): lang = "es"
    return lang

def get_msg(tid: int, key: str, update: Optional[Update] = None, **kwargs) -> any:
    lang = get_user_lang(tid, update)
    lang_msgs = MESSAGES.get(lang, MESSAGES.get("ru", {}))
    msg = lang_msgs.get(key, MESSAGES.get("ru", {}).get(key, key))
    if isinstance(msg, str): return msg.format(**kwargs)
    return msg

# --- Расчет числа экспрессии ---

# Таблица соответствия русских букв
RUSSIAN_LETTERS = {
    'А': 1, 'Б': 2, 'В': 3, 'Г': 4, 'Д': 5, 'Е': 6, 'Ё': 7, 'Ж': 8, 'З': 9,
    'И': 1, 'Й': 2, 'К': 3, 'Л': 4, 'М': 5, 'Н': 6, 'О': 7, 'П': 8, 'Р': 9,
    'С': 1, 'Т': 2, 'У': 3, 'Ф': 4, 'Х': 5, 'Ц': 6, 'Ч': 7, 'Ш': 8, 'Щ': 9,
    'Ъ': 1, 'Ы': 2, 'Ь': 3, 'Э': 4, 'Ю': 5, 'Я': 6
}

# Таблица соответствия латинских букв
LATIN_LETTERS = {
    'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8, 'I': 9,
    'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'O': 6, 'P': 7, 'Q': 8, 'R': 9,
    'S': 1, 'T': 2, 'U': 3, 'V': 4, 'W': 5, 'X': 6, 'Y': 7, 'Z': 8
}

def calculate_expression_number(name: str) -> int:
    """
    Рассчитывает число экспрессии для имени.
    Суммирует все цифры букв и сводит к одной цифре (1-9).
    """
    name_upper = name.upper().strip()
    total = 0
    
    for char in name_upper:
        if char in RUSSIAN_LETTERS:
            total += RUSSIAN_LETTERS[char]
        elif char in LATIN_LETTERS:
            total += LATIN_LETTERS[char]
        # Игнорируем пробелы, дефисы и другие символы
    
    # Сводим к одной цифре (1-9)
    while total > 9 and total not in [11, 22, 33]:  # Мастер-числа можно оставить как есть
        total = sum(int(d) for d in str(total))
    
    return total

def calculate_life_path_number(birth_date: date) -> int:
    """
    Рассчитывает число жизненного пути из даты рождения.
    Суммирует все цифры даты до получения одной цифры (1-9) или мастер-числа (11, 22, 33).
    Пример: 15.04.1985 = 1+5+0+4+1+9+8+5 = 33 (мастер-число)
    """
    day_str = str(birth_date.day).zfill(2)
    month_str = str(birth_date.month).zfill(2)
    year_str = str(birth_date.year)
    
    # Суммируем все цифры даты
    total = sum(int(d) for d in day_str + month_str + year_str)
    
    # Сводим к одной цифре, но сохраняем мастер-числа
    while total > 9 and total not in [11, 22, 33]:
        total = sum(int(d) for d in str(total))
    
    return total

def parse_name_and_date(text: str) -> Optional[tuple[str, Optional[date]]]:
    """
    Парсит имя и дату рождения из текста.
    Форматы: "Иван, 15.04.1985" или "Иван 15.04.1985"
    Возвращает (имя, дата) или None если не удалось распарсить
    """
    text = text.strip()
    
    # Пробуем формат "Имя, ДД.ММ.ГГГГ"
    match = re.match(r'^([а-яА-ЯёЁa-zA-Z]+)\s*[,]\s*(\d{2}[.\-/]\d{2}[.\-/]\d{4})$', text, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        date_str = match.group(2).strip()
        # Нормализуем разделители даты
        date_str = re.sub(r'[.\-/]', '.', date_str)
        try:
            bdate = datetime.strptime(date_str, "%d.%m.%Y").date()
            return (name, bdate)
        except ValueError:
            pass
    
    # Пробуем формат "Имя ДД.ММ.ГГГГ" (без запятой)
    match = re.match(r'^([а-яА-ЯёЁa-zA-Z]+)\s+(\d{2}[.\-/]\d{2}[.\-/]\d{4})$', text, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        date_str = match.group(2).strip()
        date_str = re.sub(r'[.\-/]', '.', date_str)
        try:
            bdate = datetime.strptime(date_str, "%d.%m.%Y").date()
            return (name, bdate)
        except ValueError:
            pass
    
    return None

def extract_names_and_dates(text: str) -> Optional[tuple[str, Optional[date], str, Optional[date]]]:
    """
    Извлекает два имени и две даты из текста.
    Форматы: "Иван, 15.04.1985 и Мария, 22.07.1992"
    Возвращает (имя1, дата1, имя2, дата2) или None
    """
    text = text.strip()
    
    # Разделяем по "и"
    parts = re.split(r'\s+и\s+', text, flags=re.IGNORECASE)
    if len(parts) == 2:
        part1 = parse_name_and_date(parts[0].strip())
        part2 = parse_name_and_date(parts[1].strip())
        if part1 and part2:
            return (part1[0], part1[1], part2[0], part2[1])
    
    return None

def analyze_compatibility(expr1: int, expr2: int, path1: int, path2: int) -> dict:
    """
    Анализирует совместимость по числам экспрессии и жизненного пути.
    Возвращает словарь с оценками совместимости.
    """
    harmonious_pairs = [(1, 2), (2, 4), (3, 6), (4, 8), (5, 7)]
    conflict_pairs = [(1, 1), (3, 4)]
    
    def is_harmonious(a: int, b: int) -> bool:
        return (a, b) in harmonious_pairs or (b, a) in harmonious_pairs
    
    def is_conflict(a: int, b: int) -> bool:
        return (a, b) in conflict_pairs or (b, a) in conflict_pairs
    
    def is_karmic(a: int, b: int) -> bool:
        return abs(a - b) >= 5
    
    expr_compatibility = "гармоничная" if is_harmonious(expr1, expr2) else ("конфликтная" if is_conflict(expr1, expr2) else ("кармическая" if is_karmic(expr1, expr2) else "нейтральная"))
    path_compatibility = "гармоничная" if is_harmonious(path1, path2) else ("конфликтная" if is_conflict(path1, path2) else ("кармическая" if is_karmic(path1, path2) else "нейтральная"))
    
    return {
        "expr_compatibility": expr_compatibility,
        "path_compatibility": path_compatibility,
        "expr1": expr1,
        "expr2": expr2,
        "path1": path1,
        "path2": path2
    }

def extract_names_from_text(text: str) -> List[str]:
    """
    Извлекает имена из текста пользователя.
    Поддерживает форматы: "Иван и Мария", "Иван, Мария", "Иван Мария"
    """
    text = text.strip()
    original_text = text
    
    # Сначала пробуем разделить по "и" (с учетом регистра)
    if re.search(r'\s+и\s+', text, flags=re.IGNORECASE):
        parts = re.split(r'\s+и\s+', text, flags=re.IGNORECASE)
        names = []
        for part in parts:
            part = part.strip()
            # Убираем запятые и другие знаки препинания
            part = re.sub(r'[^\w\sа-яА-ЯёЁa-zA-Z]', '', part)
            # Берем первое слово
            words = part.split()
            if words and words[0].isalpha() and len(words[0]) > 1:
                names.append(words[0])
        if len(names) >= 2:
            return names[:2]
    
    # Если не получилось, пробуем по запятой
    if ',' in text:
        parts = text.split(',')
        names = []
        for part in parts:
            part = re.sub(r'[^\w\sа-яА-ЯёЁa-zA-Z]', ' ', part).strip()
            words = part.split()
            if words and words[0].isalpha() and len(words[0]) > 1:
                names.append(words[0])
        if len(names) >= 2:
            return names[:2]
    
    # Если не получилось, пробуем просто разделить по пробелам
    words = re.findall(r'\b[а-яА-ЯёЁa-zA-Z]{2,}\b', text)
    if len(words) >= 2:
        return words[:2]
    elif len(words) == 1:
        return words
    
    return []

# --- База Данных ---

def _init_user_db():
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY, username TEXT, 
            credits INTEGER DEFAULT 100, subscription_end TEXT,
            dream_requests INTEGER DEFAULT 0, created_at TEXT,
            test_msg_2days_sent INTEGER DEFAULT 0, test_msg_1week_sent INTEGER DEFAULT 0,
            blocked INTEGER DEFAULT 0, language TEXT DEFAULT 'ru')''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY, telegram_id INTEGER, username TEXT,
            sparks INTEGER, amount INTEGER, status TEXT, credited INTEGER DEFAULT 0,
            created_at TEXT, is_subscription INTEGER DEFAULT 0, subscription_days INTEGER)''')
        conn.commit()
    _ensure_columns()

def _ensure_columns():
    with sqlite3.connect(USER_DB_PATH) as conn:
        cols = [c[1] for c in conn.execute("PRAGMA table_info(users)").fetchall()]
        for col in ["created_at", "test_msg_2days_sent", "test_msg_1week_sent", "blocked", "language"]:
            if col not in cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {'TEXT' if 'at' in col or 'lang' in col else 'INTEGER DEFAULT 0'}")
        conn.commit()

def _normalize_username(user) -> str:
    return getattr(user, "username", None) or f"user_{user.id}"

def _get_user_row(tid: int) -> Optional[sqlite3.Row]:
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM users WHERE telegram_id = ?", (tid,)).fetchone()

def get_or_create_user(tid: int, username: str, lang: str = 'ru') -> int:
    row = _get_user_row(tid)
    if row:
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute("UPDATE users SET username = ? WHERE telegram_id = ?", (username, tid))
        return row["credits"]
    
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute("INSERT INTO users (telegram_id, username, credits, created_at, language) VALUES (?, ?, ?, ?, ?)",
                     (tid, username, STARTING_SPARKS, datetime.utcnow().isoformat(), lang))
    return STARTING_SPARKS

def deduct_user_sparks(tid: int, amount: int) -> int:
    row = _get_user_row(tid)
    if not row: return 0
    new_bal = max(row["credits"] - amount, 0)
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute("UPDATE users SET credits = ? WHERE telegram_id = ?", (new_bal, tid))
    return new_bal

def add_user_sparks(tid: int, username: str, amount: int) -> int:
    row = _get_user_row(tid)
    if row:
        new_bal = row["credits"] + amount
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute("UPDATE users SET credits = ?, username = ? WHERE telegram_id = ?", (new_bal, username, tid))
        return new_bal
    get_or_create_user(tid, username)
    return add_user_sparks(tid, username, amount)

# --- Подписки ---

def ensure_subscription_state(tid: int):
    row = _get_user_row(tid)
    if not row or not row["subscription_end"]: return
    if datetime.utcnow() >= datetime.fromisoformat(row["subscription_end"]):
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute("UPDATE users SET credits = 0, subscription_end = NULL WHERE telegram_id = ?", (tid,))

def has_active_subscription(tid: int) -> bool:
    ensure_subscription_state(tid)
    row = _get_user_row(tid)
    if not row or not row["subscription_end"]: return False
    return datetime.utcnow() < datetime.fromisoformat(row["subscription_end"])

def activate_subscription(tid: int, username: str, sparks: int, days: int):
    end_at = (datetime.utcnow() + timedelta(days=days)).isoformat()
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute("INSERT INTO users (telegram_id, username, credits, subscription_end) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT(telegram_id) DO UPDATE SET credits=excluded.credits, subscription_end=excluded.subscription_end",
                     (tid, username, sparks, end_at))

# --- Клавиатуры ---

def get_main_menu_keyboard(tid: int, update: Update = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_msg(tid, "option_names_dates", update), callback_data='check_names_dates')],
        [InlineKeyboardButton(get_msg(tid, "option_names_only", update), callback_data='check_names_only')],
        [InlineKeyboardButton(get_msg(tid, "buy_sparks_button", update), callback_data='buy_sparks')]
    ])

def get_buy_sparks_keyboard(tid: int, has_sub: bool, update: Update = None) -> InlineKeyboardMarkup:
    rows = []
    if not has_sub:
        rows.extend([[InlineKeyboardButton(p["label"], callback_data=k)] for k, p in SUBSCRIPTION_PACKAGES.items()])
    else:
        rows.append([InlineKeyboardButton(TOP_UP_PACKAGES["topup_50"]["label"], callback_data="topup_50"),
                     InlineKeyboardButton(TOP_UP_PACKAGES["topup_100"]["label"], callback_data="topup_100")])
    rows.append([InlineKeyboardButton(get_msg(tid, "back_button", update), callback_data='back_to_menu')])
    return InlineKeyboardMarkup(rows)

def get_back_to_menu_keyboard(tid: int, update: Update = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(get_msg(tid, "back_button", update), callback_data='back_to_menu')]])

def get_interpret_another_dream_keyboard(tid: int, update: Update = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_msg(tid, "option_names_dates", update), callback_data='check_names_dates')],
        [InlineKeyboardButton(get_msg(tid, "option_names_only", update), callback_data='check_names_only')],
        [InlineKeyboardButton(get_msg(tid, "back_button", update), callback_data='back_to_menu')]
    ])

def get_quick_top_up_keyboard(tid: int, update: Update = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_msg(tid, "quick_topup_button", update), callback_data="quick_topup_5")],
        [InlineKeyboardButton(get_msg(tid, "back_button", update), callback_data='back_to_menu')]
    ])

# --- Хелперы для отправки сообщений ---

async def send_long_message(bot, chat_id, text: str, reply_markup=None, parse_mode=None, first_msg=None):
    """
    Отправляет длинное сообщение, разбивая его на части если превышает лимит Telegram (4096 символов).
    Если передан first_msg, редактирует его первым фрагментом, остальные отправляет как новые сообщения.
    """
    MAX_LENGTH = 4096
    
    if len(text) <= MAX_LENGTH:
        if first_msg:
            await first_msg.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        else:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode, reply_markup=reply_markup)
        return
    
    # Разбиваем текст на части
    parts = []
    
    # Простое разбиение по лимиту символов, стараясь не разрывать слова
    while len(text) > MAX_LENGTH:
        # Пробуем найти последний перенос строки в пределах лимита
        cut_pos = MAX_LENGTH
        last_newline = text.rfind('\n', 0, MAX_LENGTH)
        if last_newline > MAX_LENGTH * 0.8:  # Если перенос строки не слишком близко к началу
            cut_pos = last_newline + 1
        else:
            # Пробуем найти последнюю точку с пробелом
            last_dot = text.rfind('. ', 0, MAX_LENGTH)
            if last_dot > MAX_LENGTH * 0.8:
                cut_pos = last_dot + 2
            else:
                # Пробуем найти последний пробел
                last_space = text.rfind(' ', 0, MAX_LENGTH)
                if last_space > MAX_LENGTH * 0.7:
                    cut_pos = last_space + 1
        
        parts.append(text[:cut_pos])
        text = text[cut_pos:]
    
    # Добавляем оставшуюся часть
    if text:
        parts.append(text)
    
    # Отправляем части
    for i, part in enumerate(parts):
        if i == 0 and first_msg:
            # Первую часть редактируем в существующее сообщение
            await first_msg.edit_text(part, parse_mode=parse_mode)
        else:
            # Остальные отправляем как новые сообщения
            # Клавиатуру добавляем только к последнему сообщению
            markup = reply_markup if i == len(parts) - 1 else None
            await bot.send_message(chat_id=chat_id, text=part, parse_mode=parse_mode, reply_markup=markup)

# --- Хендлеры ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_user_lang(user.id, update)
    get_or_create_user(user.id, _normalize_username(user), lang)
    await update.message.reply_text(f"{get_msg(user.id, 'intro', update)}\n\n{get_msg(user.id, 'welcome', update)}",
                                   parse_mode='Markdown', reply_markup=get_main_menu_keyboard(user.id, update))

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tid = query.from_user.id
    ensure_subscription_state(tid)
    has_sub = has_active_subscription(tid)

    if query.data == 'check_names_dates':
        await query.edit_message_text(get_msg(tid, "prompt_names_dates_name1", query),
                                     reply_markup=get_back_to_menu_keyboard(tid, query))
        return STATE_WAITING_NAMES_DATES_NAME1
    
    if query.data == 'check_names_only':
        await query.edit_message_text(get_msg(tid, "prompt_name1", query),
                                     reply_markup=get_back_to_menu_keyboard(tid, query))
        return STATE_WAITING_NAME1
    

    if query.data == 'buy_sparks':
        txt = get_msg(tid, "purchase_title", query)
        await query.edit_message_text(txt, reply_markup=get_buy_sparks_keyboard(tid, has_sub, query))
        return ConversationHandler.END

    if query.data == 'back_to_menu':
        await query.edit_message_text(get_msg(tid, "welcome", query), reply_markup=get_main_menu_keyboard(tid, query))
        return ConversationHandler.END
    
    if query.data == "quick_topup_5":
        await start_yookassa_purchase(query, 5, 10)
    elif query.data in SUBSCRIPTION_PACKAGES:
        p = SUBSCRIPTION_PACKAGES[query.data]
        await start_yookassa_purchase(query, p["sparks"], p["amount"], is_sub=True, days=p["period_days"])
    elif query.data in TOP_UP_PACKAGES:
        p = TOP_UP_PACKAGES[query.data]
        await start_yookassa_purchase(query, p["sparks"], p["amount"])
    elif query.data.startswith('check_payment:'):
        await handle_payment_check(query, query.data.split(':', 1)[1])
    
    return ConversationHandler.END

async def compatibility_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    username = _normalize_username(update.effective_user)
    credits = get_or_create_user(tid, username)
    
    if credits < SPARK_COST:
        await update.message.reply_text(get_msg(tid, "insufficient_sparks", update), reply_markup=get_quick_top_up_keyboard(tid, update))
        return ConversationHandler.END
    
    rem = deduct_user_sparks(tid, SPARK_COST)
    await update.message.reply_text(get_msg(tid, "sparks_deducted_msg", update, amount=SPARK_COST, remaining=rem))
    
    t_msgs = get_msg(tid, "thinking", update)
    t_text = random.choice(t_msgs) if isinstance(t_msgs, list) else t_msgs
    msg = await update.message.reply_text(f"<i>{t_text}</i>", parse_mode='HTML')
    
    try:
        resp = requests.post(OPENROUTER_URL, headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}, 
                             json={"model": MODEL, "messages": [{"role": "user", "content": update.message.text}]})
        ai_txt = resp.json()['choices'][0]['message']['content']
        await send_long_message(context.bot, update.effective_chat.id, ai_txt, 
                               reply_markup=get_interpret_another_dream_keyboard(tid, update),
                               first_msg=msg)
        await update.message.reply_text(get_msg(tid, "back_to_menu_msg", update), reply_markup=get_interpret_another_dream_keyboard(tid, update))
    except Exception as e:
        logger.error(f"AI error: {e}")
        await msg.edit_text(get_msg(tid, "ai_error", update))
    return ConversationHandler.END

async def names_dates_name1_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик первого имени для опции 'Имена + даты рождения'"""
    tid = update.effective_user.id
    name1 = update.message.text.strip()
    
    # Сохраняем первое имя в контексте
    context.user_data['names_dates_name1'] = name1
    
    await update.message.reply_text(get_msg(tid, "prompt_names_dates_date1", update),
                                   reply_markup=get_back_to_menu_keyboard(tid, update))
    return STATE_WAITING_NAMES_DATES_DATE1

async def names_dates_date1_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик первой даты рождения"""
    tid = update.effective_user.id
    
    # Парсим дату
    date_str = update.message.text.strip()
    date_str = re.sub(r'[.\-/]', '.', date_str)
    try:
        date1 = datetime.strptime(date_str, "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(get_msg(tid, "invalid_date_format", update),
                                       reply_markup=get_back_to_menu_keyboard(tid, update))
        return STATE_WAITING_NAMES_DATES_DATE1
    
    # Сохраняем первую дату в контексте
    context.user_data['names_dates_date1'] = date1
    
    await update.message.reply_text(get_msg(tid, "prompt_names_dates_name2", update),
                                   reply_markup=get_back_to_menu_keyboard(tid, update))
    return STATE_WAITING_NAMES_DATES_NAME2

async def names_dates_name2_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик второго имени"""
    tid = update.effective_user.id
    name2 = update.message.text.strip()
    
    # Сохраняем второе имя в контексте
    context.user_data['names_dates_name2'] = name2
    
    await update.message.reply_text(get_msg(tid, "prompt_names_dates_date2", update),
                                   reply_markup=get_back_to_menu_keyboard(tid, update))
    return STATE_WAITING_NAMES_DATES_DATE2

async def names_dates_date2_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик второй даты рождения и запуск анализа"""
    tid = update.effective_user.id
    username = _normalize_username(update.effective_user)
    credits = get_or_create_user(tid, username)
    
    if credits < SPARK_COST:
        await update.message.reply_text(get_msg(tid, "insufficient_sparks", update), reply_markup=get_quick_top_up_keyboard(tid, update))
        return ConversationHandler.END
    
    # Парсим вторую дату
    date_str = update.message.text.strip()
    date_str = re.sub(r'[.\-/]', '.', date_str)
    try:
        date2 = datetime.strptime(date_str, "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(get_msg(tid, "invalid_date_format", update),
                                       reply_markup=get_back_to_menu_keyboard(tid, update))
        return STATE_WAITING_NAMES_DATES_DATE2
    
    # Получаем данные из контекста
    name1 = context.user_data.get('names_dates_name1', '')
    date1 = context.user_data.get('names_dates_date1')
    name2 = context.user_data.get('names_dates_name2', '')
    
    # Очищаем контекст
    context.user_data.pop('names_dates_name1', None)
    context.user_data.pop('names_dates_date1', None)
    context.user_data.pop('names_dates_name2', None)
    
    if not name1 or not date1 or not name2:
        await update.message.reply_text(get_msg(tid, "error_missing_data", update),
                                       reply_markup=get_back_to_menu_keyboard(tid, update))
        return ConversationHandler.END
    
    rem = deduct_user_sparks(tid, SPARK_COST)
    await update.message.reply_text(get_msg(tid, "sparks_deducted_msg", update, amount=SPARK_COST, remaining=rem))
    
    # Рассчитываем числа экспрессии и жизненного пути
    expr1 = calculate_expression_number(name1)
    expr2 = calculate_expression_number(name2)
    path1 = calculate_life_path_number(date1)
    path2 = calculate_life_path_number(date2)
    
    # Анализируем совместимость
    compatibility = analyze_compatibility(expr1, expr2, path1, path2)
    
    t_msgs = get_msg(tid, "thinking", update)
    t_text = random.choice(t_msgs) if isinstance(t_msgs, list) else t_msgs
    msg = await update.message.reply_text(f"<i>{t_text}</i>", parse_mode='HTML')
    
    # Формируем промпт с данными
    date1_str = date1.strftime("%d.%m.%Y")
    date2_str = date2.strftime("%d.%m.%Y")
    
    prompt_data = f"""Имя1: {name1}
др1: {date1_str}
Число экспрессии1: {expr1}
Число жизненного пути1: {path1}
Имя2: {name2}
др2: {date2_str}
Число экспрессии2: {expr2}
Число жизненного пути2: {path2}
Оценка совместимости по экспрессии: {compatibility['expr_compatibility']}
Оценка совместимости по жизненному пути: {compatibility['path_compatibility']}"""
    
    # Получаем шаблон промпта
    lang = get_user_lang(tid, update)
    lang_msgs = MESSAGES.get(lang, MESSAGES.get("ru", {}))
    prompt_template = lang_msgs.get("prompt_names_dates_ai", MESSAGES.get("ru", {}).get("prompt_names_dates_ai", ""))
    
    # Форматируем промпт
    try:
        prompt = prompt_template.format(
            user_input=f"{name1}, {date1_str} и {name2}, {date2_str}",
            compatibility_data=prompt_data
        )
    except KeyError:
        # Если шаблон не содержит все ключи, добавляем данные вручную
        prompt = f"{prompt_template}\n\n{prompt_data}".replace("{user_input}", f"{name1}, {date1_str} и {name2}, {date2_str}")
    
    try:
        resp = requests.post(OPENROUTER_URL, headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}, 
                             json={"model": MODEL, "messages": [{"role": "user", "content": prompt}]})
        ai_txt = resp.json()['choices'][0]['message']['content']
        await send_long_message(context.bot, update.effective_chat.id, ai_txt,
                               reply_markup=get_interpret_another_dream_keyboard(tid, update),
                               first_msg=msg)
        await update.message.reply_text(get_msg(tid, "back_to_menu_msg", update), reply_markup=get_interpret_another_dream_keyboard(tid, update))
    except Exception as e:
        logger.error(f"AI error: {e}")
        await msg.edit_text(get_msg(tid, "ai_error", update))
    return ConversationHandler.END

async def name1_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик первого имени"""
    tid = update.effective_user.id
    name1 = update.message.text.strip()
    
    # Сохраняем первое имя в контексте
    context.user_data['name1'] = name1
    
    await update.message.reply_text(get_msg(tid, "prompt_name2", update),
                                   reply_markup=get_back_to_menu_keyboard(tid, update))
    return STATE_WAITING_NAME2

async def name2_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик второго имени и запуск анализа"""
    tid = update.effective_user.id
    username = _normalize_username(update.effective_user)
    credits = get_or_create_user(tid, username)
    
    if credits < SPARK_COST:
        await update.message.reply_text(get_msg(tid, "insufficient_sparks", update), reply_markup=get_quick_top_up_keyboard(tid, update))
        return ConversationHandler.END
    
    rem = deduct_user_sparks(tid, SPARK_COST)
    await update.message.reply_text(get_msg(tid, "sparks_deducted_msg", update, amount=SPARK_COST, remaining=rem))
    
    # Получаем первое имя из контекста
    name1 = context.user_data.get('name1', '')
    name2 = update.message.text.strip()
    
    # Очищаем контекст
    context.user_data.pop('name1', None)
    
    # Рассчитываем числа экспрессии
    expr1 = calculate_expression_number(name1)
    expr2 = calculate_expression_number(name2)
    
    # Формируем промпт с числами экспрессии
    prompt_data = f"Имя 1: {name1}\nЧисло экспрессии: {expr1}\nИмя 2: {name2}\nЧисло экспрессии: {expr2}"
    
    t_msgs = get_msg(tid, "thinking", update)
    t_text = random.choice(t_msgs) if isinstance(t_msgs, list) else t_msgs
    msg = await update.message.reply_text(f"<i>{t_text}</i>", parse_mode='HTML')
    
    # Получаем шаблон напрямую из словаря сообщений без форматирования
    lang = get_user_lang(tid, update)
    lang_msgs = MESSAGES.get(lang, MESSAGES.get("ru", {}))
    prompt_template = lang_msgs.get("prompt_names_only_ai", MESSAGES.get("ru", {}).get("prompt_names_only_ai", ""))
    
    # Форматируем промпт с нужными параметрами
    try:
        prompt = prompt_template.format(
            user_input=f"{name1} и {name2}",
            expression_data=prompt_data
        )
    except KeyError:
        # Если шаблон не содержит все ключи, добавляем данные вручную
        prompt = prompt_template.replace("{user_input}", f"{name1} и {name2}").replace("{expression_data}", prompt_data)
        if "{expression_data}" in prompt_template or "{user_input}" in prompt_template:
            # Если есть незамененные ключи, используем безопасное форматирование
            prompt = f"{prompt_template}\n\n{prompt_data}".replace("{user_input}", f"{name1} и {name2}")
    
    try:
        resp = requests.post(OPENROUTER_URL, headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}, 
                             json={"model": MODEL, "messages": [{"role": "user", "content": prompt}]})
        ai_txt = resp.json()['choices'][0]['message']['content']
        await send_long_message(context.bot, update.effective_chat.id, ai_txt,
                               reply_markup=get_interpret_another_dream_keyboard(tid, update),
                               first_msg=msg)
        await update.message.reply_text(get_msg(tid, "back_to_menu_msg", update), reply_markup=get_interpret_another_dream_keyboard(tid, update))
    except Exception as e:
        logger.error(f"AI error: {e}")
        await msg.edit_text(get_msg(tid, "ai_error", update))
    return ConversationHandler.END

async def find_pair_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    username = _normalize_username(update.effective_user)
    credits = get_or_create_user(tid, username)
    
    if credits < SPARK_COST:
        await update.message.reply_text(get_msg(tid, "insufficient_sparks", update), reply_markup=get_quick_top_up_keyboard(tid, update))
        return ConversationHandler.END
    
    rem = deduct_user_sparks(tid, SPARK_COST)
    await update.message.reply_text(get_msg(tid, "sparks_deducted_msg", update, amount=SPARK_COST, remaining=rem))
    
    t_msgs = get_msg(tid, "thinking", update)
    t_text = random.choice(t_msgs) if isinstance(t_msgs, list) else t_msgs
    msg = await update.message.reply_text(f"<i>{t_text}</i>", parse_mode='HTML')
    
    prompt = get_msg(tid, "prompt_find_pair_ai", update).format(user_input=update.message.text)
    
    try:
        resp = requests.post(OPENROUTER_URL, headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}, 
                             json={"model": MODEL, "messages": [{"role": "user", "content": prompt}]})
        ai_txt = resp.json()['choices'][0]['message']['content']
        await send_long_message(context.bot, update.effective_chat.id, ai_txt,
                               reply_markup=get_interpret_another_dream_keyboard(tid, update),
                               first_msg=msg)
        await update.message.reply_text(get_msg(tid, "back_to_menu_msg", update), reply_markup=get_interpret_another_dream_keyboard(tid, update))
    except Exception as e:
        logger.error(f"AI error: {e}")
        await msg.edit_text(get_msg(tid, "ai_error", update))
    return ConversationHandler.END

# --- YooKassa Helpers ---

async def start_yookassa_purchase(query, sparks, amount, is_sub=False, days=None):
    user = query.from_user
    try:
        meta = {"is_subscription": "1" if is_sub else "0"}
        if days: meta["subscription_days"] = str(days)
        payload = {
            "amount": {"value": f"{amount}.00", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": YOOKASSA_RETURN_URL},
            "capture": True,
            "metadata": {"telegram_id": str(user.id), "sparks": str(sparks), **meta},
            "description": f"Пополнение искр: {sparks}",
            "receipt": {
                "customer": {"email": "test@test.ru"},
                "items": [
                    {
                        "description": f"Искры: {sparks}",
                        "quantity": "1.00",
                        "amount": {"value": f"{amount}.00", "currency": "RUB"},
                        "vat_code": "1",
                        "payment_subject": "service",
                        "payment_mode": "full_payment"
                    }
                ]
            }
        }
        payment = Payment.create(payload, uuid.uuid4().hex)
        
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute("INSERT INTO payments (payment_id, telegram_id, username, sparks, amount, status, created_at, is_subscription, subscription_days) VALUES (?,?,?,?,?,?,?,?,?)",
                         (payment.id, user.id, _normalize_username(user), sparks, amount, payment.status, datetime.utcnow().isoformat(), int(is_sub), days))
        
        url = payment.confirmation.confirmation_url
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Оплатить", url=url)], 
                                   [InlineKeyboardButton("✅ Я оплатил", callback_data=f"check_payment:{payment.id}")]])
        await query.edit_message_text(get_msg(user.id, "payment_waiting", query), reply_markup=kb)
    except Exception as e:
        logger.error(f"Yookassa error: {e}")
        await query.answer("Ошибка платежной системы", show_alert=True)

async def handle_payment_check(query, pid):
    payment = Payment.find_one(pid)
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute("UPDATE payments SET status = ? WHERE payment_id = ?", (payment.status, pid))
    
    row = sqlite3.connect(USER_DB_PATH).execute("SELECT * FROM payments WHERE payment_id = ?", (pid,)).fetchone()
    if payment.status == "succeeded" and row and not row[6]: # 6 is credited
        if row[8]: # is_subscription
            activate_subscription(row[1], row[2], row[3], row[9])
        else:
            add_user_sparks(row[1], row[2], row[3])
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute("UPDATE payments SET credited = 1 WHERE payment_id = ?", (pid,))
        await query.edit_message_text(get_msg(row[1], "payment_success", query), reply_markup=get_main_menu_keyboard(row[1], query))
    else:
        await query.answer(f"Статус: {payment.status}", show_alert=True)

# --- Main ---

STATE_WAITING_DESCRIPTION = 1
STATE_WAITING_NAMES_DATES_NAME1 = 2
STATE_WAITING_NAMES_DATES_DATE1 = 3
STATE_WAITING_NAMES_DATES_NAME2 = 4
STATE_WAITING_NAMES_DATES_DATE2 = 5
STATE_WAITING_NAME1 = 6
STATE_WAITING_NAME2 = 7

def main():
    _init_user_db()
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ Токен не установлен!")
        return
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler)],
        states={
            STATE_WAITING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, compatibility_handler)],
            STATE_WAITING_NAMES_DATES_NAME1: [MessageHandler(filters.TEXT & ~filters.COMMAND, names_dates_name1_handler)],
            STATE_WAITING_NAMES_DATES_DATE1: [MessageHandler(filters.TEXT & ~filters.COMMAND, names_dates_date1_handler)],
            STATE_WAITING_NAMES_DATES_NAME2: [MessageHandler(filters.TEXT & ~filters.COMMAND, names_dates_name2_handler)],
            STATE_WAITING_NAMES_DATES_DATE2: [MessageHandler(filters.TEXT & ~filters.COMMAND, names_dates_date2_handler)],
            STATE_WAITING_NAME1: [MessageHandler(filters.TEXT & ~filters.COMMAND, name1_handler)],
            STATE_WAITING_NAME2: [MessageHandler(filters.TEXT & ~filters.COMMAND, name2_handler)]
        },
        fallbacks=[CommandHandler('start', start)]
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(menu_handler))
    
    logger.info("Bot Sovmestimost started")
    app.run_polling()

if __name__ == '__main__':
    main()
