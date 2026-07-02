"""
تنظیمات مرکزی بازی VIRO Survivor.
این فایل تنها منبع حقیقت (Single Source of Truth) برای مقادیر HP، پاداش و فرمول لول است.
فرانت‌اند (Phaser) هم همین مقادیر را برای نمایش دارد، اما تصمیم نهایی همیشه با سرور است.
"""

# ---------------- دشمن‌ها ----------------
# xp و coins = پاداش پایه به‌ازای کشتن هر یک عدد از این نوع دشمن
ENEMY_TYPES = {
    "slime":    {"hp": 20,  "speed": 60,  "damage": 5,  "xp": 2,   "coins": 1},
    "zombie":   {"hp": 40,  "speed": 50,  "damage": 8,  "xp": 4,   "coins": 2},
    "skeleton": {"hp": 35,  "speed": 80,  "damage": 10, "xp": 6,   "coins": 3},
    "orc":      {"hp": 70,  "speed": 45,  "damage": 14, "xp": 9,   "coins": 5},
    "demon":    {"hp": 100, "speed": 70,  "damage": 18, "xp": 14,  "coins": 8},
    "dragon":   {"hp": 160, "speed": 55,  "damage": 25, "xp": 25,  "coins": 15},
    "boss":     {"hp": 900, "speed": 40,  "damage": 35, "xp": 120, "coins": 90, "gems": 5},
}

# حداکثر تعداد کشته‌ی قابل قبول از هر نوع، به ازای هر ثانیه بازی
# (برای جلوگیری از ارسال اعداد غیرممکن توسط کلاینت دستکاری‌شده)
MAX_KILLS_PER_SECOND = {
    "slime": 1.2,
    "zombie": 0.9,
    "skeleton": 0.8,
    "orc": 0.6,
    "demon": 0.4,
    "dragon": 0.25,
    "boss": 0.05,
}

# حداکثر مدت مجاز یک ران (ثانیه) - جلوگیری از ارسال duration دروغین بزرگ
MAX_RUN_DURATION_SECONDS = 3600  # ۱ ساعت

# حداقل فاصله بین دو ران متوالی برای هر کاربر (ثانیه) - ضدتقلب/ریت‌لیمیت
MIN_SECONDS_BETWEEN_RUNS = 15

# هر چند Wave یک Boss ظاهر شود
BOSS_WAVE_INTERVAL = 5


def xp_needed_for_level(level: int) -> int:
    """XP لازم برای رسیدن از `level` به `level+1`."""
    return int(50 * (level ** 1.4)) + 30


def level_from_total_xp(total_xp: int) -> tuple[int, int, int]:
    """
    ورودی: کل XP انباشته‌شده‌ی بازیکن
    خروجی: (level, xp_in_current_level, xp_needed_for_next_level)
    """
    level = 1
    remaining = total_xp
    while True:
        needed = xp_needed_for_level(level)
        if remaining < needed:
            return level, remaining, needed
        remaining -= needed
        level += 1
        if level > 500:  # سقف ایمنی
            return level, 0, xp_needed_for_level(level)


def compute_run_rewards(kills_by_type: dict, duration_seconds: int) -> dict:
    """
    محاسبه‌ی سرور-محور پاداش یک ران، با اعمال سقف بر اساس مدت زمان.
    ورودی کلاینت هرگز مستقیماً پذیرفته نمی‌شود؛ همیشه با این سقف‌ها هرس (clamp) می‌شود.
    """
    duration_seconds = max(0, min(int(duration_seconds), MAX_RUN_DURATION_SECONDS))

    total_xp = 0
    total_coins = 0
    total_gems = 0
    clamped_kills = {}

    for enemy_type, cfg in ENEMY_TYPES.items():
        raw_count = int(kills_by_type.get(enemy_type, 0) or 0)
        raw_count = max(0, raw_count)
        max_allowed = int(MAX_KILLS_PER_SECOND[enemy_type] * duration_seconds) + 1
        count = min(raw_count, max_allowed)
        clamped_kills[enemy_type] = count

        total_xp += count * cfg["xp"]
        total_coins += count * cfg["coins"]
        total_gems += count * cfg.get("gems", 0)

    return {
        "xp_earned": total_xp,
        "coins_earned": total_coins,
        "gems_earned": total_gems,
        "clamped_kills": clamped_kills,
        "duration_seconds": duration_seconds,
    }