"""
Скрипт рассылки отложенных сообщений нумеролога (день 2, 7, 9, 15, 18, 20, 27, 30).
Запускать по крону (например, раз в день).
"""
import os
import sys
import json
import sqlite3
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

# Путь к директории numerology
BASE_DIR = Path(__file__).resolve().parent
USER_DB_PATH = BASE_DIR / "sonnik_users.db"
MESSAGES_PATH = BASE_DIR / "messages.json"

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR.parent / ".env")
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

FOLLOWUP_DAYS = [2, 7, 9, 15, 18, 20, 27, 30]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_messages():
    if not MESSAGES_PATH.exists():
        return {}
    with open(MESSAGES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_msg(lang: str, key: str, messages: dict) -> str:
    msgs = messages.get(lang, messages.get("ru", {}))
    return msgs.get(key, messages.get("ru", {}).get(key, key))


def get_users_for_followup():
    """Пользователи, которым нужно отправить следующее сообщение по дням."""
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT telegram_id, first_report_at, last_followup_day FROM users WHERE first_report_at IS NOT NULL"
        ).fetchall()
    result = []
    now = datetime.now(timezone.utc)
    for row in rows:
        try:
            first_at = datetime.fromisoformat(row["first_report_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        if first_at.tzinfo is None:
            first_at = first_at.replace(tzinfo=timezone.utc)
        days_since = (now - first_at).days
        last_day = row["last_followup_day"] if row["last_followup_day"] is not None else -1
        for day in FOLLOWUP_DAYS:
            if days_since >= day and last_day < day:
                result.append((row["telegram_id"], day))
                break
    return result


def mark_followup_sent(telegram_id: int, day: int):
    now = datetime.utcnow().isoformat()
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            "UPDATE users SET last_followup_day = ?, updated_at = ? WHERE telegram_id = ?",
            (day, now, telegram_id),
        )


async def send_followups():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не задан")
        return

    messages = load_messages()
    app = Application.builder().token(token).build()
    to_send = get_users_for_followup()
    logger.info("К отправке: %s пользователей", len(to_send))

    for telegram_id, day in to_send:
        key = f"followup_day{day}"
        text = get_msg("ru", key, messages)
        if not text or key == text:
            logger.warning("Нет текста для %s", key)
            continue
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Новый разбор", callback_data="get_report")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")],
        ])
        try:
            await app.bot.send_message(
                chat_id=telegram_id,
                text=text,
                reply_markup=keyboard,
            )
            mark_followup_sent(telegram_id, day)
            logger.info("Отправлено пользователю %s сообщение день %s", telegram_id, day)
        except Exception as e:
            logger.error("Ошибка отправки %s день %s: %s", telegram_id, day, e)
        await asyncio.sleep(0.15)


if __name__ == "__main__":
    asyncio.run(send_followups())
