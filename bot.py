# ================================= imports ====================
import logging
from telegram import Update, ReplyKeyboardMarkup
import os
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ======================= Bot Token ====================
BotToken = os.getenv("BOT_TOKEN")
adminID = 8581685408
logging.basicConfig(level=logging.INFO)
# =====================================================


# ======================= START =========================
async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        ["🐞 گزارش باگ", "💬 پیشنهاد"],
        ["❓ راهنما", "تجربیات من از بازی"]
    ]

    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "👋 به بات وایرو خوش اومدی",
        reply_markup=markup
    )


# ======================= HANDLER =========================
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    user = update.effective_user

    # ================= reset states (FIXED) =================
    if text == "🐞 گزارش باگ":
        context.user_data["reportBug"] = True   # ❌ no reset full dict
        await update.message.reply_text("مشکل را بنویس یا عکس یا ویدیو ارسال کن")
        return

    elif text == "💬 پیشنهاد":
        context.user_data["Suggestion"] = True
        await update.message.reply_text("پیشنهادت را بنویس")
        return

    elif text == "تجربیات من از بازی":
        context.user_data["playTime"] = True
        await update.message.reply_text("تجربه‌ات را ارسال کن 🌹")
        return

    elif text == "❓ راهنما":
        await update.message.reply_text(
            """
👋 سلام، به بخش راهنما خوش آمدی.

🐞 گزارش باگ: میتونی باگ ها رو با ویدیو یا عکس به ما نشون بدی
💬 پیشنهاد: ایده برای بازی
🎮 تجربه: تجربت رو به ما بگو از تجربت ویدیو ه بده لطفا 

👨‍💻 سازنده: استودیو VIRO
📞 @Khan213187
"""
        )
        return


    # ================= BUG REPORT =================
    if context.user_data.get("reportBug"):

        caption = update.message.caption or ""
        text_msg = update.message.text or ""

        if update.message.text:

            await context.bot.send_message(
                chat_id=adminID,
                text=f"""
🚨 BUG REPORT

👤 Name: {user.full_name}
🆔 ID: {user.id}
📛 Username: @{user.username or "No Username"}

📝 Text:
{text_msg}
"""
            )

        elif update.message.photo:

            await context.bot.send_photo(
                chat_id=adminID,
                photo=update.message.photo[-1].file_id,
                caption=f"""
🚨 BUG REPORT (PHOTO)

👤 {user.full_name}
🆔 {user.id}

📝 {caption}
"""
            )

        elif update.message.video:

            await context.bot.send_video(
                chat_id=adminID,
                video=update.message.video.file_id,
                caption=f"""
🚨 BUG REPORT (VIDEO)

👤 {user.full_name}
🆔 {user.id}

📝 {caption}
"""
            )

        else:
            await update.message.reply_text("❌ فقط متن یا عکس یا ویدیو بفرست")
            return

        await update.message.reply_text("✅ گزارش شما ارسال شد")
        context.user_data["reportBug"] = False
        return


    # ================= SUGGESTION =================
    if context.user_data.get("Suggestion"):

        caption = update.message.caption or ""

        if update.message.text:

            await context.bot.send_message(
                chat_id=adminID,
                text=f"""
💡 SUGGESTION

👤 {user.full_name}
🆔 {user.id}

📝 {update.message.text}
"""
            )

        elif update.message.photo:

            await context.bot.send_photo(
                chat_id=adminID,
                photo=update.message.photo[-1].file_id,
                caption=f"""
💡 SUGGESTION (PHOTO)

👤 {user.full_name}
🆔 {user.id}

📝 {caption}
"""
            )

        elif update.message.video:

            await context.bot.send_video(
                chat_id=adminID,
                video=update.message.video.file_id,
                caption=f"""
💡 SUGGESTION (VIDEO)

👤 {user.full_name}
🆔 {user.id}

📝 {caption}
"""
            )

        else:
            await update.message.reply_text("❌ فقط متن یا عکس یا ویدیو بفرست")
            return

        await update.message.reply_text("❤️ ممنون از پیشنهادت")
        context.user_data["Suggestion"] = False
        return


    # ================= PLAY EXPERIENCE =================
    if context.user_data.get("playTime"):

        caption = update.message.caption or ""

        if update.message.text:

            await context.bot.send_message(
                chat_id=adminID,
                text=f"""
🎮 EXPERIENCE

👤 {user.full_name}
🆔 {user.id}

📝 {update.message.text}
"""
            )

        elif update.message.photo:

            await context.bot.send_photo(
                chat_id=adminID,
                photo=update.message.photo[-1].file_id,
                caption=f"""
🎮 EXPERIENCE (PHOTO)

👤 {user.full_name}
🆔 {user.id}

📝 {caption}
"""
            )

        elif update.message.video:

            await context.bot.send_video(
                chat_id=adminID,
                video=update.message.video.file_id,
                caption=f"""
🎮 EXPERIENCE (VIDEO)

👤 {user.full_name}
🆔 {user.id}

📝 {caption}
"""
            )

        else:
            await update.message.reply_text("❌ فقط متن یا عکس یا ویدیو بفرست")
            return

        await update.message.reply_text("🌹 ممنون از تجربه‌ات")
        context.user_data["playTime"] = False
        return


    await update.message.reply_text("❌ لطفاً یکی از گزینه‌ها را انتخاب کن")


# ======================= APP =========================
app = Application.builder().token(BotToken).build()

app.add_handler(CommandHandler("start", start_bot))
app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO, handle_buttons))

print("Bot is running...")
app.run_polling()
