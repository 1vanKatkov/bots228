import sqlite3
import asyncio
import logging
from pathlib import Path
from telegram.ext import Application

# Настройки логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен Telegram бота (из bot_sonnik.py)



# Путь к базе данных
BASE_DIR = Path(__file__).resolve().parent
USER_DB_PATH = BASE_DIR / "sonnik_users.db"
test = True
if test:
    TELEGRAM_BOT_TOKEN = "8235907989:AAGXZyv5PLV2vE_5FCQHIFaJiIJBSD96PPw"
else:
    TELEGRAM_BOT_TOKEN = "8486829399:AAEz3zGFH3bNiSyXqyBpDzGjVNF4zh0zMzc"
def get_all_user_ids() -> list[int]:
    """Получить список всех telegram_id пользователей из базы данных."""
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT telegram_id FROM users").fetchall()
        return [row["telegram_id"] for row in rows]


async def send_notification_to_user(bot, user_id: int, message_text: str):
    """Отправить уведомление одному пользователю."""
    try:
        await bot.send_message(
            chat_id=user_id,
            text=message_text,
            parse_mode='Markdown'
        )
        logger.info(f"Уведомление отправлено пользователю {user_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
        return False


async def send_notifications_to_all_users():
    """Отправить уведомления всем пользователям."""
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Получаем список всех пользователей
    user_ids = get_all_user_ids()
    logger.info(f"Найдено {len(user_ids)} пользователей для отправки уведомлений")

    # Текст сообщения
    message_text = "А что тебе снилось сегодня?"

    # Отправляем уведомления всем пользователям
    successful_sends = 0
    failed_sends = 0
    user_ids2 = ["495514905"]

    for user_id in (user_ids2 if test else user_ids):
        success = await send_notification_to_user(application.bot, user_id, message_text)
        if success:
            successful_sends += 1
        else:
            failed_sends += 1

        # Небольшая пауза между отправками, чтобы не превысить лимиты Telegram
        await asyncio.sleep(0.1)

    logger.info(f"Отправка завершена. Успешно: {successful_sends}, Ошибок: {failed_sends}")


if __name__ == '__main__':
    asyncio.run(send_notifications_to_all_users())