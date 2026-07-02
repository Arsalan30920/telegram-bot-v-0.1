"""
سرور بازی VIRO Survivor (Kill Monster).
این سرور جدا از ربات تلگرام اجرا می‌شود ولی از همان دیتابیس استفاده می‌کند.

اجرا:
    export BOT_TOKEN="همان توکن ربات"
    export VIRO_DB_PATH="/path/to/ViroBot.db"   (اختیاری)
    python app.py

سپس با یک HTTPS واقعی (مثلاً از طریق nginx + certbot یا ngrok برای تست) در دسترس قرارش بده،
و آدرس HTTPS نهایی را در متغیر محیطی WEBAPP_URL ربات تلگرام قرار بده.
"""
import os
import time
import logging
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_from_directory

import db
import game_config
from security import verify_init_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ViroGameServer")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ متغیر محیطی BOT_TOKEN تنظیم نشده - سرور بدون آن نمی‌تواند initData را اعتبارسنجی کند.")

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), "..", "webapp")

app = Flask(__name__, static_folder=WEBAPP_DIR, static_url_path="")

# ---- Rate limiting ساده در حافظه، به‌ازای هر endpoint حساس ----
_last_call = {}


def _rate_limited(key: str, min_seconds: float) -> bool:
    now = time.monotonic()
    last = _last_call.get(key, 0)
    if now - last < min_seconds:
        return True
    _last_call[key] = now
    return False


def _authenticate():
    """
    initData را از body (JSON) یا هدر X-Telegram-Init-Data می‌خواند و اعتبارسنجی می‌کند.
    خروجی: دیکشنری کاربر تلگرام یا None
    """
    init_data = request.headers.get("X-Telegram-Init-Data")
    if not init_data and request.is_json:
        init_data = (request.get_json(silent=True) or {}).get("initData")

    return verify_init_data(init_data, BOT_TOKEN)


# ==================== STATIC (بازی) ====================
@app.route("/")
def index():
    return send_from_directory(WEBAPP_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(WEBAPP_DIR, path)


# ==================== API ====================
@app.route("/api/auth", methods=["POST"])
def api_auth():
    user = _authenticate()
    if not user:
        return jsonify({"error": "invalid_init_data"}), 401

    user_id = user["id"]

    if _rate_limited(f"auth:{user_id}", 1.0):
        return jsonify({"error": "rate_limited"}), 429

    db.ensure_user(user_id, user.get("first_name", ""), user.get("username", ""))
    profile = db.get_profile(user_id)
    return jsonify({"ok": True, "profile": _serialize_profile(profile)})


@app.route("/api/run/finish", methods=["POST"])
def api_run_finish():
    user = _authenticate()
    if not user:
        return jsonify({"error": "invalid_init_data"}), 401

    user_id = user["id"]

    if _rate_limited(f"run_finish:{user_id}", game_config.MIN_SECONDS_BETWEEN_RUNS):
        return jsonify({"error": "too_many_runs", "message": "کمی صبر کن و دوباره بازی کن."}), 429

    body = request.get_json(silent=True) or {}
    wave_reached = max(0, int(body.get("wave_reached", 0) or 0))
    duration_seconds = max(0, int(body.get("duration_seconds", 0) or 0))
    kills_by_type = body.get("kills_by_type", {}) or {}
    if not isinstance(kills_by_type, dict):
        kills_by_type = {}

    # محاسبه‌ی کاملاً سرور-محور - هیچ مقدار سکه/XP از کلاینت مستقیم پذیرفته نمی‌شود
    result = game_config.compute_run_rewards(kills_by_type, duration_seconds)

    total_kills = sum(result["clamped_kills"].values())
    boss_kills = result["clamped_kills"].get("boss", 0)

    profile_before = db.get_profile(user_id)
    if not profile_before:
        db.ensure_user(user_id, user.get("first_name", ""), user.get("username", ""))
        profile_before = db.get_profile(user_id)

    prior_total_xp = profile_before["xp"]
    new_total_xp = prior_total_xp + result["xp_earned"]
    new_level, xp_in_level, xp_needed = game_config.level_from_total_xp(new_total_xp)

    # پرچم‌گذاری ران‌های مشکوک (بدون رد کردن، فقط برای بررسی بعدی ادمین)
    suspicious = (
        wave_reached > (duration_seconds // 3 + 5)  # سرعت پیشرفت غیرممکن در Wave
        or total_kills > duration_seconds * 3
    )
    if suspicious:
        logger.warning(f"Suspicious run from user {user_id}: wave={wave_reached}, "
                        f"kills={total_kills}, duration={duration_seconds}")

    db.apply_run_result(
        user_id=user_id,
        wave_reached=min(wave_reached, 9999),
        kills=total_kills,
        boss_kills=boss_kills,
        xp_earned=result["xp_earned"],
        coins_earned=result["coins_earned"],
        gems_earned=result["gems_earned"],
        duration_seconds=result["duration_seconds"],
        new_level=new_level,
        new_total_xp=new_total_xp,
        flagged_suspicious=suspicious,
    )

    profile_after = db.get_profile(user_id)
    return jsonify({
        "ok": True,
        "rewards": {
            "coins_earned": result["coins_earned"],
            "xp_earned": result["xp_earned"],
            "gems_earned": result["gems_earned"],
            "leveled_up": new_level > profile_before["level"],
        },
        "profile": _serialize_profile(profile_after),
    })


def _serialize_profile(profile: dict) -> dict:
    level, xp_in_level, xp_needed = game_config.level_from_total_xp(profile["xp"])
    return {
        "user_id": profile["user_id"],
        "name": profile["player_name"],
        "coins": profile["coins"],
        "gems": profile["gems"],
        "level": level,
        "xp_in_level": xp_in_level,
        "xp_needed": xp_needed,
        "hp_max": profile["hp_max"],
        "kills": profile["kills"],
        "boss_kills": profile["boss_kills"],
        "highest_wave": profile["highest_wave"],
        "play_time_seconds": profile["play_time_seconds"],
        "equipped_weapon": profile["equipped_weapon"],
        "equipped_armor": profile["equipped_armor"],
    }


@app.errorhandler(Exception)
def handle_error(e):
    logger.exception("Unhandled server error")
    return jsonify({"error": "server_error"}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    logger.info(f"🎮 VIRO Game Server running on port {port}")
    app.run(host="0.0.0.0", port=port)