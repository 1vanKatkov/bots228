import logging
import os
import random
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
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

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

load_dotenv()

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
YOOKASSA_ACCOUNT_ID = os.getenv("YOOKASSA_ACCOUNT_ID")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "https://t.me/your_bot_username")
YOOKASSA_TEST_MODE = os.getenv("YOOKASSA_TEST_MODE", "1")

if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY and YOOKASSA_ACCOUNT_ID:
    Configuration.configure(
        shop_id=YOOKASSA_SHOP_ID,
        secret_key=YOOKASSA_SECRET_KEY,
        account_id=YOOKASSA_ACCOUNT_ID,
    )
else:
    logger.warning(
        "YooKassa credentials are incomplete (shop_id, secret_key, account_id). "
        "Payment flow will report configuration errors."
    )

if YOOKASSA_TEST_MODE != "0":
    logger.info("YooKassa initialized in test mode (YOOKASSA_TEST_MODE=%s).", YOOKASSA_TEST_MODE)

USER_DB_PATH = Path(__file__).resolve().parent / "sonnik_users.db"
STARTING_SPARKS = 5
SPARK_COST = 5

WELCOME_TEXT = (
    "*Добро пожаловать в Нумерологический кабинет!*\n\n"
    "Я помогу рассчитать Число Сознания, Судьбы и Действия и соберу для вас "
    "индивидуальный PDF-отчет. Нажмите кнопку ниже, чтобы начать."
)

SUBSCRIPTION_PACKAGES = {
    "sub_150": {
        "sparks": 150,
        "amount": 149,
        "period_days": 30,
        "label": "150 искр (1 месяц) — 149₽",
    },
    "sub_450": {
        "sparks": 450,
        "amount": 399,
        "period_days": 90,
        "label": "450 искр (3 месяца) — 399₽",
    },
    "sub_900": {
        "sparks": 900,
        "amount": 749,
        "period_days": 180,
        "label": "900 искр (6 месяцев) — 749₽",
    },
}

TOP_UP_PACKAGES = {
    "topup_50": {"sparks": 50, "amount": 100, "label": "50 искр — 100₽"},
    "topup_100": {"sparks": 100, "amount": 200, "label": "100 искр — 200₽"},
}

PROMPT_FOR_NAME = (
    "Введите ваше имя на кириллице (например: Иван).\n\n"
    "Имя нужно для расчета Числа Действия."
)
PROMPT_FOR_BIRTHDATE = (
    "Теперь введите дату рождения в формате ДД.ММ.ГГГГ (например: 28.01.1991)."
)

THINKING_MESSAGES = [
    "🧮 Складываю вибрации вашего имени и даты...",
    "📜 Перевожу цифры в смыслы, готовлю отчет...",
    "✨ Подбираю тексты под ваши числа, чуть-чуть магии...",
    "🔢 Проверяю расчеты, чтобы все сошлось идеально...",
    "🪄 Собираю рекомендации по Числу Сознания и Действия...",
]

STATE_WAITING_NAME = 0
STATE_WAITING_BIRTHDATE = 1


def _init_user_db() -> None:
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                credits INTEGER NOT NULL,
                subscription_end TEXT
            )
            """
        )
    _ensure_user_subscription_column()


def _ensure_user_subscription_column() -> None:
    with sqlite3.connect(USER_DB_PATH) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
        if "subscription_end" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN subscription_end TEXT")


def _ensure_payment_columns() -> None:
    required = {
        "is_subscription": "INTEGER DEFAULT 0",
        "subscription_days": "INTEGER"
    }
    with sqlite3.connect(USER_DB_PATH) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(payments)")]
        for column, definition in required.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE payments ADD COLUMN {column} {definition}")


def _init_payments_table() -> None:
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                telegram_id INTEGER NOT NULL,
                username TEXT,
                sparks INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT,
                credited INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                is_subscription INTEGER DEFAULT 0,
                subscription_days INTEGER
            )
            """
        )
    _ensure_payment_columns()


def _normalize_username(user) -> str:
    username = getattr(user, "username", None)
    if username:
        return username
    return f"user_{user.id}"


def _get_user_row(telegram_id: int) -> Optional[sqlite3.Row]:
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()


def ensure_subscription_state(telegram_id: int) -> None:
    row = _get_user_row(telegram_id)
    if not row:
        return
    end_at = row["subscription_end"]
    if not end_at:
        return
    try:
        expiry = datetime.fromisoformat(end_at)
    except ValueError:
        logger.warning("Невалидный формат subscription_end для %s: %s", telegram_id, end_at)
        return
    if datetime.utcnow() >= expiry:
        with sqlite3.connect(USER_DB_PATH) as conn:
            conn.execute(
                "UPDATE users SET credits = 0, subscription_end = NULL WHERE telegram_id = ?",
                (telegram_id,),
            )


def has_active_subscription(telegram_id: int) -> bool:
    ensure_subscription_state(telegram_id)
    row = _get_user_row(telegram_id)
    if not row:
        return False
    end_at = row["subscription_end"]
    if not end_at:
        return False
    expiry = datetime.fromisoformat(end_at)
    return datetime.utcnow() < expiry


def activate_subscription(
    telegram_id: int, username: str, sparks: int, period_days: int
) -> None:
    if period_days <= 0:
        period_days = 30
    end_at = (datetime.utcnow() + timedelta(days=period_days)).isoformat()
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO users (telegram_id, username, credits, subscription_end)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                credits = excluded.credits,
                username = excluded.username,
                subscription_end = excluded.subscription_end
            """,
            (telegram_id, username, sparks, end_at),
        )


def _format_subscription_end(end_at: Optional[str]) -> str:
    if not end_at:
        return "не задан"
    try:
        return datetime.fromisoformat(end_at).strftime("%d.%m.%Y")
    except ValueError:
        return end_at


def is_yookassa_configured() -> bool:
    return bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY and YOOKASSA_ACCOUNT_ID)


def _current_timestamp() -> str:
    return datetime.utcnow().isoformat()


def save_payment_record(
    payment_id: str,
    telegram_id: int,
    username: str,
    sparks: int,
    amount: int,
    status: Optional[str] = None,
    is_subscription: bool = False,
    subscription_days: Optional[int] = None,
) -> None:
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO payments (
                payment_id,
                telegram_id,
                username,
                sparks,
                amount,
                status,
                credited,
                created_at,
                is_subscription,
                subscription_days
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                payment_id,
                telegram_id,
                username,
                sparks,
                amount,
                status,
                _current_timestamp(),
                int(is_subscription),
                subscription_days,
            ),
        )


def get_payment_record(payment_id: str) -> Optional[sqlite3.Row]:
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM payments WHERE payment_id = ?", (payment_id,)
        ).fetchone()
        return row


def update_payment_status(payment_id: str, status: str) -> None:
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            "UPDATE payments SET status = ? WHERE payment_id = ?",
            (status, payment_id),
        )


def mark_payment_as_credited(payment_id: str) -> None:
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.execute(
            "UPDATE payments SET credited = 1 WHERE payment_id = ?",
            (payment_id,),
        )


def get_payment_status_keyboard(payment_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🧾 Проверить снова", callback_data=f"check_payment:{payment_id}"
                )
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")],
        ]
    )


def get_payment_offer_keyboard(payment_id: str, confirmation_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💳 Перейти к оплате",
                    url=confirmation_url,
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Я оплатил",
                    callback_data=f"check_payment:{payment_id}",
                )
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")],
        ]
    )


def get_or_create_user(telegram_id: int, username: str) -> int:
    with sqlite3.connect(USER_DB_PATH) as conn:
        cur = conn.execute(
            "SELECT credits FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = cur.fetchone()
        if row:
            conn.execute(
                "UPDATE users SET username = ? WHERE telegram_id = ?",
                (username, telegram_id),
            )
            return row[0]
        conn.execute(
            "INSERT INTO users (telegram_id, username, credits) VALUES (?, ?, ?)",
            (telegram_id, username, STARTING_SPARKS),
        )
        return STARTING_SPARKS


def deduct_user_sparks(telegram_id: int, amount: int) -> int:
    with sqlite3.connect(USER_DB_PATH) as conn:
        cur = conn.execute(
            "SELECT credits FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = cur.fetchone()
        if not row:
            return 0
        new_balance = max(row[0] - amount, 0)
        conn.execute(
            "UPDATE users SET credits = ? WHERE telegram_id = ?",
            (new_balance, telegram_id),
        )
        return new_balance


def add_user_sparks(telegram_id: int, username: str, amount: int) -> int:
    with sqlite3.connect(USER_DB_PATH) as conn:
        cur = conn.execute(
            "SELECT credits FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = cur.fetchone()
        if row:
            new_balance = row[0] + amount
            conn.execute(
                "UPDATE users SET credits = ?, username = ? WHERE telegram_id = ?",
                (new_balance, username, telegram_id),
            )
            return new_balance
        initial_balance = STARTING_SPARKS + amount
        conn.execute(
            "INSERT INTO users (telegram_id, username, credits) VALUES (?, ?, ?)",
            (telegram_id, username, initial_balance),
        )
        return initial_balance


def _format_amount(amount: int) -> str:
    return str(Decimal(amount).quantize(Decimal("0.00")))


def _extract_confirmation_url(payment: Payment) -> Optional[str]:
    confirmation = getattr(payment, "confirmation", None)
    if not confirmation:
        return None
    if isinstance(confirmation, dict):
        return confirmation.get("confirmation_url")
    return getattr(confirmation, "confirmation_url", None)


PAYMENT_STATUS_LABELS = {
    "waiting_for_capture": "Ожидается подтверждение",
    "pending": "Ожидается оплата",
    "succeeded": "Оплата принята",
    "canceled": "Отменена",
}


def _payment_status_label(status: str) -> str:
    return PAYMENT_STATUS_LABELS.get(status, status.replace("_", " ").capitalize())


def _build_receipt(user, amount: int, sparks: int) -> dict:
    email = f"{_normalize_username(user)}@example.com"
    return {
        "customer": {
            "email": email,
        },
        "items": [
            {
                "description": f"{sparks} искр",
                "quantity": "1.00",
                "amount": {
                    "value": _format_amount(amount),
                    "currency": "RUB",
                },
                "vat_code": 1,
                "payment_subject": "service",
                "payment_mode": "full_payment",
            }
        ],
    }


def create_yookassa_payment(
    user, sparks: int, amount: int, metadata: dict
) -> Payment:
    if not is_yookassa_configured():
        raise RuntimeError("YooKassa конфигурация не задана.")

    payload = {
        "amount": {
            "value": _format_amount(amount),
            "currency": "RUB",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL,
        },
        "capture": True,
        "metadata": {
            "telegram_id": str(user.id),
            "sparks": str(sparks),
            **metadata,
        },
        "receipt": _build_receipt(user, amount, sparks),
        "description": f"Пакет {sparks} искр для пользователя {user.id}",
    }

    return Payment.create(payload, uuid.uuid4().hex)


async def start_yookassa_purchase(
    query,
    count: int,
    amount: int,
    *,
    is_subscription: bool = False,
    subscription_days: Optional[int] = None,
) -> None:
    user = query.from_user
    username = _normalize_username(user)

    if not is_yookassa_configured():
        await query.edit_message_text(
            "⚠️ Платежная система пока не настроена. "
            "Пожалуйста, заполните переменные окружения и попробуйте снова.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    try:
        metadata = {"is_subscription": "1" if is_subscription else "0"}
        if subscription_days:
            metadata["subscription_days"] = str(subscription_days)
        payment = create_yookassa_payment(user, count, amount, metadata)
    except Exception as exc:
        logger.exception("Не удалось создать платеж в YooKassa: %s", exc)
        await query.edit_message_text(
            "⚠️ Не удалось создать платеж. Попробуйте снова чуть позже.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    confirmation_url = _extract_confirmation_url(payment)
    if not confirmation_url:
        logger.error("YooKassa не вернула confirmation_url для платежа %s", payment.id)
        await query.edit_message_text(
            "⚠️ Не удалось подготовить ссылку на оплату.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    save_payment_record(
        payment.id,
        user.id,
        username,
        count,
        amount,
        payment.status,
        is_subscription=is_subscription,
        subscription_days=subscription_days,
    )

    await query.edit_message_text(
        "💎 Для покупки перейдите по ссылке и после платежа нажмите «Я оплатил». "
        "Статус можно проверить кнопкой ниже.",
        reply_markup=get_payment_offer_keyboard(payment.id, confirmation_url),
    )


async def handle_payment_check(query, payment_id: str) -> None:
    try:
        payment = Payment.find_one(payment_id)
    except Exception as exc:
        logger.exception("Ошибка получения статуса платежа %s: %s", payment_id, exc)
        await query.edit_message_text(
            "⚠️ Не удалось получить статус платежа. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    status = payment.status
    update_payment_status(payment_id, status)
    record = get_payment_record(payment_id)
    status_label = _payment_status_label(status)

    if not record:
        await query.edit_message_text(
            f"Статус платежа: {status_label}. Запись не найдена, напишите админу.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    sparks = record["sparks"]
    amount = record["amount"]
    username = record["username"] or _normalize_username(query.from_user)
    credited_before = bool(record["credited"])
    is_subscription = bool(record["is_subscription"])
    subscription_days = record["subscription_days"] or 0
    response_text = f"Статус платежа: {status_label} ({amount}₽).\n"

    if status == "succeeded" and not credited_before:
        if is_subscription:
            activate_subscription(
                record["telegram_id"],
                username,
                sparks,
                subscription_days,
            )
            row = _get_user_row(record["telegram_id"])
            expiry_label = _format_subscription_end(
                row["subscription_end"] if row else None
            )
            response_text = (
                f"💎 Подписка активна до {expiry_label}. "
                f"Баланс: {sparks} искр."
            )
        else:
            balance = add_user_sparks(record["telegram_id"], username, sparks)
            row = _get_user_row(record["telegram_id"])
            expiry_label = _format_subscription_end(
                row["subscription_end"] if row else None
            )
            response_text = (
                f"💰 Пополнение на {sparks} искр зачислено. "
                f"Баланс: {balance} искр.\n"
            )
        mark_payment_as_credited(payment_id)
    elif status == "succeeded":
        row = _get_user_row(record["telegram_id"])
        expiry_label = _format_subscription_end(row["subscription_end"] if row else None)
        if is_subscription:
            balance = row["credits"] if row else 0
            response_text = (
                f"💎 Подписка уже активирована до {expiry_label}. "
                f"Баланс: {balance} искр."
            )
        else:
            balance = get_or_create_user(record["telegram_id"], username)
            response_text = (
                f"💰 Оплата уже зачислена ранее. Баланс: {balance} искр.\n"
                f"Все искры сгорят {expiry_label}."
            )
    elif status == "pending":
        response_text += "Ожидаем оплату. Как только сменится статус, нажмите «Проверить снова»."
    else:
        response_text += "Если это ошибка, напишите администратору."

    await query.edit_message_text(
        response_text,
        reply_markup=get_payment_status_keyboard(payment_id),
    )


_init_user_db()
_init_payments_table()


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📜 Получить PDF-отчет", callback_data="get_report")],
            [InlineKeyboardButton("💎 Купить Астральные Искры", callback_data="buy_sparks")],
        ]
    )


def get_buy_sparks_keyboard(has_subscription: bool) -> InlineKeyboardMarkup:
    rows = []
    if not has_subscription:
        rows.extend(
            [[InlineKeyboardButton(pkg["label"], callback_data=key)] for key, pkg in SUBSCRIPTION_PACKAGES.items()]
        )
    else:
        top_up_row = [
            InlineKeyboardButton(TOP_UP_PACKAGES["topup_50"]["label"], callback_data="topup_50"),
            InlineKeyboardButton(TOP_UP_PACKAGES["topup_100"]["label"], callback_data="topup_100"),
        ]
        rows.append(top_up_row)
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user:
        username = _normalize_username(user)
        get_or_create_user(user.id, username)
    await update.message.reply_text(
        WELCOME_TEXT,
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(),
    )


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if not user:
        return ConversationHandler.END

    ensure_subscription_state(user.id)
    has_subscription = has_active_subscription(user.id)

    if query.data == "get_report":
        context.user_data.clear()
        await query.edit_message_text(PROMPT_FOR_NAME, reply_markup=get_back_to_menu_keyboard())
        return STATE_WAITING_NAME

    if query.data == "buy_sparks":
        if has_subscription:
            row = _get_user_row(user.id)
            expiry_label = _format_subscription_end(row["subscription_end"] if row else None)
            await query.edit_message_text(
                "💎 *Действующая подписка* 💎\n\n"
                f"Подписка активна до {expiry_label}. Доппокупки 50/100 искр доступны и сгорают вместе с текущим периодом.",
                parse_mode="Markdown",
                reply_markup=get_buy_sparks_keyboard(True),
            )
        else:
            await query.edit_message_text(
                "💎 *Пакеты подписки* 💎\n\n"
                "150 искр (1 месяц) — 149₽\n"
                "450 искр (3 месяца) — 399₽\n"
                "900 искр (6 месяцев) — 749₽\n",
                parse_mode="Markdown",
                reply_markup=get_buy_sparks_keyboard(False),
            )
        return ConversationHandler.END

    if query.data.startswith("check_payment:"):
        payment_id = query.data.split(":", 1)[1]
        await handle_payment_check(query, payment_id)
        return ConversationHandler.END

    if query.data in SUBSCRIPTION_PACKAGES:
        if has_subscription:
            row = _get_user_row(user.id)
            expiry_label = _format_subscription_end(row["subscription_end"] if row else None)
            await query.edit_message_text(
                "🛑 У вас уже активная подписка. "
                f"Подписка действует до {expiry_label}. Пока подписка активна, доступны только покупки 50/100 искр.",
                parse_mode="Markdown",
                reply_markup=get_buy_sparks_keyboard(True),
            )
            return ConversationHandler.END
        package = SUBSCRIPTION_PACKAGES[query.data]
        await start_yookassa_purchase(
            query,
            package["sparks"],
            package["amount"],
            is_subscription=True,
            subscription_days=package["period_days"],
        )
        return ConversationHandler.END

    if query.data in TOP_UP_PACKAGES:
        if not has_subscription:
            await query.edit_message_text(
                "⚠️ Дополнительные пакеты доступны только при активной подписке. "
                "Оформите подписку и попробуйте снова.",
                reply_markup=get_buy_sparks_keyboard(False),
            )
            return ConversationHandler.END
        package = TOP_UP_PACKAGES[query.data]
        await start_yookassa_purchase(
            query,
            package["sparks"],
            package["amount"],
            is_subscription=False,
        )
        return ConversationHandler.END

    if query.data == "back_to_menu":
        await query.message.reply_text(
            "Выберите, что хотите сделать:",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard(),
        )
        return ConversationHandler.END

    return ConversationHandler.END


def parse_birth_date(value: str) -> Optional[date]:
    match = re.match(r"^(\d{2})[.\-/](\d{2})[.\-/](\d{4})$", value.strip())
    if not match:
        return None
    day, month, year = map(int, match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def is_valid_cyrillic_name(value: str) -> bool:
    cleaned = value.strip()
    if len(cleaned) < 2:
        return False
    return bool(re.match(r"^[А-Яа-я]+$", cleaned))


async def handle_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    full_name = update.message.text.strip()
    if not is_valid_cyrillic_name(full_name):
        await update.message.reply_text(
            "Пожалуйста, укажите имя на кириллице. Пример: Иван.",
            reply_markup=get_back_to_menu_keyboard(),
        )
        return STATE_WAITING_NAME
    context.user_data["full_name"] = full_name
    await update.message.reply_text(
        PROMPT_FOR_BIRTHDATE,
        reply_markup=get_back_to_menu_keyboard(),
    )
    return STATE_WAITING_BIRTHDATE


async def handle_birthdate_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    birth_date = parse_birth_date(update.message.text)
    if not birth_date:
        await update.message.reply_text(
            "Не удалось распознать дату. Введите в формате ДД.ММ.ГГГГ.",
            reply_markup=get_back_to_menu_keyboard(),
        )
        return STATE_WAITING_BIRTHDATE

    user = update.effective_user
    if not user:
        await update.message.reply_text(
            "Не получилось распознать пользователя. Попробуйте снова.",
            reply_markup=get_main_menu_keyboard(),
        )
        return ConversationHandler.END

    full_name = context.user_data.get("full_name", "").strip()
    if not full_name:
        await update.message.reply_text(
            PROMPT_FOR_NAME,
            reply_markup=get_back_to_menu_keyboard(),
        )
        return STATE_WAITING_NAME

    ensure_subscription_state(user.id)
    username = _normalize_username(user)
    credits = get_or_create_user(user.id, username)
    if credits < SPARK_COST:
        await update.message.reply_text(
            "💫 Чтобы получить отчет, нужно 5 Астральных Искр, "
            "а на балансе меньше. Пополните баланс через меню и попробуйте снова.",
            reply_markup=get_main_menu_keyboard(),
        )
        return ConversationHandler.END

    remaining = deduct_user_sparks(user.id, SPARK_COST)
    await update.message.reply_text(f"💎 Списано {SPARK_COST} Астральных Искр. Осталось {remaining}.")

    thinking_message = await update.message.reply_text(
        f"<i>{random.choice(THINKING_MESSAGES)}</i>",
        parse_mode="HTML",
        reply_markup=get_back_to_menu_keyboard(),
    )

    try:
        pdf_path = generate_numerology_report_pdf(user.id, full_name, birth_date)
        caption = (
            "Ваш нумерологический отчет готов!\n"
        )
        with pdf_path.open("rb") as file_obj:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=file_obj,
                filename="razbor.pdf",
                caption=caption,
            )
        await thinking_message.delete()
    except Exception as exc:
        logger.exception("Не удалось сформировать отчет: %s", exc)
        await thinking_message.edit_text(
            "🌀 Не получилось собрать отчет. Попробуйте еще раз или обратитесь к администратору.",
            reply_markup=get_back_to_menu_keyboard(),
        )

    return ConversationHandler.END


def main() -> None:
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_bot_token:
        raise RuntimeError("Переменная TELEGRAM_BOT_TOKEN не задана.")

    application = Application.builder().token(telegram_bot_token).build()
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler)],
        states={
            STATE_WAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name_input),
                CallbackQueryHandler(menu_handler),
            ],
            STATE_WAITING_BIRTHDATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_birthdate_input),
                CallbackQueryHandler(menu_handler),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    logger.info("Bot Number запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
