import logging
import asyncio
import os
import random
import re
import sqlite3
import uuid
import json
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from dotenv import load_dotenv
from yookassa import Configuration, Payment

from report_generator import (
    calculate_action_number,
    calculate_character_number,
    calculate_consciousness_number,
    calculate_destiny_number,
    calculate_energy_number,
    generate_numerology_report_pdf,
)

# --- Аргументы командной строки ---
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="Bot token")
    parser.add_argument("--messages", help="Path to messages.json")
    parser.add_argument("--test", action="store_true", help="Run in test mode (test DB and test Yookassa)")
    parser.add_argument("--lang", help="Force fixed language (ru, en, es)")
    return parser.parse_known_args()[0]

args = parse_args()

# Настройка логирования
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_file = Path(__file__).resolve().parent.parent / "logs" / ("numerology_bot_test.log" if args.test else "numerology_bot.log")
(Path(__file__).resolve().parent.parent / "logs").mkdir(exist_ok=True)

from logging.handlers import RotatingFileHandler
file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)

# Загрузка сообщений из JSON
def load_messages():
    messages_path = Path(args.messages or (Path(__file__).resolve().parent / "messages.json"))
    if not messages_path.exists():
        messages_path = Path(__file__).resolve().parent / "messages.json"
    
    if not messages_path.exists():
        logger.error(f"Файл {messages_path} не найден!")
        return {}
    with open(messages_path, "r", encoding="utf-8") as f:
        return json.load(f)

MESSAGES = load_messages()

load_dotenv()

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID_TEST" if args.test else "YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY_TEST" if args.test else "YOOKASSA_SECRET_KEY")
YOOKASSA_ACCOUNT_ID = os.getenv("YOOKASSA_ACCOUNT_ID_TEST" if args.test else "YOOKASSA_ACCOUNT_ID")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "https://t.me/your_bot_username")
# Тестовый режим Юкассы
YOOKASSA_TEST_MODE = "1" if args.test else os.getenv("YOOKASSA_TEST_MODE", "1")

if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
    Configuration.configure(
        shop_id=YOOKASSA_SHOP_ID,
        secret_key=YOOKASSA_SECRET_KEY,
        account_id=YOOKASSA_SHOP_ID,  # account_id обычно совпадает с shop_id
    )

# Переключение базы данных в тестовом режиме
USER_DB_PATH = Path(__file__).resolve().parent / ("sonnik_users_test.db" if args.test else "sonnik_users.db")
STARTING_SPARKS = 5
SPARK_COST = 5

TELEGRAM_BOT_TOKEN = args.token or os.getenv("TELEGRAM_BOT_TOKEN")

SPARK_PACKAGES = {
    "sparks_10": {"sparks": 10, "amount": 19, "label": "10 искр — 19₽"},
    "sparks_50": {"sparks": 50, "amount": 69, "label": "50 искр — 69₽"},
    "sparks_100": {"sparks": 100, "amount": 109, "label": "100 искр — 109₽"},
}

def get_user_lang(telegram_id: int, update: Optional[Update] = None) -> str:
    if args.lang: return args.lang
    
    with sqlite3.connect(USER_DB_PATH) as conn:
        cur = conn.execute("SELECT language FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cur.fetchone()
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
    if isinstance(msg, list): return msg
    return msg.format(**kwargs) if isinstance(msg, str) else msg

# --- БД Хелперы ---
def _init_user_db():
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, username TEXT, credits INTEGER DEFAULT 5, dream_requests INTEGER DEFAULT 0, created_at TEXT, blocked INTEGER DEFAULT 0, language TEXT DEFAULT 'ru')")
        conn.execute("CREATE TABLE IF NOT EXISTS payments (payment_id TEXT PRIMARY KEY, telegram_id INTEGER, username TEXT, sparks INTEGER, amount INTEGER, status TEXT, credited INTEGER DEFAULT 0, created_at TEXT)")
        conn.commit()
    _ensure_columns()

def _ensure_columns():
    with sqlite3.connect(USER_DB_PATH) as conn:
        cols = [c[1] for c in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "language" not in cols: conn.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'ru'")
        if "blocked" not in cols: conn.execute("ALTER TABLE users ADD COLUMN blocked INTEGER DEFAULT 0")
        if "updated_at" not in cols: conn.execute("ALTER TABLE users ADD COLUMN updated_at TEXT")
        if "first_report_at" not in cols: conn.execute("ALTER TABLE users ADD COLUMN first_report_at TEXT")
        if "last_followup_day" not in cols: conn.execute("ALTER TABLE users ADD COLUMN last_followup_day INTEGER DEFAULT -1")
        conn.commit()

def _normalize_username(user) -> str:
    return getattr(user, "username", None) or f"user_{user.id}"

def get_or_create_user(tid, username):
    now = datetime.utcnow().isoformat()
    row = sqlite3.connect(USER_DB_PATH).execute("SELECT credits FROM users WHERE telegram_id = ?", (tid,)).fetchone()
    if row:
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute("UPDATE users SET username = ?, updated_at = ? WHERE telegram_id = ?", (username, now, tid))
        return row[0]
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute("INSERT INTO users (telegram_id, username, created_at, updated_at) VALUES (?,?,?,?)", (tid, username, now, now))
    return STARTING_SPARKS

def add_user_sparks(tid: int, username: str, amount: int) -> int:
    now = datetime.utcnow().isoformat()
    row = sqlite3.connect(USER_DB_PATH).execute("SELECT credits FROM users WHERE telegram_id = ?", (tid,)).fetchone()
    if row:
        new_bal = row[0] + amount
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute("UPDATE users SET credits = ?, username = ?, updated_at = ? WHERE telegram_id = ?", (new_bal, username, now, tid))
        return new_bal
    get_or_create_user(tid, username)
    return add_user_sparks(tid, username, amount)

def deduct_user_sparks(tid: int, amount: int) -> int:
    now = datetime.utcnow().isoformat()
    row = sqlite3.connect(USER_DB_PATH).execute("SELECT credits FROM users WHERE telegram_id = ?", (tid,)).fetchone()
    if not row: return 0
    new_bal = max(row[0] - amount, 0)
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute("UPDATE users SET credits = ?, updated_at = ? WHERE telegram_id = ?", (new_bal, now, tid))
    return new_bal

def get_first_report_at(tid: int):
    row = sqlite3.connect(USER_DB_PATH).execute("SELECT first_report_at FROM users WHERE telegram_id = ?", (tid,)).fetchone()
    return row[0] if row and row[0] else None

def set_first_report_at(tid: int):
    now = datetime.utcnow().isoformat()
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute("UPDATE users SET first_report_at = ?, updated_at = ?, last_followup_day = ? WHERE telegram_id = ?", (now, now, 0, tid))

def set_last_followup_day(tid: int, day: int):
    now = datetime.utcnow().isoformat()
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute("UPDATE users SET last_followup_day = ?, updated_at = ? WHERE telegram_id = ?", (day, now, tid))

def get_last_followup_day(tid: int) -> int:
    row = sqlite3.connect(USER_DB_PATH).execute("SELECT last_followup_day FROM users WHERE telegram_id = ?", (tid,)).fetchone()
    return row[0] if row and row[0] is not None else -1

# --- Клавиатуры ---
def get_main_menu_keyboard(tid, update=None):
    return InlineKeyboardMarkup([[InlineKeyboardButton(get_msg(tid, "main_menu", update), callback_data="get_report")],
                                 [InlineKeyboardButton(get_msg(tid, "buy_sparks", update), callback_data="buy_sparks")]])

def get_buy_sparks_keyboard(tid, update=None):
    rows = [[InlineKeyboardButton(p["label"], callback_data=k)] for k, p in SPARK_PACKAGES.items()]
    rows.append([InlineKeyboardButton(get_msg(tid, "back", update), callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

def get_back_to_menu_keyboard(tid, update=None):
    return InlineKeyboardMarkup([[InlineKeyboardButton(get_msg(tid, "back", update), callback_data="back_to_menu")]])

def get_new_report_keyboard(tid, update=None):
    return InlineKeyboardMarkup([[InlineKeyboardButton(get_msg(tid, "new_report_btn", update), callback_data="get_report")],
                                 [InlineKeyboardButton(get_msg(tid, "back", update), callback_data="back_to_menu")]])

def get_learn_more_keyboard(tid, update=None):
    return InlineKeyboardMarkup([[InlineKeyboardButton(get_msg(tid, "learn_more", update), callback_data='learn_more_about_self')],
                                 [InlineKeyboardButton(get_msg(tid, "back", update), callback_data="back_to_menu")]])

# --- Хендлеры ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_or_create_user(user.id, user.username or f"user_{user.id}")
    await update.message.reply_text(get_msg(user.id, "welcome", update), parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user.id, update))

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tid = query.from_user.id
    if query.data in ["get_report", "learn_more_about_self"]:
        await query.edit_message_text(get_msg(tid, "prompt_name", query), reply_markup=get_back_to_menu_keyboard(tid, query))
        return 1 # STATE_WAITING_NAME
    if query.data == "buy_sparks":
        await query.edit_message_text(get_msg(tid, "purchase_title", query), reply_markup=get_buy_sparks_keyboard(tid, query))
    if query.data == "back_to_menu":
        await query.edit_message_text(get_msg(tid, "welcome", query), reply_markup=get_main_menu_keyboard(tid, query))
    
    if query.data in SPARK_PACKAGES:
        p = SPARK_PACKAGES[query.data]
        await start_yookassa_purchase(query, p["sparks"], p["amount"])
    elif query.data.startswith('check_payment:'):
        await handle_payment_check(query, query.data.split(':', 1)[1])
        
    return ConversationHandler.END

async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["full_name"] = update.message.text
    await update.message.reply_text(get_msg(update.effective_user.id, "prompt_birthdate", update), reply_markup=get_back_to_menu_keyboard(update.effective_user.id, update))
    return 2 # STATE_WAITING_BIRTHDATE

async def date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    username = _normalize_username(update.effective_user)
    credits = get_or_create_user(tid, username)
    
    if credits < SPARK_COST:
        await update.message.reply_text(get_msg(tid, "insufficient_sparks", update), reply_markup=get_buy_sparks_keyboard(tid, update))
        return ConversationHandler.END

    # Сначала проверяем формат даты (искры не списываем)
    try:
        bdate = datetime.strptime(update.message.text, "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(get_msg(tid, "invalid_date", update))
        return ConversationHandler.END

    # Генерируем отчёт; искры списываем только после успешной генерации
    try:
        pdf = generate_numerology_report_pdf(tid, context.user_data["full_name"], bdate)
        deduct_user_sparks(tid, SPARK_COST)
        with open(pdf, "rb") as f:
            await update.message.reply_document(f, filename="razbor.pdf", caption=get_msg(tid, "report_ready", update))
        # День 0: первое сообщение после первого разбора
        first_at = get_first_report_at(tid)
        if first_at is None:
            set_first_report_at(tid)
            await update.message.reply_text(
                get_msg(tid, "followup_day0", update),
                reply_markup=get_new_report_keyboard(tid, update)
            )
    except Exception as e:
        logger.error(f"Error generating numerology report: {e}")
        await update.message.reply_text(get_msg(tid, "report_error", update))
    return ConversationHandler.END

# --- YooKassa Helpers ---

async def start_yookassa_purchase(query, sparks, amount):
    user = query.from_user
    try:
        payload = {
            "amount": {"value": f"{amount}.00", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": YOOKASSA_RETURN_URL},
            "capture": True,
            "metadata": {"telegram_id": str(user.id), "sparks": str(sparks)},
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
            conn.execute("INSERT INTO payments (payment_id, telegram_id, username, sparks, amount, status, created_at) VALUES (?,?,?,?,?,?,?)",
                         (payment.id, user.id, _normalize_username(user), sparks, amount, payment.status, datetime.utcnow().isoformat()))
        
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
        add_user_sparks(row[1], row[2], row[3])
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute("UPDATE payments SET credited = 1 WHERE payment_id = ?", (pid,))
        await query.edit_message_text(get_msg(row[1], "payment_success", query), reply_markup=get_main_menu_keyboard(row[1], query))
    else:
        await query.answer(f"Статус: {payment.status}", show_alert=True)

def main():
    _init_user_db()
    if not TELEGRAM_BOT_TOKEN: return
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler)],
        states={1: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler)],
                2: [MessageHandler(filters.TEXT & ~filters.COMMAND, date_handler)]},
        fallbacks=[CommandHandler('start', start)]
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(menu_handler))
    app.run_polling()

if __name__ == '__main__':
    main()
