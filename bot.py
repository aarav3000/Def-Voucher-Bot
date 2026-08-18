import asyncio
import logging
from decimal import Decimal

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

import database as db

from config import (
    BOT_TOKEN,
    DATABASE_URL,
    ADMIN_IDS,
    UPI_ID,
    UPI_NAME,
    SUPPORT_USERNAME,
    REQUIRED_CHANNELS,
    REFERRAL_REWARD,
)


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


# =========================================================
# BOT
# =========================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    ),
)

dp = Dispatcher()


# =========================================================
# STATES
# =========================================================

class UserStates(StatesGroup):
    custom_quantity = State()
    utr = State()
    recover_order = State()


class AdminStates(StatesGroup):
    add_product = State()
    add_stock = State()
    change_price = State()
    welcome = State()
    terms = State()
    channel = State()


# =========================================================
# DEFAULT TEXT
# =========================================================

DEFAULT_WELCOME = """🌟 <b>WELCOME TO DEF VOUCHER HUB</b> 🌟

🎁 Your trusted place for exciting vouchers & exclusive deals!

🛍️ <b>Shop Smart • Save More • Enjoy More</b>

⚡ Fast order processing
🔐 Secure payment verification
🎟️ Voucher delivery
🎁 Refer friends & earn points
🆘 Dedicated support

━━━━━━━━━━━━━━━━━━

🚀 <b>Ready to grab your voucher?</b>

Choose an option from the menu below 👇
"""


DEFAULT_TERMS = """📜 <b>TERMS & CONDITIONS</b>

🔹 Please check the voucher description and validity before purchasing.

🔹 Digital voucher purchases are generally final after successful delivery.

🔹 Payment must be made only to the payment details shown by the bot.

🔹 UTR verification may be manual.

🔹 Fake, edited or reused UTRs are strictly prohibited.

🔹 Never share OTP, UPI PIN, bank password or other sensitive information.

🔹 Keep your voucher code private.

🔹 Contact support if you face a genuine problem.

━━━━━━━━━━━━━━━━━━

By purchasing a voucher, you confirm that you have read and accepted these terms.
"""


# =========================================================
# SETTINGS TABLE
# =========================================================

async def init_settings():

    await db._pool.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    defaults = {
        "welcome": DEFAULT_WELCOME,
        "terms": DEFAULT_TERMS,
        "channels": ",".join(REQUIRED_CHANNELS),
    }

    for key, value in defaults.items():

        await db._pool.execute(
            """
            INSERT INTO bot_settings(key, value)
            VALUES($1, $2)
            ON CONFLICT(key) DO NOTHING
            """,
            key,
            value,
        )


async def get_setting(key):

    row = await db._pool.fetchrow(
        """
        SELECT value
        FROM bot_settings
        WHERE key=$1
        """,
        key,
    )

    return row["value"] if row else ""


async def set_setting(key, value):

    await db._pool.execute(
        """
        INSERT INTO bot_settings(key, value)
        VALUES($1, $2)

        ON CONFLICT(key)
        DO UPDATE SET value=EXCLUDED.value
        """,
        key,
        value,
    )


async def get_required_channels():

    value = await get_setting("channels")

    if not value:
        return []

    return [
        channel.strip()
        for channel in value.split(",")
        if channel.strip()
    ]


# =========================================================
# ADMIN
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# =========================================================
# MAIN MENU
# =========================================================

def main_menu():

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛍️ Buy Vouchers"),
                KeyboardButton(text="🧾 My Orders"),
            ],
            [
                KeyboardButton(text="🎟️ Recover Vouchers"),
                KeyboardButton(text="🎁 Refer & Earn"),
            ],
            [
                KeyboardButton(text="💰 My Points"),
                KeyboardButton(text="🆘 Support"),
            ],
            [
                KeyboardButton(
                    text="📜 Terms & Conditions"
                ),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# =========================================================
# CHANNEL CHECK
# =========================================================

async def channel_keyboard():

    channels = await get_required_channels()

    rows = []

    for channel in channels:

        username = channel.replace("@", "").strip()

        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📢 Join @{username}",
                    url=f"https://t.me/{username}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="✅ Verify Membership",
                callback_data="verify_membership",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


async def is_channel_member(user_id: int):

    channels = await get_required_channels()

    if not channels:
        return True

    for channel in channels:

        try:

            member = await bot.get_chat_member(
                chat_id=channel,
                user_id=user_id,
            )

            if member.status in {
                "left",
                "kicked",
            }:
                return False

        except Exception:

            logging.exception(
                "Could not verify channel %s",
                channel,
            )

            return False

    return True


# =========================================================
# SEND HOME
# =========================================================

async def send_home(message: Message):

    welcome = await get_setting("welcome")

    await message.answer(
        welcome or DEFAULT_WELCOME,
        reply_markup=main_menu(),
    )


# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start(
    message: Message,
    state: FSMContext,
):

    await state.clear()

    referrer = None

    parts = message.text.split(maxsplit=1)

    if len(parts) == 2:

        argument = parts[1].strip()

        if argument.isdigit():

            referrer = int(argument)

    await db.ensure_user(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        referrer=referrer,
    )

    if not await is_channel_member(
        message.from_user.id
    ):

        await message.answer(
            "👋 <b>Welcome to DEF Voucher Hub!</b>\n\n"
            "📢 Please join our required channel first.\n\n"
            "After joining, tap <b>Verify Membership</b> 👇",
            reply_markup=await channel_keyboard(),
        )

        return

    await send_home(message)


# =========================================================
# CHANNEL VERIFY
# =========================================================

@dp.callback_query(
    F.data == "verify_membership"
)
async def verify_membership(
    call: CallbackQuery,
):

    if await is_channel_member(
        call.from_user.id
    ):

        await call.answer(
            "✅ Membership verified!"
        )

        await call.message.answer(
            await get_setting("welcome")
            or DEFAULT_WELCOME,
            reply_markup=main_menu(),
        )

    else:

        await call.answer(
            "❌ Join all required channels first.",
            show_alert=True,
        )


# =========================================================
# BUY VOUCHERS
# =========================================================

def product_keyboard(products):

    rows = []

    for product in products:

        stock = int(product["stock"])

        status = (
            "🟢"
            if stock > 0
            else "🔴"
        )

        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{status} "
                        f"{product['name']} "
                        f"• ₹{Decimal(product['price']):.2f}"
                    ),
                    callback_data=(
                        f"product:{product['id']}"
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 Back",
                callback_data="go_home",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


@dp.message(
    F.text == "🛍️ Buy Vouchers"
)
async def buy_vouchers(
    message: Message,
):

    if not await is_channel_member(
        message.from_user.id
    ):

        await message.answer(
            "📢 Please join the required channel first.",
            reply_markup=await channel_keyboard(),
        )

        return

    products = await db.get_products()

    if not products:

        await message.answer(
            "🛍️ <b>VOUCHER STORE</b>\n\n"
            "😔 No vouchers are available right now."
        )

        return

    await message.answer(
        "🛍️ <b>VOUCHER STORE</b>\n\n"
        "Choose your voucher 👇",
        reply_markup=product_keyboard(products),
    )


@dp.callback_query(
    F.data == "buy_menu"
)
async def buy_menu(
    call: CallbackQuery,
):

    products = await db.get_products()

    if not products:

        await call.message.answer(
            "😔 No products available."
        )

        await call.answer()

        return

    await call.message.answer(
        "🛍️ <b>VOUCHER STORE</b>\n\n"
        "Choose your voucher 👇",
        reply_markup=product_keyboard(products),
    )

    await call.answer()


# =========================================================
# PRODUCT DETAILS
# =========================================================

def quantity_keyboard(
    product_id,
    stock,
):

    rows = []

    for quantity in [1, 2, 5, 10]:

        if quantity <= stock:

            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🎟️ Buy {quantity}",
                        callback_data=(
                            f"quantity:{product_id}:{quantity}"
                        ),
                    )
                ]
            )

    if stock > 10:

        rows.append(
            [
                InlineKeyboardButton(
                    text="🔢 Custom Quantity",
                    callback_data=(
                        f"custom_quantity:{product_id}"
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 Back",
                callback_data="buy_menu",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


@dp.callback_query(
    F.data.startswith("product:")
)
async def product_details(
    call: CallbackQuery,
):

    product_id = int(
        call.data.split(":")[1]
    )

    product = await db.get_product(
        product_id
    )

    if not product:

        await call.answer(
            "❌ Product unavailable.",
            show_alert=True,
        )

        return

    stock = await db.stock_count(
        product_id
    )

    if stock:

        stock_text = (
            f"🟢 <b>IN STOCK</b> "
            f"({stock} available)"
        )

    else:

        stock_text = (
            "🔴 <b>OUT OF STOCK</b>"
        )

    text = (
        f"🛍️ <b>{product['name']}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"📖 <b>Description</b>\n\n"
        f"{product['description'] or 'No description available.'}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Price: <b>₹{Decimal(product['price']):.2f}</b>\n"
        f"{stock_text}\n\n"
        f"👇 <b>Select Quantity</b>"
    )

    await call.message.edit_text(
        text,
        reply_markup=quantity_keyboard(
            product_id,
            stock,
        ),
    )

    await call.answer()


# =========================================================
# QUANTITY
# =========================================================

@dp.callback_query(
    F.data.startswith("quantity:")
)
async def quantity_selected(
    call: CallbackQuery,
):

    _, product_id, quantity = (
        call.data.split(":")
    )

    await show_confirmation(
        call,
        int(product_id),
        int(quantity),
    )

    await call.answer()


@dp.callback_query(
    F.data.startswith("custom_quantity:")
)
async def custom_quantity_start(
    call: CallbackQuery,
    state: FSMContext,
):

    product_id = int(
        call.data.split(":")[1]
    )

    await state.set_state(
        UserStates.custom_quantity
    )

    await state.update_data(
        product_id=product_id
    )

    await call.message.answer(
        "🔢 <b>Custom Quantity</b>\n\n"
        "Send the number of vouchers.\n\n"
        "Example: <code>3</code>"
    )

    await call.answer()


@dp.message(
    UserStates.custom_quantity
)
async def custom_quantity_message(
    message: Message,
    state: FSMContext,
):

    try:

        quantity = int(
            message.text.strip()
        )

        if quantity < 1 or quantity > 100:

            raise ValueError

    except ValueError:

        await message.answer(
            "❌ Enter a quantity between 1 and 100."
        )

        return

    data = await state.get_data()

    product_id = data["product_id"]

    stock = await db.stock_count(
        product_id
    )

    if quantity > stock:

        await message.answer(
            f"❌ Only {stock} vouchers are available."
        )

        return

    await state.clear()

    product = await db.get_product(
        product_id
    )

    total = (
        Decimal(product["price"])
        * quantity
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Continue",
                    callback_data=(
                        f"confirm:{product_id}:{quantity}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Back",
                    callback_data=(
                        f"product:{product_id}"
                    ),
                )
            ],
        ]
    )

    await message.answer(
        f"🧾 <b>ORDER SUMMARY</b>\n\n"
        f"🛍️ {product['name']}\n"
        f"🔢 Quantity: <b>{quantity}</b>\n"
        f"💰 Total: <b>₹{total:.2f}</b>\n\n"
        f"📜 Please read the Terms & Conditions before purchasing.",
        reply_markup=keyboard,
    )


# =========================================================
# CONFIRMATION
# =========================================================

async def show_confirmation(
    call,
    product_id,
    quantity,
):

    product = await db.get_product(
        product_id
    )

    if not product:

        await call.answer(
            "❌ Product unavailable.",
            show_alert=True,
        )

        return

    stock = await db.stock_count(
        product_id
    )

    if quantity > stock:

        await call.answer(
            "❌ Not enough stock.",
            show_alert=True,
        )

        return

    total = (
        Decimal(product["price"])
        * quantity
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Confirm Purchase",
                    callback_data=(
                        f"confirm:{product_id}:{quantity}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Terms & Conditions",
                    callback_data="show_terms",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Back",
                    callback_data=(
                        f"product:{product_id}"
                    ),
                )
            ],
        ]
    )

    await call.message.edit_text(
        f"🧾 <b>ORDER SUMMARY</b>\n\n"
        f"🛍️ Product: <b>{product['name']}</b>\n"
        f"🔢 Quantity: <b>{quantity}</b>\n"
        f"💰 Total: <b>₹{total:.2f}</b>\n\n"
        f"⚠️ Please verify the product before purchasing.",
        reply_markup=keyboard,
    )


# =========================================================
# CONFIRM PURCHASE
# =========================================================

@dp.callback_query(
    F.data.startswith("confirm:")
)
async def confirm_purchase(
    call: CallbackQuery,
    state: FSMContext,
):

    _, product_id, quantity = (
        call.data.split(":")
    )

    product_id = int(product_id)
    quantity = int(quantity)

    try:

        order_id, amount, product_name = (
            await db.create_order(
                call.from_user.id,
                product_id,
                quantity,
            )
        )

    except ValueError as error:

        await call.answer(
            str(error),
            show_alert=True,
        )

        return

    await state.set_state(
        UserStates.utr
    )

    await state.update_data(
        order_id=order_id
    )

    await call.message.edit_text(
        f"🧾 <b>ORDER #{order_id}</b>\n\n"
        f"🛍️ {product_name}\n"
        f"🔢 Quantity: <b>{quantity}</b>\n"
        f"💰 Amount: <b>₹{Decimal(amount):.2f}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💳 <b>PAYMENT DETAILS</b>\n\n"
        f"UPI ID:\n"
        f"<code>{UPI_ID}</code>\n\n"
        f"Pay exactly:\n"
        f"<b>₹{Decimal(amount):.2f}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"📤 After payment, send your "
        f"<b>UTR / Transaction ID</b> here.\n\n"
        f"⚠️ Never send OTP, UPI PIN or password."
    )

    await call.answer(
        "🧾 Order created!"
    )


# =========================================================
# UTR
# =========================================================

@dp.message(
    UserStates.utr
)
async def receive_utr(
    message: Message,
    state: FSMContext,
):

    utr = message.text.strip()

    if len(utr) < 6 or len(utr) > 100:

        await message.answer(
            "❌ Please enter a valid UTR / Transaction ID."
        )

        return

    data = await state.get_data()

    order_id = data.get("order_id")

    if not order_id:

        await state.clear()

        await message.answer(
            "❌ Order session expired. Please create a new order."
        )

        return

    success = await db.set_utr(
        order_id,
        message.from_user.id,
        utr,
    )

    await state.clear()

    if not success:

        await message.answer(
            "❌ This order is no longer accepting UTR."
        )

        return

    
