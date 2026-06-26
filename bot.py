# ================================= imports ====================
import os
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ======================= LOGGING ====================
logging.basicConfig(level=logging.INFO)

# ======================= BOT CONFIG ====================
BotToken = os.getenv("BOT_TOKEN")
adminID = 8581685408

if not BotToken:
    raise ValueError("BOT_TOKEN is not set!")

# ======================= START =========================
async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    keyboard = [
        ["🐞 گزارش باگ", "💬 پیشنهاد"],
        ["❓ راهنما", "تجربیات من از بازی"]
    ]

    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "👋 به بات وایرو خوش اومدی",
        reply_markup=markup
    )

# ======================= HANDLE BUTTONS =========================
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    text = update.message.text or ""
    user = update.effective_user

    # ---------------- MENU ----------------
    if text == "🐞 گزارش باگ":
        context.user_data.clear()
        context.user_data["mode"] = "bug"
        await update.message.reply_text("مشکل را بنویس یا عکس یا ویدیو بفرست")
        return

    elif text == "💬 پیشنهاد":
        context.user_data.clear()
        context.user_data["mode"] = "suggest"
        await update.message.reply_text("پیشنهادت را بنویس")
        return

    elif text == "تجربیات من از بازی":
        context.user_data.clear()
        context.user_data["mode"] = "play"
        await update.message.reply_text("تجربه‌ات را ارسال کن 🌹")
        return

    elif text == "❓ راهنما":
        await update.message.reply_text(
            "👋 راهنما:\n\n"
            "🐞 گزارش باگ\n💬 پیشنهاد\n🎮 تجربه بازی\n\n"
            "👨‍💻 VIRO Studio\n📞 @Khan213187"
        )
        return

    # ======================= BUG =========================
    if context.user_data.get("mode") == "bug":

        await send_to_admin(update, context, user, "🚨 BUG REPORT")
        return

    # ======================= SUGGEST =========================
    if context.user_data.get("mode") == "suggest":

        await send_to_admin(update, context, user, "💡 SUGGESTION")
        return

    # ======================= PLAY =========================
    if context.user_data.get("mode") == "play":

        await send_to_admin(update, context, user, "🎮 EXPERIENCE")
        return

    await update.message.reply_text("❌ لطفاً یکی از گزینه‌ها را انتخاب کن")

# ======================= SEND FUNCTION (ANTI CRASH) =========================
async def send_to_admin(update, context, user, title):

    msg = update.message

    caption = msg.caption or ""
    text = msg.text or ""

    try:

        if msg.text:

            await context.bot.send_message(
                chat_id=adminID,
                text=f"""
{title}

👤 {user.full_name}
🆔 {user.id}

📝 {text}
"""
            )

        elif msg.photo:

            await context.bot.send_photo(
                chat_id=adminID,
                photo=msg.photo[-1].file_id,
                caption=f"""
{title} (PHOTO)

👤 {user.full_name}
🆔 {user.id}

📝 {caption}
"""
            )

        elif msg.video:

            await context.bot.send_video(
                chat_id=adminID,
                video=msg.video.file_id,
                caption=f"""
{title} (VIDEO)

👤 {user.full_name}
🆔 {user.id}

📝 {caption}
"""
            )

        else:
            await update.message.reply_text("❌ فقط متن یا عکس یا ویدیو بفرست")
            return

        await update.message.reply_text("✅ ارسال شد")
        context.user_data["mode"] = None

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ خطا در ارسال")

# ======================= APP =========================
app = Application.builder().token(BotToken).build()

app.add_handler(CommandHandler("start", start_bot))
app.add_handler(MessageHandler(filters.ALL, handle_buttons))

print("Bot is running...")
app.run_polling()
