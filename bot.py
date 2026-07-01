import asyncio
import random
from telegram.ext import CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from functools import wraps
from telegram.constants import ChatMemberStatus
from datetime import datetime
import sqlite3
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters, CallbackContext
)

# ================== DATABASE ==================
conn = sqlite3.connect('ViroBot.db', check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS USERSPROFILE (
    user_id INTEGER PRIMARY KEY,
    player_name TEXT,
    username TEXT,
    join_date TEXT,
    coins INTEGER DEFAULT 100
)
""")

try:
    cur.execute("ALTER TABLE USERSPROFILE ADD COLUMN coins INTEGER DEFAULT 100")
    conn.commit()
except sqlite3.OperationalError:
    pass

cur.execute("""
    CREATE TABLE IF NOT EXISTS ADMINPROFILE(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER, 
    admin_name TEXT,
    admin_username TEXT,
    admin_join_date TEXT)""")

cur.execute("""
CREATE TABLE IF NOT EXISTS reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    caption TEXT,
    send_date TEXT,
    image_path TEXT,
    video_path TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS suggestion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    caption TEXT,
    send_date TEXT,
    image_path TEXT,
    video_path TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS playtime (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    caption TEXT,
    send_date TEXT,
    image_path TEXT,
    video_path TEXT
)
""")

conn.commit()

# ================== LOGGING ==================
logging.basicConfig(level=logging.INFO)

BotToken = "BOT_TOKEN"  
ADMINS_ID = [8581685408]
CHANNEL_ID = "@VirozStudiogame"


# ================== COIN FUNCTIONS ==================
def find_coin(user_id):
    cur.execute("SELECT coins FROM USERSPROFILE WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    if result:
        return result[0]
    return 0


def has_enough_coins(user_id, amount):
    coins = find_coin(user_id)
    return coins >= amount


def add_coin(user_id, amount):
    cur.execute("UPDATE USERSPROFILE SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()


def remove_coin(user_id, amount):
    cur.execute("UPDATE USERSPROFILE SET coins = coins - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()


# ================== KEYBOARDS ==================
def is_admin(user_id):
    result = cur.execute(
        "SELECT 1 FROM ADMINPROFILE WHERE admin_id = ?",
        (user_id,)
    ).fetchone()
    return result is not None


async def check_member(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        member = await context.bot.get_chat_member(
            chat_id=CHANNEL_ID,
            user_id=user_id
        )
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        ]
    except Exception as e:
        return False


def join_required(func):
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        if not await check_member(update, context):
            await update.message.reply_text(
                "لطفا جوین شو تا بتونی استفاده کنی🙃👾:\n"
                "https://t.me/VirozStudiogame"
            )
            return
        return await func(update, context, *args, **kwargs)

    return wrapper


def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🐞 گزارش باگ", "💬 پیشنهاد"],
            ["❓ راهنما", "تجربیات من از بازی"],
            ["کد هدیه🎁", "مینی گیم👾"]
        ],
        resize_keyboard=True
    )


def back_keyboard():
    return ReplyKeyboardMarkup(
        [["🔙 بازگشت"]],
        resize_keyboard=True
    )


def admin_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["کاربران👤"],
            ["تجربیات", "گزارش ها", "پیشنهادات"],
            ["افزودن ادمین", "ساخت کد هدیه"],
            ["حذف ادمین"]
        ],
        resize_keyboard=True
    )


def admin_back_keyboard():
    return ReplyKeyboardMarkup(
        [["🔙 بازگشت", "حذف اطلاعات"]],
        resize_keyboard=True
    )


# ================== SPIN KEYBOARD ==================
spin_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("💰 10 سکه", callback_data="spin_10")],
    [InlineKeyboardButton("💰 50 سکه", callback_data="spin_50")],
    [InlineKeyboardButton("💰 100 سکه", callback_data="spin_100")],
    [InlineKeyboardButton("مقدار دلخواهت رو بنویس", callback_data="spin_500")],
])


# ================== HANDLERS ==================
async def handler_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.message.from_user
    if user.id in ADMINS_ID or is_admin(user.id):
        await admin_button(update, context)
    else:
        await user_button(update, context)


# ================== SPIN HANDLER ==================
async def spin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    bet = int(query.data.split("_")[1])

    # بررسی سکه
    if not has_enough_coins(user_id, bet):
        await query.message.reply_text("❌ سکه کافی نداری.")
        return

    # کم کردن مبلغ شرط
    remove_coin(user_id, bet)

    # پیام اولیه
    msg = await query.message.reply_text("🎰 در حال چرخاندن...")

    # انیمیشن ساده
    for i in range(3):
        await asyncio.sleep(0.7)
        await msg.edit_text("🎰 در حال چرخاندن" + "." * (i + 1))

    # نتیجه
    if random.randint(1, 100) <= 45:  # 45 درصد برد
        reward = int(bet * 1.5)
        add_coin(user_id, reward)

        await msg.edit_text(
            f"🎉 برنده شدی!\n\n"
            f"💰 شرط: {bet}\n"
            f"🏆 جایزه: {reward} سکه"
        )
    else:
        await msg.edit_text(
            f"😢 باختی!\n\n"
            f"💸 {bet} سکه از دست دادی."
        )

    await query.message.delete()


# ================== START ==================
@join_required
async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not update.message:
        return

    if is_admin(user.id) or user.id in ADMINS_ID:
        keyboard = admin_keyboard()
    else:
        keyboard = main_keyboard()

    cur.execute("""
        INSERT OR IGNORE INTO USERSPROFILE (user_id, player_name, username, join_date)
        VALUES (?, ?, ?, ?)
    """, (user.id, user.first_name, user.username, join_date))
    conn.commit()

    await update.message.reply_text(
        "سلام خیلی خوش اومدی به وایرو🙃🌹",
        reply_markup=keyboard,
    )


# ================== USER BUTTON ==================
async def user_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text or ""
    user = update.effective_user
    state = context.user_data.get("state", "main")

    if state == "main":
        if text == "🔙 بازگشت":
            await update.message.reply_text(
                "شما در منوی اصلی هستید ✅",
                reply_markup=main_keyboard()
            )
            return
        elif text == "🐞 گزارش باگ":
            context.user_data["state"] = "bug"
            await update.message.reply_text(
                "متاسفیم میتوانی با عکس ویدیو یا متن مشکل را بهمون توضیح بدی",
                reply_markup=back_keyboard()
            )
            return
        elif text == "💬 پیشنهاد":
            context.user_data["state"] = "suggest"
            await update.message.reply_text(
                "وایییی پیشنهادت رو برامون بنویس",
                reply_markup=back_keyboard()
            )
            return
        elif text == "تجربیات من از بازی":
            context.user_data["state"] = "play"
            await update.message.reply_text(
                "امیدواریم که تجربه خوبی بوده باشه بفرست برامون😀",
                reply_markup=back_keyboard()
            )
            return
        elif text == "❓ راهنما":
            await update.message.reply_text(
                "👋 راهنما:\n\n🐞 گزارش باگ\n💬 پیشنهاد\n🎮 تجربه بازی\n\n👨‍💻 VIRO Studio\n📞 @Khan213187"
            )
            return
        elif text == "کد هدیه🎁":
            await update.message.reply_text(
                "میدونیم واقعا ذوق داری اما صبر کن این بخش بعدا فعال میشه 🙂"
            )
            return
        elif text == "مینی گیم👾":
            player = update.effective_user
            await update.message.reply_text(f"""
╔══════════════════════════════╗
        🎮 آرکید ویرو 🎮
╚══════════════════════════════╝

👾 بازیکن: {player.first_name or player.username}
🔥 وضعیت: آماده ورود به آرنا

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        🎲 انتخاب بازی
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎰  /luckySpin
   ✦ چرخ شانس
   💰 بختت رو امتحان کن

🧠  /quiz
   ✦ چالش هوش
   ❓ ببین چقدر باهوشی

💣  /bomb
   ✦ میدان مین
   💥 یه اشتباه = انفجار

✊  /paper
   ✦ سنگ کاغذ قیچی
   ⚔️ نبرد کلاسیک

⚔️  /killmonster
   ✦ نبرد با هیولا
   👹 زنده بمون یا حذف شو

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏆 سیستم جوایز
💰 سکه | ⭐ تجربه | 🏅 ارتقا سطح

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
▶️ روی یکی از دستورها بزن و وارد بازی شو
⚡ آرنا منتظرته...
""")
            return

    elif state == "bug":
        if text == "🔙 بازگشت":
            context.user_data["state"] = "main"
            await update.message.reply_text("به منوی اصلی برگشتی", reply_markup=main_keyboard())
            return

        send_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        image_path = None
        video_path = None

        if update.message.photo:
            image_path = update.message.photo[-1].file_id
            caption = update.message.caption or text
        elif update.message.video:
            video_path = update.message.video.file_id
            caption = update.message.caption or text
        else:
            caption = text

        try:
            cur.execute("""
                INSERT INTO reports (user_id, username, caption, send_date, image_path, video_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user.id, user.username, caption, send_date, image_path, video_path))
            conn.commit()

            await send_to_admin(update, context, user, "🚨 BUG REPORT")
            await update.message.reply_text("✅ گزارش ثبت شد")
            context.user_data["state"] = "main"

        except Exception as e:
            logging.error(e)
            await update.message.reply_text("❌ خطا در ثبت گزارش")
        return

    elif state == "suggest":
        if text == "🔙 بازگشت":
            context.user_data["state"] = "main"
            await update.message.reply_text("به منوی اصلی برگشتی", reply_markup=main_keyboard())
            return

        send_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        image_path = None
        video_path = None

        if update.message.photo:
            image_path = update.message.photo[-1].file_id
            caption = update.message.caption or text
        elif update.message.video:
            video_path = update.message.video.file_id
            caption = update.message.caption or text
        else:
            caption = text

        try:
            cur.execute("""
                INSERT INTO suggestion (user_id, username, caption, send_date, image_path, video_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user.id, user.username, caption, send_date, image_path, video_path))
            conn.commit()

            await send_to_admin(update, context, user, "💡 SUGGESTION")
            await update.message.reply_text("✅ ارسال شد")
            context.user_data["state"] = "main"

        except Exception as e:
            logging.error(e)
            await update.message.reply_text("خطا در ثبت✖️")
        return

    elif state == "play":
        if text == "🔙 بازگشت":
            context.user_data["state"] = "main"
            await update.message.reply_text("به منوی اصلی برگشتی", reply_markup=main_keyboard())
            return

        send_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        image_path = None
        video_path = None

        if update.message.photo:
            image_path = update.message.photo[-1].file_id
            caption = update.message.caption or text
        elif update.message.video:
            video_path = update.message.video.file_id
            caption = update.message.caption or text
        else:
            caption = text

        try:
            cur.execute("""
                INSERT INTO playtime (user_id, username, caption, send_date, image_path, video_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user.id, user.username, caption, send_date, image_path, video_path))
            conn.commit()

            await send_to_admin(update, context, user, "💡 EXPERIENCE")
            await update.message.reply_text("✅ ارسال شد")
            context.user_data["state"] = "main"

        except Exception as e:
            logging.error(e)
            await update.message.reply_text("خطا در ثبت✖️")
        return


# ================= SEND TO ADMIN =================
async def send_to_admin(update, context, user, title):
    msg = update.message
    caption = msg.caption or ""
    text = msg.text or ""

    try:
        if msg.text and not msg.photo and not msg.video:
            for ad_id in ADMINS_ID:
                await context.bot.send_message(
                    chat_id=ad_id,
                    text=f"{title}\n\n👤 {user.full_name}\n🆔 {user.id}\n\n📝 {text}"
                )
        elif msg.photo:
            for ad_id in ADMINS_ID:
                await context.bot.send_photo(
                    chat_id=ad_id,
                    photo=msg.photo[-1].file_id,
                    caption=f"{title}\n\n👤 {user.full_name}\n🆔 {user.id}\n\n📝 {caption}"
                )
        elif msg.video:
            for ad_id in ADMINS_ID:
                await context.bot.send_video(
                    chat_id=ad_id,
                    video=msg.video.file_id,
                    caption=f"{title}\n\n👤 {user.full_name}\n🆔 {user.id}\n\n📝 {caption}"
                )
        else:
            await update.message.reply_text("⚠️ فرمت پشتیبانی نمی‌شود")
            return

        await update.message.reply_text("📤 ارسال به ادمین انجام شد")

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ خطا در ارسال به ادمین")


# ================= ADMIN BUTTON =================
async def admin_button(update, context):
    if not update.message:
        return

    text = update.message.text or ""
    user = update.effective_user
    state = context.user_data.get("state", "main")

    if text == "🔙 بازگشت":
        context.user_data["state"] = "main"
        await update.message.reply_text(
            "شما در منوی اصلی هستید ✅",
            reply_markup=admin_keyboard()
        )
        return

    if text == "حذف اطلاعات":
        if state == "reports":
            cur.execute("DELETE FROM reports")
            conn.commit()
            context.user_data["state"] = "main"
            await update.message.reply_text(
                "reports data deleted🐉",
                reply_markup=admin_keyboard()
            )
        elif state == "suggest":
            cur.execute("DELETE FROM suggestion")
            conn.commit()
            context.user_data["state"] = "main"
            await update.message.reply_text(
                "suggest data deleted🐉",
                reply_markup=admin_keyboard()
            )
        elif state == "play":
            cur.execute("DELETE FROM playtime")
            conn.commit()
            context.user_data["state"] = "main"
            await update.message.reply_text(
                "playTime data deleted🐉",
                reply_markup=admin_keyboard()
            )
        return

    if state == "main":
        if text == "کاربران👤":
            context.user_data["state"] = "users"
            user_rows = cur.execute("SELECT user_id, player_name, username, join_date FROM USERSPROFILE").fetchall()

            if not user_rows:
                await update.message.reply_text("هیچ کاربری ثبت نشده ❌", reply_markup=admin_back_keyboard())
                return

            msg = "📋 لیست کاربران:\n\n"
            for r in user_rows:
                msg += f"👤 {r[1]} | 🆔 {r[0]}\n📝 @{r[2] if r[2] else 'ندارد'}\n📅 {r[3]}\n\n"

            await update.message.reply_text(msg, reply_markup=admin_back_keyboard())
            return

        elif text == "گزارش ها":
            context.user_data["state"] = "reports"
            rows = cur.execute("SELECT user_id, username, caption, send_date FROM reports").fetchall()

            if not rows:
                await update.message.reply_text("هیچ گزارشی ثبت نشده ❌", reply_markup=admin_back_keyboard())
                return

            msg = "📋 لیست گزارش‌ها:\n\n"
            for r in rows:
                msg += f"👤 {r[1]} | 🆔 {r[0]}\n📝 {r[2]}\n📅 {r[3]}\n\n"

            await update.message.reply_text(msg, reply_markup=admin_back_keyboard())
            return

        elif text == "پیشنهادات":
            context.user_data["state"] = "suggest"
            sugg_rows = cur.execute("SELECT user_id, username, caption, send_date FROM suggestion").fetchall()

            if not sugg_rows:
                await update.message.reply_text("هیچ پیشنهادی ثبت نشده ❌", reply_markup=admin_back_keyboard())
                return

            msg = "📋 لیست پیشنهادات:\n\n"
            for r in sugg_rows:
                msg += f"👤 {r[1]} | 🆔 {r[0]}\n📝 {r[2]}\n📅 {r[3]}\n\n"

            await update.message.reply_text(msg, reply_markup=admin_back_keyboard())
            return

        elif text == "تجربیات":
            context.user_data["state"] = "play"
            play_rows = cur.execute("SELECT user_id, username, caption, send_date FROM playtime").fetchall()

            if not play_rows:
                await update.message.reply_text("هیچ تجربه‌ای ثبت نشده ❌", reply_markup=admin_back_keyboard())
                return

            msg = "📋 لیست تجربیات:\n\n"
            for r in play_rows:
                msg += f"👤 {r[1]} | 🆔 {r[0]}\n📝 {r[2]}\n📅 {r[3]}\n\n"

            await update.message.reply_text(msg, reply_markup=admin_back_keyboard())
            return

        elif text == "افزودن ادمین":
            context.user_data["state"] = "Add_admin"
            await update.message.reply_text(
                "آیدی عددی ادمین جدید را ارسال کن:",
                reply_markup=admin_back_keyboard()
            )
            return

        elif text == "حذف ادمین":
            context.user_data["state"] = "remove_admin"
            await update.message.reply_text(
                "آیدی عددی ادمینی که می‌خواهی حذف کنی را ارسال کن:",
                reply_markup=admin_back_keyboard()
            )
            return

    elif state == "Add_admin":
        admin_join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            admin_id = int(text)

            cur.execute(
                "SELECT 1 FROM ADMINPROFILE WHERE admin_id = ?",
                (admin_id,)
            )
            exists = cur.fetchone()

            if exists:
                await update.message.reply_text(
                    "❌ این کاربر قبلاً ادمین است.",
                    reply_markup=admin_keyboard()
                )
            else:
                cur.execute("""
                    INSERT INTO ADMINPROFILE (admin_id, admin_name, admin_username, admin_join_date) 
                    VALUES (?, ?, ?, ?)
                """, (admin_id, user.full_name, user.username, admin_join_date))
                conn.commit()

                if admin_id not in ADMINS_ID:
                    ADMINS_ID.append(admin_id)

                await update.message.reply_text(
                    "✅ ادمین با موفقیت اضافه شد.",
                    reply_markup=admin_keyboard()
                )

        except ValueError:
            await update.message.reply_text(
                "❌ لطفاً فقط آیدی عددی ارسال کن."
            )

        context.user_data["state"] = "main"
        return

    elif state == "remove_admin":
        try:
            admin_id = int(text)

            if admin_id in ADMINS_ID:
                ADMINS_ID.remove(admin_id)

            cur.execute(
                "DELETE FROM ADMINPROFILE WHERE admin_id = ?",
                (admin_id,)
            )
            conn.commit()

            if cur.rowcount == 0:
                await update.message.reply_text("❌ چنین ادمینی پیدا نشد.")
            else:
                await update.message.reply_text(
                    "✅ ادمین حذف شد.",
                    reply_markup=admin_keyboard()
                )

        except ValueError:
            await update.message.reply_text("❌ فقط آیدی عددی ارسال کن.")

        context.user_data["state"] = "main"
        return


# ================= COMMAND HANDLERS =================
async def lucky_spin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("مقدار پول برای استارت بازی رو انتخاب کن", reply_markup=spin_keyboard)


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎯 بازی چالش هوش به زودی میاد!")


async def bomb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💣 بازی میدان مین به زودی میاد!")


async def paper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✊ بازی سنگ کاغذ قیچی به زودی میاد!")


async def killmonster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚔️ بازی نبرد با هیولا به زودی میاد!")


# ================= APP =================
app = Application.builder().token(BotToken).build()

app.add_handler(CallbackQueryHandler(spin_handler))
app.add_handler(CommandHandler("start", start_bot))
app.add_handler(CommandHandler("luckySpin", lucky_spin))  # اصلاح: با حروف بزرگ S
app.add_handler(CommandHandler("quiz", quiz))
app.add_handler(CommandHandler("bomb", bomb))
app.add_handler(CommandHandler("paper", paper))
app.add_handler(CommandHandler("killmonster", killmonster))
app.add_handler(MessageHandler(filters.ALL, handler_button))

print("Bot is running...")
app.run_polling()
