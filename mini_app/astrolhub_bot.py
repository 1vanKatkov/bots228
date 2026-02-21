"""
Бот @astrolhub_bot — Mini App. Открывает приложение по кнопке.
При первом /start пользователь создаётся в приложении с 100 искрами.
Токен: ASTROLHUB_BOT_TOKEN в .env
"""
import asyncio
import os
import logging
from pathlib import Path

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("ASTROLHUB_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://astrolhub.onrender.com/").rstrip("/")


def _ensure_user_has_sparks(telegram_id: int, username: str = None) -> int:
    """Создаёт пользователя в Mini App при первом сообщении (100 искр). Возвращает баланс."""
    try:
        payload = {"telegram_id": telegram_id}
        if username:
            payload["username"] = username
        r = requests.post(
            f"{MINI_APP_URL}/api/balance",
            data=payload,
            timeout=10,
        )
        if r.ok:
            return r.json().get("balance", 100)
    except Exception as e:
        logger.warning("Не удалось создать пользователя в Mini App: %s", e)
    return 100


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user:
        balance = await asyncio.to_thread(
            _ensure_user_has_sparks, user.id, (user.username or "").strip() or None
        )
        welcome = (
            "Добро пожаловать в AstrolHub.\n\n"
            f"На вашем счёте {balance} искр. Нажмите кнопку ниже, чтобы открыть приложение."
        )
    else:
        welcome = "Добро пожаловать в AstrolHub.\n\nНажмите кнопку ниже, чтобы открыть приложение."
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ Открыть приложение", web_app=WebAppInfo(url=MINI_APP_URL))],
    ])
    await update.message.reply_text(welcome, reply_markup=keyboard)


def main() -> None:
    if not BOT_TOKEN:
        logger.error("Задайте ASTROLHUB_BOT_TOKEN или TELEGRAM_BOT_TOKEN в .env")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
