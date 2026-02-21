import asyncio
from telegram import Bot
from telegram.error import TelegramError

async def test_send():
    bot = Bot(token='8235907989:AAGXZyv5PLV2vE_5FCQHIFaJiIJBSD96PPw')
    try:
        # Попробуем получить информацию о чате
        chat = await bot.get_chat(chat_id=495514905)
        print(f'Chat info: {chat}')

        # Отправим сообщение
        await bot.send_message(chat_id=495514905, text='Test message from numerology integration')
        print('Message sent successfully')
    except TelegramError as e:
        print(f'Telegram error: {e}')
    except Exception as e:
        print(f'Other error: {e}')

if __name__ == '__main__':
    asyncio.run(test_send())