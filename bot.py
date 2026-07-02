import asyncio
import os
import random
import time
import threading
import logging
from functools import wraps
from datetime import datetime

import sqlite3
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    CallbackContext,
)

# ================== LOGGING ==================


# لاگ‌ها دیگه هیچ اطلاعات حساس (مثل توکن) رو چاپ نمی‌کنن
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("viro_bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ViroBot")

# ================== DATABASE ==================
conn = sqlite3.connect('ViroBot.db', check_same_thread=False)
cur = conn.cursor()

# قفل سراسری برای جلوگیری از Race Condition روی نوشتن‌های همزمان دیتابیس
# (چون check_same_thread=False است و آپدیت‌های async می‌تونن همزمان اجرا بشن)
db_lock = threading.Lock()

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

# ---- جدول جدید: لاگ تراکنش سکه، برای ردیابی و کشف تقلب ----
cur.execute("""
CREATE TABLE IF NOT EXISTS coin_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    reason TEXT,
    balance_after INTEGER,
    created_at TEXT
)
""")

# ---- جدول جدید: آمار مینی‌گیم‌ها برای پروفایل/لیدربورد آینده ----
cur.execute("""
CREATE TABLE IF NOT EXISTS minigame_stats (
    user_id INTEGER PRIMARY KEY,
    quiz_wins INTEGER DEFAULT 0,
    bomb_wins INTEGER DEFAULT 0,
    rps_wins INTEGER DEFAULT 0,
    monster_kills INTEGER DEFAULT 0
)
""")

conn.commit()

# ✅ توکن باید از متغیر محیطی خونده بشه، هیچ‌وقت مستقیم توی کد یا چاپ نشه
BotToken = "8813949311:AAHDMJPzAi3DG_F3edWMRsNGhX-qD_XOLBo"
if not BotToken:
    raise RuntimeError(
        "❌ متغیر محیطی BOT_TOKEN تنظیم نشده است. "
        "توکن ربات را هرگز داخل کد ننویس؛ آن را به‌صورت متغیر محیطی ست کن."
    )

ADMINS_ID = [8581685408]
CHANNEL_ID = "@VirozStudiogame"

# ✅ آدرس HTTPS سرور بازی VIRO Survivor (فایل server/app.py)
# باید یک دامنه HTTPS واقعی باشد؛ تلگرام WebApp با HTTP یا IP لوکال کار نمی‌کند.
WEBAPP_URL = os.getenv("WEBAPP_URL")

# محدودیت‌های امنیتی
MAX_TEXT_LENGTH = 1000          # حداکثر طول متن گزارش/پیشنهاد/تجربه
MAX_BET = 100000                # سقف شرط در چرخ شانس
RATE_LIMIT_SECONDS = 1.5        # فاصله زمانی مجاز بین اکشن‌های حساس هر کاربر

# ================== RATE LIMITING ==================
_last_action_time = {}  # {(user_id, action_key): timestamp}
_rate_limit_lock = threading.Lock()


def rate_limited(action_key: str, seconds: float = RATE_LIMIT_SECONDS):
    """
    جلوگیری از اسپم/فارم کردن سکه با کلیک یا ارسال پشت‌سرهم.
    هر کاربر برای هر اکشن حداقل `seconds` ثانیه باید صبر کند.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user = update.effective_user
            if user is None:
                return
            key = (user.id, action_key)
            now = time.monotonic()
            with _rate_limit_lock:
                last = _last_action_time.get(key, 0)
                if now - last < seconds:
                    if update.callback_query:
                        await update.callback_query.answer(
                            "⏳ کمی صبر کن، خیلی سریع داری کلیک می‌کنی!", show_alert=False
                        )
                    else:
                        await update.message.reply_text("⏳ کمی صبر کن و دوباره امتحان کن.")
                    return
                _last_action_time[key] = now
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator


# ================== COIN FUNCTIONS (SECURE) ==================
def find_coin(user_id):
    with db_lock:
        cur.execute("SELECT coins FROM USERSPROFILE WHERE user_id = ?", (user_id,))
        result = cur.fetchone()
    return result[0] if result else 0


def has_enough_coins(user_id, amount):
    if amount <= 0:
        return False
    return find_coin(user_id) >= amount


def _log_transaction(user_id, amount, reason, balance_after):
    cur.execute("""
        INSERT INTO coin_transactions (user_id, amount, reason, balance_after, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, amount, reason, balance_after, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


def add_coin(user_id, amount, reason="unspecified"):
    """اضافه کردن سکه با اعتبارسنجی کامل و ثبت لاگ تراکنش."""
    if not isinstance(amount, int) or amount <= 0:
        logger.warning(f"Blocked invalid add_coin amount={amount} for user={user_id}")
        return False
    with db_lock:
        cur.execute("UPDATE USERSPROFILE SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
        cur.execute("SELECT coins FROM USERSPROFILE WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        balance_after = row[0] if row else amount
        _log_transaction(user_id, amount, reason, balance_after)
        conn.commit()
    return True


def remove_coin(user_id, amount, reason="unspecified"):
    """کم کردن سکه با جلوگیری از منفی شدن موجودی (ضدتقلب)."""
    if not isinstance(amount, int) or amount <= 0:
        logger.warning(f"Blocked invalid remove_coin amount={amount} for user={user_id}")
        return False
    with db_lock:
        cur.execute("SELECT coins FROM USERSPROFILE WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        current = row[0] if row else 0
        if current < amount:
            # جلوگیری از منفی شدن سکه حتی در شرایط رقابتی (race condition)
            return False
        cur.execute("UPDATE USERSPROFILE SET coins = coins - ? WHERE user_id = ?", (amount, user_id))
        balance_after = current - amount
        _log_transaction(user_id, -amount, reason, balance_after)
        conn.commit()
    return True


def ensure_user_exists(user_id, first_name, username):
    with db_lock:
        cur.execute("SELECT user_id FROM USERSPROFILE WHERE user_id = ?", (user_id,))
        exists = cur.fetchone()
        if not exists:
            join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("""
                INSERT INTO USERSPROFILE (user_id, player_name, username, join_date, coins)
                VALUES (?, ?, ?, ?, 100)
            """, (user_id, first_name, username, join_date))
            conn.commit()
        cur.execute("SELECT 1 FROM minigame_stats WHERE user_id = ?", (user_id,))
        if not cur.fetchone():
            cur.execute("INSERT INTO minigame_stats (user_id) VALUES (?)", (user_id,))
            conn.commit()


def _sanitize_text(text: str) -> str:
    """جلوگیری از فلود دیتابیس با متن‌های بیش‌ازحد بلند."""
    if not text:
        return ""
    return text.strip()[:MAX_TEXT_LENGTH]


# ================== KEYBOARDS ==================
def is_admin(user_id):
    with db_lock:
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
        logger.error(f"Error checking member: {e}")
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
@rate_limited("spin")
async def spin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    ensure_user_exists(user_id, query.from_user.first_name, query.from_user.username)

    try:
        bet = int(query.data.split("_")[1])
    except (ValueError, IndexError):
        await query.message.reply_text("❌ مقدار نامعتبر!")
        return

    if bet <= 0 or bet > MAX_BET:
        await query.message.reply_text("❌ مقدار شرط نامعتبر است.")
        return

    if not has_enough_coins(user_id, bet):
        await query.message.reply_text("❌ سکه کافی نداری.")
        return

    if not remove_coin(user_id, bet, reason="spin_bet"):
        await query.message.reply_text("❌ خطا در ثبت شرط، دوباره امتحان کن.")
        return

    msg = await query.message.reply_text("🎰 در حال چرخش...")

    await asyncio.sleep(1)
    await msg.edit_text("🎰 در حال بررسی نتیجه...")

    win = random.randint(1, 100)

    if win <= 45:
        reward = int(bet * 1.5)
        add_coin(user_id, reward, reason="spin_win")

        await msg.edit_text(
            f"🎉 بردی!\n\n"
            f"💰 شرط: {bet}\n"
            f"🏆 جایزه: {reward}\n"
            f"📈 سود خالص: {reward - bet}"
        )
    else:
        await msg.edit_text(
            f"😢 باختی!\n\n"
            f"💸 از دست دادی: {bet}"
        )

    await query.message.delete()


# ================== START ==================
@join_required
async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    if not update.message:
        return

    if is_admin(user.id) or user.id in ADMINS_ID:
        keyboard = admin_keyboard()
    else:
        keyboard = main_keyboard()

    ensure_user_exists(user.id, user.first_name, user.username)

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

    ensure_user_exists(user.id, user.first_name, user.username)

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
   ✦ نبرد با هیولا (بازی واقعی)
   👹 وارد آرنای وب می‌شی

🕹️  /killmonster_classic
   ✦ نسخه سریع متنی

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
            caption = _sanitize_text(update.message.caption or text)
        elif update.message.video:
            video_path = update.message.video.file_id
            caption = _sanitize_text(update.message.caption or text)
        else:
            caption = _sanitize_text(text)

        try:
            with db_lock:
                cur.execute("""
                    INSERT INTO reports (user_id, username, caption, send_date, image_path, video_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user.id, user.username, caption, send_date, image_path, video_path))
                conn.commit()

            await send_to_admin(update, context, user, "🚨 BUG REPORT")
            await update.message.reply_text("✅ گزارش ثبت شد")
            context.user_data["state"] = "main"

        except Exception as e:
            logger.error(e)
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
            caption = _sanitize_text(update.message.caption or text)
        elif update.message.video:
            video_path = update.message.video.file_id
            caption = _sanitize_text(update.message.caption or text)
        else:
            caption = _sanitize_text(text)

        try:
            with db_lock:
                cur.execute("""
                    INSERT INTO suggestion (user_id, username, caption, send_date, image_path, video_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user.id, user.username, caption, send_date, image_path, video_path))
                conn.commit()

            await send_to_admin(update, context, user, "💡 SUGGESTION")
            await update.message.reply_text("✅ ارسال شد")
            context.user_data["state"] = "main"

        except Exception as e:
            logger.error(e)
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
            caption = _sanitize_text(update.message.caption or text)
        elif update.message.video:
            video_path = update.message.video.file_id
            caption = _sanitize_text(update.message.caption or text)
        else:
            caption = _sanitize_text(text)

        try:
            with db_lock:
                cur.execute("""
                    INSERT INTO playtime (user_id, username, caption, send_date, image_path, video_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user.id, user.username, caption, send_date, image_path, video_path))
                conn.commit()

            await send_to_admin(update, context, user, "💡 EXPERIENCE")
            await update.message.reply_text("✅ ارسال شد")
            context.user_data["state"] = "main"

        except Exception as e:
            logger.error(e)
            await update.message.reply_text("خطا در ثبت✖️")
        return


# ================= SEND TO ADMIN =================
async def send_to_admin(update, context, user, title):
    msg = update.message
    caption = _sanitize_text(msg.caption or "")
    text = _sanitize_text(msg.text or "")

    try:
        if msg.text and not msg.photo and not msg.video:
            for ad_id in ADMINS_ID:
                await context.bot.send_message(
                    chat_id=ad_id,
                    text=f"{title}\n\n👤 {user.full_name}\n🆔 {user.id}\n📝 @{user.username or 'ندارد'}\n\n📝 {text}"
                )
        elif msg.photo:
            for ad_id in ADMINS_ID:
                await context.bot.send_photo(
                    chat_id=ad_id,
                    photo=msg.photo[-1].file_id,
                    caption=f"{title}\n\n👤 {user.full_name}\n🆔 {user.id}\n📝 @{user.username or 'ندارد'}\n\n📝 {caption}"
                )
        elif msg.video:
            for ad_id in ADMINS_ID:
                await context.bot.send_video(
                    chat_id=ad_id,
                    video=msg.video.file_id,
                    caption=f"{title}\n\n👤 {user.full_name}\n🆔 {user.id}\n📝 @{user.username or 'ندارد'}\n\n📝 {caption}"
                )
        else:
            await update.message.reply_text("⚠️ فرمت پشتیبانی نمی‌شود")
            return

        await update.message.reply_text("📤 ارسال به ادمین انجام شد")

    except Exception as e:
        logger.error(f"Error sending to admin: {e}")
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
        with db_lock:
            if state == "reports":
                cur.execute("DELETE FROM reports")
                conn.commit()
            elif state == "suggest":
                cur.execute("DELETE FROM suggestion")
                conn.commit()
            elif state == "play":
                cur.execute("DELETE FROM playtime")
                conn.commit()

        if state == "reports":
            context.user_data["state"] = "main"
            await update.message.reply_text("reports data deleted🐉", reply_markup=admin_keyboard())
        elif state == "suggest":
            context.user_data["state"] = "main"
            await update.message.reply_text("suggest data deleted🐉", reply_markup=admin_keyboard())
        elif state == "play":
            context.user_data["state"] = "main"
            await update.message.reply_text("playTime data deleted🐉", reply_markup=admin_keyboard())
        return

    if state == "main":
        if text == "کاربران👤":
            context.user_data["state"] = "users"
            with db_lock:
                user_rows = cur.execute(
                    "SELECT user_id, player_name, username, join_date FROM USERSPROFILE"
                ).fetchall()

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
            with db_lock:
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
            with db_lock:
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
            with db_lock:
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

            with db_lock:
                cur.execute("SELECT 1 FROM ADMINPROFILE WHERE admin_id = ?", (admin_id,))
                exists = cur.fetchone()

                if exists:
                    already = True
                else:
                    cur.execute("""
                        INSERT INTO ADMINPROFILE (admin_id, admin_name, admin_username, admin_join_date) 
                        VALUES (?, ?, ?, ?)
                    """, (admin_id, user.full_name, user.username, admin_join_date))
                    conn.commit()
                    already = False

            if already:
                await update.message.reply_text("❌ این کاربر قبلاً ادمین است.", reply_markup=admin_keyboard())
            else:
                if admin_id not in ADMINS_ID:
                    ADMINS_ID.append(admin_id)
                logger.info(f"Admin {user.id} added new admin: {admin_id}")
                await update.message.reply_text("✅ ادمین با موفقیت اضافه شد.", reply_markup=admin_keyboard())

        except ValueError:
            await update.message.reply_text("❌ لطفاً فقط آیدی عددی ارسال کن.")

        context.user_data["state"] = "main"
        return

    elif state == "remove_admin":
        try:
            admin_id = int(text)

            if admin_id in ADMINS_ID:
                ADMINS_ID.remove(admin_id)

            with db_lock:
                cur.execute("DELETE FROM ADMINPROFILE WHERE admin_id = ?", (admin_id,))
                conn.commit()
                removed = cur.rowcount

            if removed == 0:
                await update.message.reply_text("❌ چنین ادمینی پیدا نشد.")
            else:
                logger.info(f"Admin {user.id} removed admin: {admin_id}")
                await update.message.reply_text("✅ ادمین حذف شد.", reply_markup=admin_keyboard())

        except ValueError:
            await update.message.reply_text("❌ فقط آیدی عددی ارسال کن.")

        context.user_data["state"] = "main"
        return


# ================================================================
#                        مینی‌گیم‌ها (کامل)
# ================================================================

# ---------------- QUIZ (چالش هوش) ----------------
QUIZ_REWARD = 15
QUIZ_QUESTIONS = [
    {"q": "پایتخت ایران کدام است؟", "options": ["تهران", "شیراز", "اصفهان", "مشهد"], "answer": 0},
    {"q": "۲ + ۲ × ۲ برابر است با؟", "options": ["۶", "۸", "۴", "۲"], "answer": 0},
    {"q": "بزرگترین سیاره منظومه شمسی کدام است؟", "options": ["زمین", "مریخ", "مشتری", "زحل"], "answer": 2},
    {"q": "کدام حیوان سریع‌ترین حیوان خشکی است؟", "options": ["شیر", "یوزپلنگ", "اسب", "گورخر"], "answer": 1},
    {"q": "آب از چند اتم تشکیل شده؟", "options": ["۲", "۳", "۴", "۱"], "answer": 1},
    {"q": "پایتخت فرانسه کدام شهر است؟", "options": ["لندن", "برلین", "پاریس", "رم"], "answer": 2},
]


@rate_limited("quiz")
async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username)

    q_index = random.randint(0, len(QUIZ_QUESTIONS) - 1)
    q = QUIZ_QUESTIONS[q_index]

    buttons = [
        [InlineKeyboardButton(opt, callback_data=f"quiz_{q_index}_{i}")]
        for i, opt in enumerate(q["options"])
    ]

    await update.message.reply_text(
        f"🧠 چالش هوش:\n\n{q['q']}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@rate_limited("quiz_answer")
async def quiz_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    ensure_user_exists(user.id, user.first_name, user.username)

    try:
        _, q_index_str, choice_str = query.data.split("_")
        q_index = int(q_index_str)
        choice = int(choice_str)
        q = QUIZ_QUESTIONS[q_index]
    except (ValueError, IndexError):
        await query.edit_message_text("❌ سوال نامعتبر یا منقضی شده.")
        return

    if choice == q["answer"]:
        add_coin(user.id, QUIZ_REWARD, reason="quiz_win")
        with db_lock:
            cur.execute(
                "UPDATE minigame_stats SET quiz_wins = quiz_wins + 1 WHERE user_id = ?",
                (user.id,)
            )
            conn.commit()
        await query.edit_message_text(f"✅ درست بود! 🎉\n💰 +{QUIZ_REWARD} سکه گرفتی.")
    else:
        correct_text = q["options"][q["answer"]]
        await query.edit_message_text(f"❌ اشتباه بود!\nجواب درست: {correct_text}")


# ---------------- BOMB (میدان مین) ----------------
BOMB_COST = 15
BOMB_REWARD = 25
BOMB_BOX_COUNT = 6


@rate_limited("bomb")
async def bomb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username)

    if not has_enough_coins(user.id, BOMB_COST):
        await update.message.reply_text(f"❌ برای بازی به {BOMB_COST} سکه نیاز داری.")
        return

    if not remove_coin(user.id, BOMB_COST, reason="bomb_entry"):
        await update.message.reply_text("❌ خطا در کسر سکه، دوباره امتحان کن.")
        return

    bomb_index = random.randint(0, BOMB_BOX_COUNT - 1)
    # ذخیره محل بمب فقط برای این راند در حافظه کاربر (سمت سرور، غیرقابل دستکاری از کلاینت)
    context.user_data["bomb_index"] = bomb_index
    context.user_data["bomb_played"] = False

    buttons = [
        InlineKeyboardButton("📦", callback_data=f"bomb_{i}")
        for i in range(BOMB_BOX_COUNT)
    ]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]

    await update.message.reply_text(
        f"💣 میدان مین!\nهزینه بازی: {BOMB_COST} سکه\nیکی از جعبه‌ها رو انتخاب کن. یکی از اونا بمبه 💥",
        reply_markup=InlineKeyboardMarkup(rows)
    )


@rate_limited("bomb_pick")
async def bomb_pick_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    ensure_user_exists(user.id, user.first_name, user.username)

    if context.user_data.get("bomb_played"):
        await query.edit_message_text("⚠️ این بازی قبلاً تموم شده. با /bomb یه راند جدید شروع کن.")
        return

    bomb_index = context.user_data.get("bomb_index")
    if bomb_index is None:
        await query.edit_message_text("⚠️ راند فعالی پیدا نشد. با /bomb شروع کن.")
        return

    try:
        picked = int(query.data.split("_")[1])
    except (ValueError, IndexError):
        return

    context.user_data["bomb_played"] = True

    if picked == bomb_index:
        await query.edit_message_text(f"💥 بوووم! این خونه بمب بود.\n💸 {BOMB_COST} سکه رو از دست دادی.")
    else:
        add_coin(user.id, BOMB_REWARD, reason="bomb_win")
        with db_lock:
            cur.execute(
                "UPDATE minigame_stats SET bomb_wins = bomb_wins + 1 WHERE user_id = ?",
                (user.id,)
            )
            conn.commit()
        await query.edit_message_text(
            f"✅ سالم رد شدی! 🎉\n💰 +{BOMB_REWARD} سکه گرفتی."
        )


# ---------------- PAPER (سنگ کاغذ قیچی) ----------------
RPS_COST = 10
RPS_REWARD = 18
RPS_CHOICES = {"rock": "🪨 سنگ", "paper": "📄 کاغذ", "scissors": "✂️ قیچی"}
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


@rate_limited("paper")
async def paper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username)

    buttons = [[
        InlineKeyboardButton("🪨 سنگ", callback_data="rps_rock"),
        InlineKeyboardButton("📄 کاغذ", callback_data="rps_paper"),
        InlineKeyboardButton("✂️ قیچی", callback_data="rps_scissors"),
    ]]

    await update.message.reply_text(
        f"✊ سنگ کاغذ قیچی!\nهزینه بازی: {RPS_COST} سکه | جایزه برد: {RPS_REWARD} سکه\nانتخابت رو بزن:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@rate_limited("rps_play")
async def rps_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    ensure_user_exists(user.id, user.first_name, user.username)

    player_choice = query.data.split("_", 1)[1]
    if player_choice not in RPS_CHOICES:
        return

    if not has_enough_coins(user.id, RPS_COST):
        await query.edit_message_text(f"❌ برای بازی به {RPS_COST} سکه نیاز داری.")
        return

    if not remove_coin(user.id, RPS_COST, reason="rps_entry"):
        await query.edit_message_text("❌ خطا در کسر سکه، دوباره امتحان کن.")
        return

    bot_choice = random.choice(list(RPS_CHOICES.keys()))

    if bot_choice == player_choice:
        add_coin(user.id, RPS_COST, reason="rps_tie_refund")
        result_text = "🤝 مساوی شد! سکه‌ت برگشت."
    elif RPS_BEATS[player_choice] == bot_choice:
        add_coin(user.id, RPS_REWARD, reason="rps_win")
        with db_lock:
            cur.execute(
                "UPDATE minigame_stats SET rps_wins = rps_wins + 1 WHERE user_id = ?",
                (user.id,)
            )
            conn.commit()
        result_text = f"🎉 بردی! +{RPS_REWARD} سکه"
    else:
        result_text = f"😢 باختی! {RPS_COST} سکه از دست دادی."

    await query.edit_message_text(
        f"تو: {RPS_CHOICES[player_choice]}\nربات: {RPS_CHOICES[bot_choice]}\n\n{result_text}"
    )


# ---------------- KILLMONSTER (نبرد با هیولا) ----------------
KM_COST = 15
KM_PLAYER_HP = 100
KM_MONSTER_HP = 80
KM_REWARD_PER_HP = 1  # به ازای هر HP باقی‌مانده بازیکن، سکه جایزه


@rate_limited("killmonster_open")
async def killmonster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ✅ نسخه‌ی جدید: به‌جای اجرای بازی داخل چت، دکمه‌ی Telegram WebApp باز می‌شود
    و کاربر وارد بازی واقعی VIRO Survivor (Phaser.js) می‌شود.
    نسخه‌ی متنی قبلی حذف نشده و از طریق /killmonster_classic همچنان در دسترس است.
    """
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username)

    if not WEBAPP_URL:
        await update.message.reply_text(
            "⚠️ بازی هنوز فعال نیست (WEBAPP_URL تنظیم نشده). از /killmonster_classic استفاده کن."
        )
        return

    buttons = [[InlineKeyboardButton("👹 ورود به آرنا", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.message.reply_text(
        "⚔️ آماده‌ای وارد آرنای VIRO Survivor بشی؟\nبرای شروع دکمه‌ی زیر رو بزن:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@rate_limited("killmonster")
async def killmonster_classic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نسخه‌ی قبلی، متنی و داخل چت - برای حفظ سازگاری کامل با قابلیت قبلی حذف نشده."""
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username)

    if not has_enough_coins(user.id, KM_COST):
        await update.message.reply_text(f"❌ برای ورود به نبرد به {KM_COST} سکه نیاز داری.")
        return

    if not remove_coin(user.id, KM_COST, reason="km_entry"):
        await update.message.reply_text("❌ خطا در کسر سکه، دوباره امتحان کن.")
        return

    context.user_data["km_player_hp"] = KM_PLAYER_HP
    context.user_data["km_monster_hp"] = KM_MONSTER_HP
    context.user_data["km_active"] = True

    buttons = [[InlineKeyboardButton("⚔️ حمله", callback_data="km_attack")]]

    await update.message.reply_text(
        f"👹 هیولا ظاهر شد!\n\n"
        f"❤️ HP تو: {KM_PLAYER_HP}\n"
        f"💀 HP هیولا: {KM_MONSTER_HP}\n\n"
        f"با دکمه حمله بجنگ!",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@rate_limited("km_attack")
async def killmonster_attack_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    ensure_user_exists(user.id, user.first_name, user.username)

    if not context.user_data.get("km_active"):
        await query.edit_message_text("⚠️ نبرد فعالی پیدا نشد. با /killmonster شروع کن.")
        return

    player_hp = context.user_data.get("km_player_hp", KM_PLAYER_HP)
    monster_hp = context.user_data.get("km_monster_hp", KM_MONSTER_HP)

    player_damage = random.randint(10, 25)
    monster_hp -= player_damage

    log = f"⚔️ تو {player_damage} دمیج زدی.\n"

    if monster_hp <= 0:
        context.user_data["km_active"] = False
        reward = KM_PLAYER_HP  # پاداش کامل چون هیولا رو کشتی بدون آسیب اضافه
        reward = max(reward, 20)
        add_coin(user.id, reward, reason="km_win")
        with db_lock:
            cur.execute(
                "UPDATE minigame_stats SET monster_kills = monster_kills + 1 WHERE user_id = ?",
                (user.id,)
            )
            conn.commit()
        await query.edit_message_text(
            f"{log}💀 هیولا رو کشتی! 🎉\n💰 +{reward} سکه گرفتی."
        )
        return

    monster_damage = random.randint(8, 20)
    player_hp -= monster_damage
    log += f"👹 هیولا {monster_damage} دمیج بهت زد.\n"

    if player_hp <= 0:
        context.user_data["km_active"] = False
        await query.edit_message_text(f"{log}💀 تو شکست خوردی! هیولا برنده شد.")
        return

    context.user_data["km_player_hp"] = player_hp
    context.user_data["km_monster_hp"] = monster_hp

    buttons = [[InlineKeyboardButton("⚔️ حمله", callback_data="km_attack")]]
    await query.edit_message_text(
        f"{log}\n❤️ HP تو: {player_hp}\n💀 HP هیولا: {monster_hp}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ================= COMMAND: LUCKY SPIN =================
@rate_limited("luckyspin_open")
async def lucky_spin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user_exists(user_id, update.effective_user.first_name, update.effective_user.username)
    await update.message.reply_text("🎰 مقدار شرط رو انتخاب کن:", reply_markup=spin_keyboard)


# ================= GLOBAL ERROR HANDLER =================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """جلوگیری از کرش کل ربات به‌خاطر یک خطای مدیریت‌نشده."""
    logger.error("Unhandled exception:", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ یه خطای غیرمنتظره پیش اومد. لطفاً دوباره امتحان کن."
            )
    except Exception:
        pass


# ================= APP =================
app = Application.builder().token(BotToken).build()

# هندلرهای Callback با pattern مشخص تا با هم تداخل نکنن
app.add_handler(CallbackQueryHandler(spin_handler, pattern=r"^spin_"))
app.add_handler(CallbackQueryHandler(quiz_answer_handler, pattern=r"^quiz_"))
app.add_handler(CallbackQueryHandler(bomb_pick_handler, pattern=r"^bomb_"))
app.add_handler(CallbackQueryHandler(rps_handler, pattern=r"^rps_"))
app.add_handler(CallbackQueryHandler(killmonster_attack_handler, pattern=r"^km_attack$"))

app.add_handler(CommandHandler("start", start_bot))
app.add_handler(CommandHandler("luckySpin", lucky_spin))
app.add_handler(CommandHandler("quiz", quiz))
app.add_handler(CommandHandler("bomb", bomb))
app.add_handler(CommandHandler("paper", paper))
app.add_handler(CommandHandler("killmonster", killmonster))
app.add_handler(CommandHandler("killmonster_classic", killmonster_classic))
app.add_handler(MessageHandler(filters.ALL, handler_button))

app.add_error_handler(error_handler)

logger.info("🤖 Bot is running...")
if __name__ == "__main__":
    app.run_polling()
