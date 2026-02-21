import logging
from logging.handlers import RotatingFileHandler
import os
import sqlite3
import asyncio
import csv
import io
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional

import matplotlib
matplotlib.use('Agg') # Non-interactive backend
import matplotlib.pyplot as plt

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from dotenv import load_dotenv

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("TELEGRAM_ADMIN_BOT_TOKEN")

# Authorized admins
ALLOWED_USERNAMES = ["dragom_star", "balakin_as", "philecron", "gr88887"]

# Database paths
SONNIK_DB = ROOT_DIR / "sonnik" / "sonnik_users.db"
NUMEROLOGY_DB = ROOT_DIR / "numerology" / "sonnik_users.db"

# Bot Tokens for Broadcast
SONNIK_TOKEN = "8486829399:AAEz3zGFH3bNiSyXqyBpDzGjVNF4zh0zMzc"
NUMEROLOGY_TOKEN = "8527944321:AAHZincQYdl01id4EuzBj7w5Uml4MyjFCjM"

# States for ConversationHandler
STATE_CHOOSE_BOT = 1
STATE_BOT_MENU = 2
STATE_FIND_USER = 3
STATE_USER_DETAILS = 4
STATE_ADJUST_BALANCE = 5
STATE_BROADCAST = 6

# Log paths
LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Enable logging
log_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log_file = LOGS_DIR / "admin_bot.log"

# File handler
file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)

def is_authorized(update: Update) -> bool:
    user = update.effective_user
    if not user or not user.username:
        return False
    return user.username.lower() in [u.lower().lstrip('@') for u in ALLOWED_USERNAMES]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        if update.message:
            await update.message.reply_text("Доступ запрещен.")
        elif update.callback_query:
            await update.callback_query.answer("Доступ запрещен.", show_alert=True)
        return ConversationHandler.END

    keyboard = [
        [
            InlineKeyboardButton("Сонник", callback_data="bot_sonnik"),
            InlineKeyboardButton("Нумерология", callback_data="bot_numerology"),
        ],
        [InlineKeyboardButton("Проверить статус всех ботов", callback_data="check_status")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "выбор бота:"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
    
    return STATE_CHOOSE_BOT

async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bots = {
        "Сонник": "bot_sonnik.py",
        "Сонник2": "bot_sonnik2.py",
        "Нумерология": "bot_number.py",
    }
    
    status_text = "Статус ботов:\n\n"
    
    try:
        # Get list of all python processes with command line arguments
        cmd = 'powershell "Get-CimInstance Win32_Process -Filter \\"name=\'python.exe\'\\" | Select-Object CommandLine"'
        output = subprocess.check_output(cmd, shell=True, text=True)
        
        for name, script in bots.items():
            is_running = script in output
            status = "Запущен" if is_running else "Не запущен"
            status_text += f"{name}: {status}\n"
            
    except Exception as e:
        logger.error(f"Error checking bot status: {e}")
        status_text += "Ошибка при проверке процессов."

    keyboard = [[InlineKeyboardButton("Назад", callback_data="back_to_start")]]
    await query.edit_message_text(status_text, reply_markup=InlineKeyboardMarkup(keyboard))
    return STATE_CHOOSE_BOT

async def bot_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        if query.data and query.data.startswith("bot_"):
            bot_type = query.data.split("_")[1]
            context.user_data["active_bot"] = bot_type
        else:
            bot_type = context.user_data.get("active_bot")
    else:
        bot_type = context.user_data.get("active_bot")

    if not bot_type:
        return await start(update, context)

    bot_name = "Сонник" if bot_type == "sonnik" else "Нумерология"

    keyboard = [
        [InlineKeyboardButton("Статистика", callback_data="stats")],
        [InlineKeyboardButton("График новых пользователей", callback_data="charts")],
        [InlineKeyboardButton("Выгрузить приход (CSV)", callback_data="export_daily_csv")],
        [InlineKeyboardButton("Выгрузить Users (CSV)", callback_data="export_users")],
        [InlineKeyboardButton("Выгрузить Payments (CSV)", callback_data="export_payments")],
        [InlineKeyboardButton("Выгрузить логи (30 дней)", callback_data="export_logs")],
        [InlineKeyboardButton("Найти пользователя", callback_data="find_user")],
        [InlineKeyboardButton("Рассылка (ВСЕМ)", callback_data="broadcast")],
        [InlineKeyboardButton("Тестовая рассылка (АДМИНАМ)", callback_data="test_broadcast")],
        [InlineKeyboardButton("Назад к выбору бота", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"Управление ботом: *{bot_name}*"
    if query and query.message.text == text:
        pass
    elif query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    return STATE_BOT_MENU

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bot_type = context.user_data.get("active_bot")
    db_path = SONNIK_DB if bot_type == "sonnik" else NUMEROLOGY_DB
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE blocked = 1")
    blocked_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*), SUM(amount) FROM payments WHERE status = 'succeeded'")
    pay_stats = cursor.fetchone()
    total_payments = pay_stats[0] or 0
    total_amount = pay_stats[1] or 0
    cursor.execute("SELECT COUNT(*) FROM users WHERE credits > 0 AND blocked = 0")
    users_with_balance = cursor.fetchone()[0]
    conn.close()
    
    text = (
        f"*Статистика ({'Сонник' if bot_type == 'sonnik' else 'Нумерология'}):*\n\n"
        f"Всего пользователей: `{total_users}`\n"
        f"Заблокировали бота: `{blocked_users}`\n"
        f"Активных с балансом: `{users_with_balance}`\n"
        f"Успешных оплат: `{total_payments}`\n"
        f"Общая сумма: `{total_amount} руб.`"
    )
    
    keyboard = [[InlineKeyboardButton("Назад", callback_data="back_to_bot_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return STATE_BOT_MENU

async def export_daily_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bot_type = context.user_data.get("active_bot")
    db_path = SONNIK_DB if bot_type == "sonnik" else NUMEROLOGY_DB
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get users by day
    cursor.execute("""
        SELECT date(created_at) as day, count(*) 
        FROM users 
        WHERE created_at IS NOT NULL 
        GROUP BY day 
        ORDER BY day DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await query.message.reply_text("Нет данных.")
        return STATE_BOT_MENU

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Дата', 'Количество новых пользователей'])
    writer.writerows(rows)
    
    file_data = output.getvalue().encode('utf-8')
    file_stream = io.BytesIO(file_data)
    
    filename = f"{bot_type}_daily_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=file_stream,
        filename=filename,
        caption=f"Сухие цифры прихода пользователей для бота {bot_type}"
    )
    return STATE_BOT_MENU

async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bot_type = context.user_data.get("active_bot")
    table_name = "users" if query.data == "export_users" else "payments"
    db_path = SONNIK_DB if bot_type == "sonnik" else NUMEROLOGY_DB
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    
    # Get column names
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    conn.close()
    
    if not rows:
        await query.message.reply_text("Таблица пуста.")
        return STATE_BOT_MENU

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(columns)
    writer.writerows(rows)
    
    file_data = output.getvalue().encode('utf-8')
    file_stream = io.BytesIO(file_data)
    
    filename = f"{bot_type}_{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=file_stream,
        filename=filename,
        caption=f"Экспорт таблицы {table_name} для бота {bot_type}"
    )
    return STATE_BOT_MENU

async def send_charts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bot_type = context.user_data.get("active_bot")
    db_path = SONNIK_DB if bot_type == "sonnik" else NUMEROLOGY_DB
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get users by day for the last 30 days
    cursor.execute("""
        SELECT date(created_at) as day, count(*) 
        FROM users 
        WHERE created_at IS NOT NULL 
        GROUP BY day 
        ORDER BY day DESC 
        LIMIT 30
    """)
    data = cursor.fetchall()
    conn.close()
    
    if not data:
        await query.message.reply_text("Нет данных для построения графика.")
        return STATE_BOT_MENU
    
    data.reverse() # Order chronologically
    days = [row[0] for row in data]
    counts = [row[1] for row in data]
    
    plt.figure(figsize=(10, 6))
    plt.plot(days, counts, marker='o', linestyle='-', color='b')
    plt.title(f"Новые пользователи по дням ({bot_type})")
    plt.xlabel("Дата")
    plt.ylabel("Кол-во пользователей")
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.tight_layout()
    
    img_stream = io.BytesIO()
    plt.savefig(img_stream, format='png')
    img_stream.seek(0)
    plt.close()
    
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=img_stream,
        caption=f"График новых пользователей за последние 30 дней ({bot_type})"
    )
    return STATE_BOT_MENU

async def export_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    bot_type = context.user_data.get("active_bot")
    log_filename = f"{bot_type}_bot.log"
    log_path = LOGS_DIR / log_filename
    
    if not log_path.exists():
        await query.message.reply_text(f"Файл логов {log_filename} не найден.")
        return STATE_BOT_MENU
    
    # Filter logs for last 30 days
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    filtered_logs = []
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Log format: 2026-01-29 07:48:15,123 - ...
                try:
                    date_str = line.split(',')[0].split(' - ')[0]
                    log_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    if log_date >= thirty_days_ago:
                        filtered_logs.append(line)
                except (ValueError, IndexError):
                    # If line doesn't match format, include it if we already started including
                    if filtered_logs:
                        filtered_logs.append(line)
    except Exception as e:
        logger.error(f"Error reading log file: {e}")
        await query.message.reply_text("Ошибка при чтении логов.")
        return STATE_BOT_MENU

    if not filtered_logs:
        await query.message.reply_text("Нет логов за последние 30 дней.")
        return STATE_BOT_MENU

    output = io.StringIO()
    output.writelines(filtered_logs)
    
    file_data = output.getvalue().encode('utf-8')
    file_stream = io.BytesIO(file_data)
    
    filename = f"{bot_type}_logs_30d_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=file_stream,
        filename=filename,
        caption=f"Логи за последние 30 дней для бота {bot_type}"
    )
    return STATE_BOT_MENU

async def find_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите username (без @) или Telegram ID пользователя:")
    return STATE_FIND_USER

async def find_user_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    search_query = update.message.text.strip().replace("@", "")
    bot_type = context.user_data.get("active_bot")
    db_path = SONNIK_DB if bot_type == "sonnik" else NUMEROLOGY_DB
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    if search_query.isdigit():
        cursor.execute("SELECT telegram_id, username, credits, blocked FROM users WHERE telegram_id = ?", (int(search_query),))
    else:
        cursor.execute("SELECT telegram_id, username, credits, blocked FROM users WHERE LOWER(username) = ?", (search_query.lower(),))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        await update.message.reply_text("Пользователь не найден. Попробуйте еще раз или напишите /start для отмены:")
        return STATE_FIND_USER
    
    context.user_data["target_user_id"] = user[0]
    return await show_user_details(update, context, user)

async def show_user_details(update: Update, context: ContextTypes.DEFAULT_TYPE, user_row=None):
    if not user_row:
        user_id = context.user_data.get("target_user_id")
        bot_type = context.user_data.get("active_bot")
        db_path = SONNIK_DB if bot_type == "sonnik" else NUMEROLOGY_DB
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, username, credits, blocked FROM users WHERE telegram_id = ?", (user_id,))
        user_row = cursor.fetchone()
        conn.close()

    tid, uname, credits, blocked = user_row
    text = (
        f"*Пользователь:*\n"
        f"ID: `{tid}`\n"
        f"Username: `@{uname if uname else 'нет'}`\n"
        f"Баланс: `{credits}` искр\n"
        f"Статус: `{'🚫 ЗАБЛОКИРОВАН' if blocked else '✅ Активен'}`\n"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("Добавить", callback_data="adj_add"),
            InlineKeyboardButton("Списать", callback_data="adj_sub"),
        ],
        [InlineKeyboardButton("Пересоздать пользователя", callback_data="recreate_user")],
        [InlineKeyboardButton("Удалить пользователя", callback_data="delete_user")],
        [InlineKeyboardButton("Назад к меню бота", callback_data="back_to_bot_menu")],
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return STATE_USER_DETAILS

async def adjust_balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = "добавить" if query.data == "adj_add" else "списать"
    context.user_data["balance_action"] = query.data
    await query.edit_message_text(f"Количество искр для {action}:")
    return STATE_ADJUST_BALANCE

async def adjust_balance_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount_str = update.message.text.strip()
    if not amount_str.isdigit():
        await update.message.reply_text("Введите целое число:")
        return STATE_ADJUST_BALANCE
    
    amount = int(amount_str)
    action = context.user_data.get("balance_action")
    user_id = context.user_data.get("target_user_id")
    bot_type = context.user_data.get("active_bot")
    db_path = SONNIK_DB if bot_type == "sonnik" else NUMEROLOGY_DB
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    if action == "adj_add":
        cursor.execute("UPDATE users SET credits = credits + ? WHERE telegram_id = ?", (amount, user_id))
    else:
        cursor.execute("UPDATE users SET credits = MAX(0, credits - ?) WHERE telegram_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text("Баланс изменен.")
    return await show_user_details(update, context)

async def recreate_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = context.user_data.get("target_user_id")
    bot_type = context.user_data.get("active_bot")
    db_path = SONNIK_DB if bot_type == "sonnik" else NUMEROLOGY_DB
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Сбрасываем искры до 5, обнуляем запросы, подписку и блокировку
    cursor.execute("""
        UPDATE users 
        SET credits = 5, 
            dream_requests = 0, 
            subscription_end = NULL,
            blocked = 0
        WHERE telegram_id = ?
    """, (user_id,))
    conn.commit()
    conn.close()
    
    await query.edit_message_text("Пользователь пересоздан (баланс: 5 искр, запросы и подписка обнулены).")
    return await show_user_details(update, context)

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = context.user_data.get("target_user_id")
    bot_type = context.user_data.get("active_bot")
    db_path = SONNIK_DB if bot_type == "sonnik" else NUMEROLOGY_DB
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE telegram_id = ?", (user_id,))
    # Также удаляем платежи пользователя для чистоты, если нужно. 
    # Но обычно платежи оставляют для истории. Оставлю только удаление пользователя.
    conn.commit()
    conn.close()
    
    await query.edit_message_text(f"Пользователь {user_id} удален из базы данных {bot_name_for_msg(bot_type)}.")
    return await bot_menu(update, context)

def bot_name_for_msg(bot_type: str) -> str:
    return "Сонник" if bot_type == "sonnik" else "Нумерология"

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите текст рассылки. Он будет отправлен ВСЕМ пользователям бота. Напишите /start для отмены:")
    context.user_data["is_test_broadcast"] = False
    return STATE_BROADCAST

async def test_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите текст ТЕСТОВОЙ рассылки. Он будет отправлен только администраторам в этом боте. Напишите /start для отмены:")
    context.user_data["is_test_broadcast"] = True
    return STATE_BROADCAST

async def broadcast_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    bot_type = context.user_data.get("active_bot")
    is_test = context.user_data.get("is_test_broadcast", False)
    
    if is_test:
        # Test broadcast to admins via Admin Bot
        status_msg = await update.message.reply_text(f"Начинаю тестовую рассылку для администраторов...")
        
        # We need IDs of admins. We'll try to find them in both databases.
        admin_ids = set()
        for db_path in [SONNIK_DB, NUMEROLOGY_DB]:
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                placeholders = ', '.join(['?'] * len(ALLOWED_USERNAMES))
                cursor.execute(f"SELECT telegram_id FROM users WHERE LOWER(username) IN ({placeholders})", 
                               [u.lower().lstrip('@') for u in ALLOWED_USERNAMES])
                for row in cursor.fetchall():
                    admin_ids.add(row[0])
                conn.close()
            except Exception as e:
                logger.error(f"Error searching admins in {db_path}: {e}")

        sent = 0
        failed = 0
        for aid in admin_ids:
            try:
                await context.bot.send_message(chat_id=aid, text=f"{message_text}")
                sent += 1
            except Exception as e:
                logger.error(f"Failed to send test to {aid}: {e}")
                failed += 1
        
        await update.message.reply_text(f"Тестовая рассылка завершена.\nОтправлено админам: `{sent}`\nОшибок: `{failed}`\n(Админ должен хотя бы раз запустить этот админ-бот)", parse_mode="Markdown")
        return await bot_menu(update, context)

    # Regular broadcast to all users
    db_path = SONNIK_DB if bot_type == "sonnik" else NUMEROLOGY_DB
    token = SONNIK_TOKEN if bot_type == "sonnik" else NUMEROLOGY_TOKEN
    
    from telegram import Bot
    from telegram.error import TelegramError, Forbidden, BadRequest
    
    target_bot = Bot(token=token)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Пропускаем заблокированных пользователей
    cursor.execute("SELECT telegram_id FROM users WHERE blocked = 0")
    user_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    status_msg = await update.message.reply_text(f"Начинаю рассылку для {len(user_ids)} пользователей...")
    
    sent = 0
    failed = 0
    blocked_count = 0
    for uid in user_ids:
        try:
            await target_bot.send_message(chat_id=uid, text=message_text)
            sent += 1
            if sent % 10 == 0:
                await status_msg.edit_text(f"Прогресс: {sent}/{len(user_ids)}...")
            await asyncio.sleep(0.05)
        except (Forbidden, BadRequest) as e:
            err_msg = str(e).lower()
            if "chat not found" in err_msg or "bot was blocked" in err_msg or "user is deactivated" in err_msg:
                # Помечаем пользователя как заблокированного
                try:
                    conn_inner = sqlite3.connect(db_path)
                    conn_inner.execute("UPDATE users SET blocked = 1 WHERE telegram_id = ?", (uid,))
                    conn_inner.commit()
                    conn_inner.close()
                    blocked_count += 1
                except Exception as inner_e:
                    logger.error(f"Error marking user {uid} as blocked: {inner_e}")
            failed += 1
        except TelegramError:
            failed += 1
    
    await update.message.reply_text(
        f"Рассылка завершена.\nУспешно: `{sent}`\nОшибок: `{failed}`\nИз них заблокировано: `{blocked_count}`", 
        parse_mode="Markdown"
    )
    return await bot_menu(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено.")
    return await start(update, context)

def main():
    if not TOKEN or TOKEN == "ВАШ_ТОКЕН_ЗДЕСЬ":
        print("ОШИБКА: TELEGRAM_ADMIN_BOT_TOKEN не установлен в admin/.env")
        return

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATE_CHOOSE_BOT: [
                CallbackQueryHandler(bot_menu, pattern="^bot_"),
                CallbackQueryHandler(check_status, pattern="^check_status$"),
                CallbackQueryHandler(start, pattern="^back_to_start$"),
            ],
            STATE_BOT_MENU: [
                CallbackQueryHandler(show_stats, pattern="^stats$"),
                CallbackQueryHandler(send_charts, pattern="^charts$"),
                CallbackQueryHandler(export_daily_csv, pattern="^export_daily_csv$"),
                CallbackQueryHandler(export_logs, pattern="^export_logs$"),
                CallbackQueryHandler(export_csv, pattern="^export_(users|payments)$"),
                CallbackQueryHandler(find_user_start, pattern="^find_user$"),
                CallbackQueryHandler(broadcast_start, pattern="^broadcast$"),
                CallbackQueryHandler(test_broadcast_start, pattern="^test_broadcast$"),
                CallbackQueryHandler(start, pattern="^back_to_start$"),
                CallbackQueryHandler(bot_menu, pattern="^back_to_bot_menu$"),
                CallbackQueryHandler(bot_menu, pattern="^bot_"),
            ],
            STATE_FIND_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, find_user_result),
            ],
            STATE_USER_DETAILS: [
                CallbackQueryHandler(adjust_balance_start, pattern="^adj_"),
                CallbackQueryHandler(recreate_user, pattern="^recreate_user$"),
                CallbackQueryHandler(delete_user, pattern="^delete_user$"),
                CallbackQueryHandler(bot_menu, pattern="^back_to_bot_menu$"),
            ],
            STATE_ADJUST_BALANCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, adjust_balance_finish),
            ],
            STATE_BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_finish),
            ],
        },
        fallbacks=[CommandHandler("start", start), CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    print("Админ-бот запущен.")
    application.run_polling()

if __name__ == "__main__":
    main()
