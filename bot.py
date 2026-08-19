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

    defaults = {
        "welcome": DEFAULT_WELCOME,
        "terms": DEFAULT_TERMS,
        "channels": ",".join(REQUIRED_CHANNELS),
    }

    for key, value in defaults.items():

        existing = await db.get_setting(key)

        if existing == "":
            await db.set_setting(
                key,
                value
            )


async def get_setting(key):
    return await db.get_setting(key)

async def set_setting(key, value):
    await db.set_setting(key, value)


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

    products = await db.get_active_products()

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

    order = await db.get_order(order_id)

    await state.clear()

    if not success:
        await message.answer(
            "❌ This order is no longer accepting UTR."
        )

        return

    await message.answer(
        f"⏳ <b>PAYMENT SUBMITTED</b>\n\n"
        f"🧾 Order: <b>#{order_id}</b>\n"
        f"💰 Amount: <b>₹{Decimal(order['amount']):.2f}</b>\n"
        f"🟡 Status: <b>Pending Verification</b>\n\n"
        f"👨‍💻 Payment will be checked by the admin.\n"
        f"🎟️ Your voucher will be delivered after verification.",
        reply_markup=main_menu(),
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Approve",
                    callback_data=f"approve:{order_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Reject",
                    callback_data=f"reject:{order_id}",
                ),
            ]
        ]
    )

    admin_text = (
        f"🔔 <b>NEW PAYMENT</b>\n\n"
        f"🧾 Order: <b>#{order_id}</b>\n"
        f"👤 User ID: <code>{message.from_user.id}</code>\n"
        f"👤 Username: @{message.from_user.username or 'N/A'}\n"
        f"🛍️ Product: {order['product_name']}\n"
        f"🔢 Quantity: {order['qty']}\n"
        f"💰 Amount: ₹{Decimal(order['amount']):.2f}\n"
        f"🔢 UTR: <code>{utr}</code>"
    )

    for admin_id in ADMIN_IDS:

        try:

            await bot.send_message(
                admin_id,
                admin_text,
                reply_markup=keyboard,
            )

        except Exception:

            logging.exception(
                "Failed to notify admin %s",
                admin_id,
            )


# =========================================================
# MY ORDERS
# =========================================================

@dp.message(
    F.text == "🧾 My Orders"
)
async def my_orders(
    message: Message,
):

    orders = await db.user_orders(
        message.from_user.id
    )

    if not orders:

        await message.answer(
            "🧾 <b>MY ORDERS</b>\n\n"
            "You don't have any orders yet."
        )

        return

    text = "🧾 <b>MY ORDERS</b>\n\n"

    for order in orders:

        text += (
            f"🆔 <b>#{order['id']}</b>\n"
            f"🛍️ {order['product_name']}\n"
            f"🔢 Qty: {order['qty']}\n"
            f"💰 ₹{Decimal(order['amount']):.2f}\n"
            f"📌 Status: <b>{order['status']}</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
        )

    await message.answer(text)


# =========================================================
# RECOVER VOUCHERS
# =========================================================

@dp.message(
    F.text == "🎟️ Recover Vouchers"
)
async def recover_start(
    message: Message,
    state: FSMContext,
):

    await state.set_state(
        UserStates.recover_order
    )

    await message.answer(
        "🎟️ <b>RECOVER VOUCHERS</b>\n\n"
        "Send your approved Order ID.\n\n"
        "Example:\n"
        "<code>1024</code>"
    )


@dp.message(
    UserStates.recover_order
)
async def recover_order(
    message: Message,
    state: FSMContext,
):

    try:

        order_id = int(
            message.text.strip()
        )

    except ValueError:

        await message.answer(
            "❌ Please send only the Order ID."
        )

        return

    await state.clear()

    codes = await db.order_codes(
        order_id,
        message.from_user.id,
    )

    if codes is None:

        await message.answer(
            "❌ Order not found, or the order has not been approved yet."
        )

        return

    code_text = "\n".join(
        f"🎟️ <code>{code}</code>"
        for code in codes
    )

    await message.answer(
        f"🎟️ <b>YOUR VOUCHERS</b>\n\n"
        f"🧾 Order: <b>#{order_id}</b>\n\n"
        f"{code_text}\n\n"
        f"🔐 Keep these codes private."
    )


# =========================================================
# REFER & EARN
# =========================================================

@dp.message(
    F.text == "🎁 Refer & Earn"
)
async def refer_earn(
    message: Message,
):

    points = await db.user_points(
        message.from_user.id
    )

    me = await bot.get_me()

    referral_link = (
        f"https://t.me/"
        f"{me.username}"
        f"?start="
        f"{message.from_user.id}"
    )

    await message.answer(
        f"🎁 <b>REFER & EARN</b>\n\n"
        f"⭐ Your Points: <b>{points}</b>\n\n"
        f"👥 Invite your friends using your personal referral link.\n\n"
        f"🎯 When your referred user completes their "
        f"first successful purchase, you receive:\n\n"
        f"💎 <b>+{REFERRAL_REWARD} POINT</b>\n\n"
        f"🔗 <b>Your Referral Link</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"🚀 Share & earn!"
    )


# =========================================================
# MY POINTS
# =========================================================

@dp.message(
    F.text == "💰 My Points"
)
async def my_points(
    message: Message,
):

    points = await db.user_points(
        message.from_user.id
    )

    await message.answer(
        f"💰 <b>MY POINTS</b>\n\n"
        f"⭐ Available Points: <b>{points}</b>\n\n"
        f"🎁 Earn more by referring friends."
    )


# =========================================================
# SUPPORT
# =========================================================

@dp.message(
    F.text == "🆘 Support"
)
async def support(
    message: Message,
):

    if SUPPORT_USERNAME:

        username = (
            SUPPORT_USERNAME
            .replace("@", "")
            .strip()
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💬 Contact Support",
                        url=f"https://t.me/{username}",
                    )
                ]
            ]
        )

        await message.answer(
            "🆘 <b>SUPPORT CENTER</b>\n\n"
            "Having a problem with your order?\n"
            "Our support team is ready to help.",
            reply_markup=keyboard,
        )

    else:

        await message.answer(
            "🆘 <b>SUPPORT CENTER</b>\n\n"
            "Please contact the administrator."
        )


# =========================================================
# TERMS
# =========================================================

@dp.message(
    F.text == "📜 Terms & Conditions"
)
async def terms(
    message: Message,
):

    text = await get_setting(
        "terms"
    )

    await message.answer(
        text or DEFAULT_TERMS
    )


@dp.callback_query(
    F.data == "show_terms"
)
async def show_terms(
    call: CallbackQuery,
):

    text = await get_setting(
        "terms"
    )

    await call.message.answer(
        text or DEFAULT_TERMS
    )

    await call.answer()


# =========================================================
# HOME
# =========================================================

@dp.callback_query(
    F.data == "go_home"
)
async def go_home(
    call: CallbackQuery,
):

    await call.message.answer(
        await get_setting("welcome")
        or DEFAULT_WELCOME,
        reply_markup=main_menu(),
    )

    await call.answer()

# =========================================================
# ADMIN PANEL
# =========================================================

def admin_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Add Product",
                    callback_data="admin:add_product",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📦 Add Voucher Stock",
                    callback_data="admin:add_stock",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Change Price",
                    callback_data="admin:change_price",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Products & Stock",
                    callback_data="admin:products",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Product ON / OFF",
                    callback_data="admin:toggle_products",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 Pending Payments",
                    callback_data="admin:pending",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📢 Manage Channels",
                    callback_data="admin:channels",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Change Welcome",
                    callback_data="admin:welcome",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Change Terms",
                    callback_data="admin:terms",
                )
            ],
        ]
    )


@dp.message(Command("admin"))
async def admin_panel(
    message: Message,
):

    if not is_admin(
        message.from_user.id
    ):
        return

    await message.answer(
        "👑 <b>DEF VOUCHER ADMIN PANEL</b>\n\n"
        "Select an option:",
        reply_markup=admin_keyboard(),
    )


# =========================================================
# ADMIN — ADD PRODUCT
# =========================================================

@dp.callback_query(
    F.data == "admin:add_product"
)
async def admin_add_product(
    call: CallbackQuery,
    state: FSMContext,
):

    if not is_admin(
        call.from_user.id
    ):
        return

    await state.set_state(
        AdminStates.add_product
    )

    await call.message.answer(
        "➕ <b>ADD PRODUCT</b>\n\n"
        "Send details in this format:\n\n"
        "<code>Name | Price | Description</code>\n\n"
        "Example:\n"
        "<code>Shein ₹500 | 450 | ₹500 voucher with applicable conditions</code>"
    )

    await call.answer()


@dp.message(
    AdminStates.add_product
)
async def admin_add_product_message(
    message: Message,
    state: FSMContext,
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()
        return

    parts = message.text.split(
        "|",
        2,
    )

    if len(parts) != 3:

        await message.answer(
            "❌ Invalid format.\n\n"
            "<code>Name | Price | Description</code>"
        )

        return

    name = parts[0].strip()
    price_text = parts[1].strip()
    description = parts[2].strip()

    try:

        price = Decimal(price_text)

        if price <= 0:
            raise ValueError

    except Exception:

        await message.answer(
            "❌ Invalid price."
        )

        return

    product_id = await db.add_product(
        name,
        description,
        price,
    )

    await state.clear()

    await message.answer(
        f"✅ <b>PRODUCT ADDED</b>\n\n"
        f"🆔 ID: <code>{product_id}</code>\n"
        f"🛍️ {name}\n"
        f"💰 ₹{price:.2f}"
    )


# =========================================================
# ADMIN — ADD STOCK
# =========================================================

@dp.callback_query(
    F.data == "admin:add_stock"
)
async def admin_stock_products(
    call: CallbackQuery,
):

    if not is_admin(
        call.from_user.id
    ):
        return

    products = await db.get_products()

    if not products:

        await call.answer(
            "Create a product first.",
            show_alert=True,
        )

        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=product["name"],
                    callback_data=(
                        f"admin_stock:{product['id']}"
                    ),
                )
            ]
            for product in products
        ]
    )

    await call.message.answer(
        "📦 <b>SELECT PRODUCT</b>",
        reply_markup=keyboard,
    )

    await call.answer()


@dp.callback_query(
    F.data.startswith("admin_stock:")
)
async def admin_stock_select(
    call: CallbackQuery,
    state: FSMContext,
):

    if not is_admin(
        call.from_user.id
    ):
        return

    product_id = int(
        call.data.split(":")[1]
    )

    await state.set_state(
        AdminStates.add_stock
    )

    await state.update_data(
        product_id=product_id
    )

    await call.message.answer(
        "📦 <b>ADD VOUCHER CODES</b>\n\n"
        "Send one code per line.\n\n"
        "Example:\n"
        "<code>"
        "ABC123\n"
        "XYZ456\n"
        "DEF789"
        "</code>"
    )

    await call.answer()


@dp.message(
    AdminStates.add_stock
)
async def admin_stock_message(
    message: Message,
    state: FSMContext,
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()
        return

    data = await state.get_data()

    product_id = data["product_id"]

    codes = [
        code.strip()
        for code in message.text.splitlines()
        if code.strip()
    ]

    if not codes:

        await message.answer(
            "❌ No voucher codes received."
        )

        return

    added = await db.add_vouchers(
        product_id,
        codes,
    )

    current_stock = await db.stock_count(
        product_id
    )

    await state.clear()

    await message.answer(
        f"📦 <b>STOCK UPDATED</b>\n\n"
        f"✅ Added: <b>{added}</b> codes\n"
        f"📊 Current Stock: <b>{current_stock}</b>"
    )


# =========================================================
# ADMIN — CHANGE PRICE
# =========================================================

@dp.callback_query(
    F.data == "admin:change_price"
)
async def admin_price_products(
    call: CallbackQuery,
):

    if not is_admin(
        call.from_user.id
    ):
        return

    products = await db.get_products()

    if not products:

        await call.answer(
            "No products available.",
            show_alert=True,
        )

        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=product["name"],
                    callback_data=(
                        f"admin_price:{product['id']}"
                    ),
                )
            ]
            for product in products
        ]
    )

    await call.message.answer(
        "💰 <b>SELECT PRODUCT</b>",
        reply_markup=keyboard,
    )

    await call.answer()


@dp.callback_query(
    F.data.startswith("admin_price:")
)
async def admin_price_select(
    call: CallbackQuery,
    state: FSMContext,
):

    if not is_admin(
        call.from_user.id
    ):
        return

    product_id = int(
        call.data.split(":")[1]
    )

    await state.set_state(
        AdminStates.change_price
    )

    await state.update_data(
        product_id=product_id
    )

    await call.message.answer(
        "💰 <b>NEW PRICE</b>\n\n"
        "Send the new price.\n\n"
        "Example: <code>399</code>"
    )

    await call.answer()


@dp.message(
    AdminStates.change_price
)
async def admin_change_price(
    message: Message,
    state: FSMContext,
):

    if not is_admin(
        message.from_user.id
    ):

        await state.clear()
        return

    try:

        price = Decimal(
            message.text.strip()
        )

        if price <= 0:
            raise ValueError

    except Exception:

        await message.answer(
            "❌ Invalid price."
        )

        return

    data = await state.get_data()

    await db._pool.execute(
        """
        UPDATE products
        SET price=$1
        WHERE id=$2
        """,
        price,
        data["product_id"],
    )

    await state.clear()

    await message.answer(
        f"✅ <b>PRICE UPDATED</b>\n\n"
        f"New Price: <b>₹{price:.2f}</b>"
    )


# =========================================================
# ADMIN — PRODUCTS & STOCK
# =========================================================

@dp.callback_query(
    F.data == "admin:products"
)
async def admin_products(
    call: CallbackQuery,
):

    if not is_admin(
        call.from_user.id
    ):
        return

    products = await db.get_products()

    if not products:

        await call.message.answer(
            "📊 No products found."
        )

        await call.answer()
        return

    text = "📊 <b>PRODUCTS & STOCK</b>\n\n"

    for product in products:

        text += (
            f"🆔 #{product['id']}\n"
            f"🛍️ {product['name']}\n"
            f"💰 ₹{Decimal(product['price']):.2f}\n"
            f"📦 Stock: {product['stock']}\n"
            f"━━━━━━━━━━━━━━━━\n"
        )

    await call.message.answer(
        text
    )

    await call.answer()

# =========================================================
# ADMIN — PRODUCT ON / OFF
# =========================================================

@dp.callback_query(
    F.data == "admin:toggle_products"
)
async def admin_toggle_products(
    call: CallbackQuery,
):

    if not is_admin(call.from_user.id):
        return

    products = await db.get_products()

    if not products:
        await call.answer(
            "No products available.",
            show_alert=True,
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "🟢 " if product["active"]
                        else "🔴 "
                    ) + product["name"],
                    callback_data=(
                        f"toggle_product:{product['id']}"
                    ),
                )
            ]
            for product in products
        ]
    )

    await call.message.answer(
        "🔄 <b>PRODUCT ON / OFF</b>\n\n"
        "🟢 ON = Product active\n"
        "🔴 OFF = Product disabled\n\n"
        "Tap a product 👇",
        reply_markup=keyboard,
    )

    await call.answer()


@dp.callback_query(
    F.data.startswith("toggle_product:")
)
async def toggle_product(
    call: CallbackQuery,
):

    if not is_admin(call.from_user.id):
        return

    product_id = int(
        call.data.split(":")[1]
    )

    product = await db.get_product(
        product_id
    )

    if not product:
        await call.answer(
            "❌ Product not found.",
            show_alert=True,
        )
        return

    new_status = not product["active"]

    success = await db.set_product_status(
        product_id,
        new_status,
    )

    if not success:
        await call.answer(
            "❌ Could not update product.",
            show_alert=True,
        )
        return

    await call.answer(
        f"{product['name']} → "
        f"{'🟢 ON' if new_status else '🔴 OFF'}"
    )

# =========================================================
# ADMIN — PENDING PAYMENTS
# =========================================================

def payment_keyboard(order_id):

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Approve",
                    callback_data=f"approve:{order_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Reject",
                    callback_data=f"reject:{order_id}",
                ),
            ]
        ]
    )


@dp.callback_query(
    F.data == "admin:pending"
)
async def admin_pending(
    call: CallbackQuery,
):

    if not is_admin(
        call.from_user.id
    ):
        return

    orders = await db.pending_orders()

    if not orders:

        await call.message.answer(
            "💳 <b>Pending Payments</b>\n\n"
            "No pending payments."
        )

        await call.answer()
        return

    for order in orders:

        await call.message.answer(
            f"💳 <b>PENDING PAYMENT</b>\n\n"
            f"🧾 Order: <b>#{order['id']}</b>\n"
            f"👤 User ID: <code>{order['tg_id']}</code>\n"
            f"👤 Username: @{order['username'] or 'N/A'}\n"
            f"🛍️ Product: {order['product_name']}\n"
            f"🔢 Qty: {order['qty']}\n"
            f"💰 Amount: ₹{Decimal(order['amount']):.2f}\n"
            f"🔢 UTR: <code>{order['utr']}</code>",
            reply_markup=payment_keyboard(
                order["id"]
            ),
        )

    await call.answer()


# =========================================================
# ADMIN — APPROVE PAYMENT
# =========================================================

@dp.callback_query(
    F.data.startswith("approve:")
)
async def approve_order(
    call: CallbackQuery,
):

    if not is_admin(
        call.from_user.id
    ):
        return

    order_id = int(
        call.data.split(":")[1]
    )

    try:

        order, codes = await db.approve_order(
            order_id,
            REFERRAL_REWARD,
        )

    except ValueError as error:

        await call.answer(
            str(error),
            show_alert=True,
        )

        return

    if not order:

        await call.answer(
            "❌ Order already processed.",
            show_alert=True,
        )

        return

    code_text = "\n".join(
        f"🎟️ <code>{code}</code>"
        for code in codes
    )

    await bot.send_message(
        order["tg_id"],
        f"🎉 <b>PAYMENT VERIFIED!</b>\n\n"
        f"🧾 Order: <b>#{order_id}</b>\n"
        f"💰 Payment: <b>Verified ✅</b>\n\n"
        f"🎟️ <b>YOUR VOUCHER CODE(S)</b>\n\n"
        f"{code_text}\n\n"
        f"🔐 Keep your codes private.\n\n"
        f"❤️ Thank you for shopping with us!",
    )

    await call.message.edit_reply_markup(
        reply_markup=None
    )

    await call.answer(
        "✅ Approved & delivered!"
    )


# =========================================================
# ADMIN — REJECT PAYMENT
# =========================================================

@dp.callback_query(
    F.data.startswith("reject:")
)
async def reject_order(
    call: CallbackQuery,
):

    if not is_admin(
        call.from_user.id
    ):
        return

    order_id = int(
        call.data.split(":")[1]
    )

    success = await db.reject_order(
        order_id
    )

    if not success:

        await call.answer(
            "❌ Order already processed.",
            show_alert=True,
        )

        return

    order = await db.get_order(
        order_id
    )

    if order:

        await bot.send_message(
            order["tg_id"],
            f"❌ <b>PAYMENT REJECTED</b>\n\n"
            f"🧾 Order: <b>#{order_id}</b>\n\n"
            f"Your payment could not be verified.\n\n"
            f"🆘 Please contact support if you believe this is an error.",
        )

    await call.message.edit_reply_markup(
        reply_markup=None
    )

    await call.answer(
        "❌ Payment rejected."
        )

# =========================================================
# ADMIN — CHANNEL MANAGEMENT
# =========================================================

@dp.callback_query(
    F.data == "admin:channels"
)
async def admin_channels(
    call: CallbackQuery,
):

    if not is_admin(call.from_user.id):
        return

    channels = await get_required_channels()

    if channels:
        current = "\n".join(
            f"📢 {channel}"
            for channel in channels
        )
    else:
        current = "❌ No required channel configured."

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Set Channel(s)",
                    callback_data="channel:set",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑️ Remove All",
                    callback_data="channel:remove",
                )
            ],
        ]
    )

    await call.message.answer(
        f"📢 <b>CHANNEL SETTINGS</b>\n\n"
        f"<b>Current channels:</b>\n"
        f"{current}\n\n"
        f"⚠️ Channel membership is compulsory.",
        reply_markup=keyboard,
    )

    await call.answer()


@dp.callback_query(
    F.data == "channel:set"
)
async def channel_set(
    call: CallbackQuery,
    state: FSMContext,
):

    if not is_admin(call.from_user.id):
        return

    await state.set_state(
        AdminStates.channel
    )

    await call.message.answer(
        "📢 <b>SET REQUIRED CHANNEL(S)</b>\n\n"
        "Send channel username.\n\n"
        "Single channel:\n"
        "<code>@mychannel</code>\n\n"
        "Multiple channels:\n"
        "<code>@channel1,@channel2</code>"
    )

    await call.answer()


@dp.message(
    AdminStates.channel
)
async def save_channel(
    message: Message,
    state: FSMContext,
):

    if not is_admin(message.from_user.id):

        await state.clear()
        return

    channels = [
        x.strip()
        for x in message.text.split(",")
        if x.strip()
    ]

    if not channels:

        await message.answer(
            "❌ Please provide at least one channel."
        )

        return

    for channel in channels:

        if not channel.startswith("@"):

            await message.answer(
                "❌ Invalid channel format.\n\n"
                "Example:\n"
                "<code>@mychannel</code>"
            )

            return

    await set_setting(
        "channels",
        ",".join(channels),
    )

    await state.clear()

    await message.answer(
        "✅ <b>CHANNELS UPDATED</b>\n\n"
        "📢 Users must join the configured "
        "channel(s) before using the bot."
    )


@dp.callback_query(
    F.data == "channel:remove"
)
async def remove_channels(
    call: CallbackQuery,
):

    if not is_admin(call.from_user.id):
        return

    await set_setting(
        "channels",
        "",
    )

    await call.answer(
        "✅ Channels removed."
    )

    await call.message.answer(
        "📢 Required channel verification "
        "has been disabled."
    )


# =========================================================
# ADMIN — CHANGE WELCOME
# =========================================================

@dp.callback_query(
    F.data == "admin:welcome"
)
async def change_welcome(
    call: CallbackQuery,
    state: FSMContext,
):

    if not is_admin(call.from_user.id):
        return

    await state.set_state(
        AdminStates.welcome
    )

    await call.message.answer(
        "✏️ <b>CHANGE WELCOME MESSAGE</b>\n\n"
        "Send the new welcome message.\n\n"
        "HTML formatting is supported.\n\n"
        "Example:\n"
        "<code>&lt;b&gt;Welcome!&lt;/b&gt;</code>"
    )

    await call.answer()


@dp.message(
    AdminStates.welcome
)
async def save_welcome(
    message: Message,
    state: FSMContext,
):

    if not is_admin(message.from_user.id):

        await state.clear()
        return

    if not message.text:

        await message.answer(
            "❌ Please send text."
        )

        return

    await set_setting(
        "welcome",
        message.text,
    )

    await state.clear()

    await message.answer(
        "✅ <b>WELCOME MESSAGE UPDATED</b>"
    )


# =========================================================
# ADMIN — CHANGE TERMS
# =========================================================

@dp.callback_query(
    F.data == "admin:terms"
)
async def change_terms(
    call: CallbackQuery,
    state: FSMContext,
):

    if not is_admin(call.from_user.id):
        return

    await state.set_state(
        AdminStates.terms
    )

    await call.message.answer(
        "📜 <b>CHANGE TERMS & CONDITIONS</b>\n\n"
        "Send the new Terms & Conditions.\n\n"
        "HTML formatting is supported."
    )

    await call.answer()


@dp.message(
    AdminStates.terms
)
async def save_terms(
    message: Message,
    state: FSMContext,
):

    if not is_admin(message.from_user.id):

        await state.clear()
        return

    if not message.text:

        await message.answer(
            "❌ Please send text."
        )

        return

    await set_setting(
        "terms",
        message.text,
    )

    await state.clear()

    await message.answer(
        "✅ <b>TERMS & CONDITIONS UPDATED</b>"
    )


# =========================================================
# BOT STARTUP
# =========================================================

async def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing."
        )

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is missing."
        )

    await db.init_db(
        DATABASE_URL
    )

    await init_settings()

    logging.info(
        "🚀 DEF Voucher Bot started"
    )

    try:

        await bot.delete_webhook(
            drop_pending_updates=True
        )

        await dp.start_polling(
            bot
        )

    finally:

        await db.close_db()

        await bot.session.close()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    asyncio.run(main())

# =========================
# BOT COMPATIBILITY HELPERS
# =========================

async def user_points(tg_id):
    return await get_user_points(tg_id)


async def user_orders(tg_id):
    return await get_user_orders(tg_id)


async def pending_orders():
    return await get_pending_orders()


async def order_codes(order_id, tg_id):
    return await get_order_codes(order_id, tg_id)
