"""
لایه دیتابیس سرور بازی.
از همان فایل ViroBot.db که ربات تلگرام استفاده می‌کند استفاده می‌شود
(مسیر با متغیر محیطی VIRO_DB_PATH قابل تنظیم است، پیش‌فرض همان مسیر ربات).
"""
import os
import sqlite3
import threading
from datetime import datetime

DB_PATH = os.getenv("VIRO_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "ViroBot.db"))

_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_lock = threading.Lock()


def _init_schema():
    with _lock:
        cur = _conn.cursor()

        # این جدول از قبل توسط ربات ساخته می‌شود؛ اینجا هم برای اطمینان از وجودش می‌سازیم
        # (اگر از قبل وجود داشته باشد، هیچ اتفاقی نمی‌افتد - IF NOT EXISTS)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS USERSPROFILE (
            user_id INTEGER PRIMARY KEY,
            player_name TEXT,
            username TEXT,
            join_date TEXT,
            coins INTEGER DEFAULT 100
        )
        """)

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

        # ---- جدول جدید مخصوص بازی Kill Monster ----
        cur.execute("""
        CREATE TABLE IF NOT EXISTS game_players (
            user_id INTEGER PRIMARY KEY,
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            gems INTEGER DEFAULT 0,
            hp_max INTEGER DEFAULT 100,
            kills INTEGER DEFAULT 0,
            boss_kills INTEGER DEFAULT 0,
            highest_wave INTEGER DEFAULT 0,
            play_time_seconds INTEGER DEFAULT 0,
            equipped_weapon TEXT DEFAULT 'sword',
            equipped_armor TEXT DEFAULT 'none',
            last_run_at TEXT,
            created_at TEXT,
            updated_at TEXT,
            new_xp_in_level TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS game_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            wave_reached INTEGER,
            kills INTEGER,
            boss_kills INTEGER,
            coins_earned INTEGER,
            xp_earned INTEGER,
            gems_earned INTEGER,
            duration_seconds INTEGER,
            created_at TEXT,
            flagged_suspicious INTEGER DEFAULT 0
        )
        """)

        _conn.commit()


_init_schema()


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_user(user_id: int, first_name: str, username: str):
    with _lock:
        cur = _conn.cursor()
        cur.execute("SELECT 1 FROM USERSPROFILE WHERE user_id = ?", (user_id,))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO USERSPROFILE (user_id, player_name, username, join_date, coins)
                VALUES (?, ?, ?, ?, 100)
            """, (user_id, first_name, username, now_str()))

        cur.execute("SELECT 1 FROM game_players WHERE user_id = ?", (user_id,))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO game_players (user_id, created_at, updated_at)
                VALUES (?, ?, ?)
            """, (user_id, now_str(), now_str()))

        _conn.commit()


def get_profile(user_id: int):
    with _lock:
        cur = _conn.cursor()
        cur.execute("""
            SELECT u.user_id, u.player_name, u.username, u.coins,
                   g.level, g.xp, g.gems, g.hp_max, g.kills, g.boss_kills,
                   g.highest_wave, g.play_time_seconds, g.equipped_weapon,
                   g.equipped_armor, g.last_run_at
            FROM USERSPROFILE u
            JOIN game_players g ON g.user_id = u.user_id
            WHERE u.user_id = ?
        """, (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def add_coins(user_id: int, amount: int, reason: str):
    if amount <= 0:
        return
    with _lock:
        cur = _conn.cursor()
        cur.execute("UPDATE USERSPROFILE SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
        cur.execute("SELECT coins FROM USERSPROFILE WHERE user_id = ?", (user_id,))
        balance_after = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO coin_transactions (user_id, amount, reason, balance_after, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, amount, reason, balance_after, now_str()))
        _conn.commit()


def get_last_run_timestamp(user_id: int):
    with _lock:
        cur = _conn.cursor()
        cur.execute("SELECT last_run_at FROM game_players WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return row["last_run_at"] if row else None


def apply_run_result(user_id: int, wave_reached: int, kills: int, boss_kills: int,
                      xp_earned: int, coins_earned: int, gems_earned: int,
                      duration_seconds: int, new_level: int, new_total_xp: int,
                      flagged_suspicious: bool = False):
    with _lock:
        cur = _conn.cursor()

        cur.execute("UPDATE USERSPROFILE SET coins = coins + ? WHERE user_id = ?", (coins_earned, user_id))
        cur.execute("SELECT coins FROM USERSPROFILE WHERE user_id = ?", (user_id,))
        balance_after = cur.fetchone()[0]
        if coins_earned:
            cur.execute("""
                INSERT INTO coin_transactions (user_id, amount, reason, balance_after, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, coins_earned, "killmonster_run", balance_after, now_str()))

        cur.execute("""
            UPDATE game_players
            SET level = ?,
                xp = ?,
                gems = gems + ?,
                kills = kills + ?,
                boss_kills = boss_kills + ?,
                highest_wave = MAX(highest_wave, ?),
                play_time_seconds = play_time_seconds + ?,
                last_run_at = ?,
                updated_at = ?
            WHERE user_id = ?
        """, (new_level, new_xp_in_level, gems_earned, kills, boss_kills,
              wave_reached, duration_seconds, now_str(), now_str(), user_id))

        cur.execute("""
            INSERT INTO game_runs (user_id, wave_reached, kills, boss_kills, coins_earned,
                                    xp_earned, gems_earned, duration_seconds, created_at, flagged_suspicious)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, wave_reached, kills, boss_kills, coins_earned, xp_earned,
              gems_earned, duration_seconds, now_str(), int(flagged_suspicious)))

        _conn.commit()