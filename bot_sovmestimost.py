import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import random

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройки OpenRouter API (из sonnik.py)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = "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"
MODEL = "@preset/sovmestimost"

# Токен Telegram бота (замените на свой токен от @BotFather)
TELEGRAM_BOT_TOKEN = "8552158630:AAG3ydFkKg5-28WBOuXO-QXH2uo2c9kov00"

start_messages = [
    "💞 Здравствуйте под сводом сердечных тайн. Я помогу разглядеть узоры вашей совместной судьбы. Расскажите о вашей паре?",

    "✨ Добро пожаловать в пространство любовных созвучий. Каждая пара — это уникальная музыка душ. Давайте услышим вашу мелодию?",

    "🌹 Приветствую вас, искательница сердечной истины. Я помогу понять глубину связи ваших душ. Что объединяет ваши сердца?",

    "🕊️ Здравствуйте, милая. Я вижу нити, связывающие сердца через время. Позвольте помочь разглядеть узор вашей совместной судьбы.",

    "💫 Добро пожаловать в сад любовных созвездий. Здесь мы читаем карту ваших сердечных путей. Расскажите о вашем спутнике?",

    "🔮 Приветствую вас у источника сердечной мудрости. Каждая встреча душ — это урок и дар. Какой урок проходят ваши сердца вместе?",

    "🌙 Здравствуйте под светом луны взаимоотношений. Я помогаю женщинам понимать язык любви их судьбы. Что говорит ваше сердце?",

    "🎴 Добро пожаловать в галерею сердечных связей. Я помогу разглядеть истинные картины ваших отношений. Что нарисовала судьба для вас двоих?",

    "🌊 Приветствую вас в океане любовных энергий. Каждая пара — это уникальное течение. Куда несет вашу лодку река чувств?",

    "🕯️ Здравствуйте в свете сердечной истины. Я помогаю разглядеть огонь, горящий между двумя душами. Какой свет дарите вы друг другу?"
]

thinking_messages = [
    "💫 Читаю узоры вашей совместной судьбы...",
    "🌹 Прислушиваюсь к музыке ваших душ...",
    "🔮 Вглядываюсь в карту ваших сердечных путей...",
    "🕊️ Слежу за нитями кармической связи...",
    "🌊 Чувствую течение ваших энергий...",
    "🎴 Раскладываю карты сердечного расклада...",
    "✨ Созерцаю танец ваших душ...",
    "🌙 Сверяю ваши созвездия...",
    "💞 Измеряю глубину вашей связи...",
    "🕯️ Ищу огонь вашего союза...",
    "🌀 Расшифровываю послания ваших сердец...",
    "🌌 Слежу за переплетением ваших судеб...",
    "📜 Читаю свиток вашей совместной истории...",
    "🔍 Ищу отголоски прошлых встреч...",
    "🌺 Вдыхаю аромат вашего союза..."
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    await update.message.reply_text(start_messages[random.randint(0, 9)]
                                    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений"""
    user_message = update.message.text

    # Отправляем сообщение "думаю..."
    thinking_message = await update.message.reply_text(thinking_messages[random.randint(0, 14)])

    try:
        # Подготовка запроса к OpenRouter API
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        }

        # Делаем запрос к API
        response = requests.post(OPENROUTER_URL, headers=headers, json=payload)
        response.raise_for_status()

        # Получаем ответ от API
        result = response.json()
        ai_response = result['choices'][0]['message']['content']

        # Редактируем сообщение "думаю..." на ответ от AI
        await thinking_message.edit_text(ai_response)

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        await thinking_message.edit_text(
            "🌀 Врата между мирами временно закрыты... Подождите, пока они вновь откроются для толкования"
        )


def main() -> None:
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем бота
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()