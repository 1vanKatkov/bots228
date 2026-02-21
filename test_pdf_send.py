import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)

from telegram import Bot
from telegram.error import TelegramError

async def test_send_file():
    bot = Bot(token='8235907989:AAGXZyv5PLV2vE_5FCQHIFaJiIJBSD96PPw')

    # Путь к PDF файлу
    pdf_path = Path('numerology/reports/razbor.pdf')

    try:
        print(f'Sending file: {pdf_path}, exists: {pdf_path.exists()}')
        if pdf_path.exists():
            print(f'File size: {pdf_path.stat().st_size} bytes')

        with pdf_path.open('rb') as file_obj:
            await bot.send_document(
                chat_id=495514905,
                document=file_obj,
                filename='test.pdf',
                caption='Test PDF'
            )
        print('PDF sent successfully')
    except TelegramError as e:
        print(f'Telegram error: {e}')
    except Exception as e:
        print(f'Other error: {e}')

if __name__ == '__main__':
    asyncio.run(test_send_file())