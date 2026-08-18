import os
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- CONFIGURATION (Railway Variables se aayega) ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "123456789"))
UPI_ID = os.getenv("UPI_ID", "yourname@upi")

# Mandatory Force Join Channels Username (without @)
REQUIRED_CHANNELS = ["Dailynewloots235", "shein577"]

# Database Setup
def init_db():
    conn = sqlite3.connect("store.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            price_per_unit REAL,
            stock INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            code_text TEXT,
            status TEXT DEFAULT 'UNUSED'
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- FORCE JOIN CHECKER ---
async def check_force_join(user_id, context):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=f"@{channel}", user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    return True

# --- 1. /START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_joined = await check_force_join(user_id, context)

    if not is_joined:
        buttons = [
            [InlineKeyboardButton(f"📍 Join @{ch}", url=f"https://t.me/{ch}")] for ch in REQUIRED_CHANNELS
        ]
        buttons.append([InlineKeyboardButton("❤️ I've Joined — Verify", callback_data="verify_join")])
        
        await update.message.reply_text(
            f"🐮 **Welcome to Voucher Shop Bot!**\n\n"
            f"Join compulsory channels to continue.\n"
            f"After joining, tap **Verify** below.",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
        return

    # Bottom Permanent Menu (Reply Keyboard)
    reply_keyboard = [
        ["🧠 Buy Vouchers", "🎒 My Orders"],
        ["💥 Recover Vouchers", "🌟 Support"],
        ["🎁 Refer & Earn"]
    ]
    markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "👋 **Welcome to Code Store!** Select an option below:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# Verification Button Callback
async def verify_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if await check_force_join(user_id, context):
        await query.message.delete()
        reply_keyboard = [
            ["🧠 Buy Vouchers", "🎒 My Orders"],
            ["💥 Recover Vouchers", "🌟 Support"],
            ["🎁 Refer & Earn"]
        ]
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ Verification successful! Welcome to the Store.",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
        )
    else:
        await query.answer("❌ Aapne abhi tak saare channels join nahi kiye hain!", show_alert=True)

# --- 2. SHOW VOUCHERS LIST ---
async def show_vouchers_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Dynamic Category List with In Stock / Out of Stock Indicators
    keyboard = [
        [InlineKeyboardButton("👑 Shein 1000 per 800 off — 🟢 IN STOCK", callback_data="prod_shein_800")],
        [InlineKeyboardButton("👑 Bigbasket 349 per 160 cashback — 🟢 IN STOCK", callback_data="prod_bb_160")],
        [InlineKeyboardButton("👓 Buy Lenskart 1 year discount — 🔴 OUT OF STOCK", callback_data="prod_lenskart")],
        [InlineKeyboardButton("🎧 Audible 2 Month coupon — 🟢 IN STOCK", callback_data="prod_audible")],
        [InlineKeyboardButton("👑 Amazon gift card ₹20 — 🔴 OUT OF STOCK", callback_data="prod_amz20")]
    ]
    
    await update.message.reply_text(
        "🧠 **Choose a Service**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# --- 3. PRODUCT DETAILS & QUANTITY SELECTION ---
async def product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if "OUT OF STOCK" in query.data or "lenskart" in query.data or "amz20" in query.data:
        await query.answer("⚠️ This item is currently OUT OF STOCK!", show_alert=True)
        return

    # Sample details for Shein
    unit_price = 114.78
    context.user_data["selected_price"] = unit_price

    msg = (
        "**Shein 1000 per 800 off**\n\n"
        "SHEIN 👋 800 Off on 😃 1000\n"
        "🟢 Applicable on All SHEIN Products\n"
        "⭐ Instant use bale lena okok\n\n"
        "🟢 **Availability:** IN STOCK\n"
        f"**Price:** ₹{unit_price} per code\n\n"
        "Select option:"
    )

    qty_keyboard = [
        [
            InlineKeyboardButton(f"✅ 1 code — ₹{unit_price}", callback_data="qty_1"),
            InlineKeyboardButton(f"✅ 5 codes — ₹{round(unit_price*5, 2)}", callback_data="qty_5")
        ],
        [
            InlineKeyboardButton(f"✅ 10 codes — ₹{round(unit_price*10, 2)}", callback_data="qty_10"),
            InlineKeyboardButton("🔢 Other amount", callback_data="qty_custom")
        ],
        [InlineKeyboardButton("⭐ Back", callback_data="back_to_store")]
    ]

    await query.edit_message_text(text=msg, reply_markup=InlineKeyboardMarkup(qty_keyboard), parse_mode="Markdown")

# --- 4. TERMS & CONDITIONS / AGREE ---
async def show_tnc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    qty = int(query.data.split("_")[1]) if "qty_" in query.data else 1
    price = context.user_data.get("selected_price", 114.78)
    total_amount = round(qty * price, 2)
    context.user_data["total_amount"] = total_amount

    tnc_text = (
        "🥂 **Terms & Conditions**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "All Vouchers Provided are Applicable on Products.\n"
        "Use the Vouchers at the same day when purchased to avoid expiry.\n"
        " Video recording required during checkout for any warranty claims.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Service:** Shein 1000 per 800 off\n"
        f"**Qty:** {qty} | **Amount:** ₹{total_amount}\n\n"
        "Tap **I Agree** to confirm and generate Payment QR."
    )

    confirm_keyboard = [
        [InlineKeyboardButton("✅ I Agree & Pay Now", callback_data="pay_now")],
        [InlineKeyboardButton("⭐ Back", callback_data="back_to_store")]
    ]

    await query.edit_message_text(text=tnc_text, reply_markup=InlineKeyboardMarkup(confirm_keyboard), parse_mode="Markdown")

# --- 5. PAYMENT QR GENERATION ---
async def generate_payment_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    amount = context.user_data.get("total_amount", 114.78)
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=upi://pay?pa={UPI_ID}&am={amount}&cu=INR"

    caption = (
        f"💰 **Total Payable Amount:** ₹{amount}\n"
        f"📲 **UPI ID:** `{UPI_ID}`\n\n"
        f"1. QR code scan karke exact payment karein.\n"
        f"2. Payment screenshot aur UTR yahan chat me bhej dein."
    )

    await query.message.delete()
    await context.bot.send_photo(chat_id=query.from_user.id, photo=qr_url, caption=caption, parse_mode="Markdown")

# Main Function
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify_join_callback, pattern="^verify_join$"))
    app.add_handler(MessageHandler(filters.Regex("^🧠 Buy Vouchers$"), show_vouchers_menu))
    app.add_handler(CallbackQueryHandler(product_detail, pattern="^prod_"))
    app.add_handler(CallbackQueryHandler(show_tnc, pattern="^qty_"))
    app.add_handler(CallbackQueryHandler(generate_payment_qr, pattern="^pay_now$"))

    print("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
         
