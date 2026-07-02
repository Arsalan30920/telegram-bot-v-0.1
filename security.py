"""
اعتبارسنجی initData ارسالی از Telegram WebApp.
طبق مستندات رسمی: https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_INIT_DATA_AGE_SECONDS = 24 * 60 * 60  # ۲۴ ساعت - جلوگیری از Replay با initData قدیمی/لو رفته


def verify_init_data(init_data: str, bot_token: str):
    """
    اگر initData معتبر باشد، دیکشنری کاربر (dict) را برمی‌گرداند.
    در غیر این صورت None برمی‌گرداند.
    هرگز به initData بدون بررسی این تابع اعتماد نکن.
    """
    if not init_data or not bot_token:
        return None

    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    auth_date = parsed.get("auth_date")
    if not auth_date or not auth_date.isdigit():
        return None
    if time.time() - int(auth_date) > MAX_INIT_DATA_AGE_SECONDS:
        return None  # initData منقضی شده - احتمال Replay Attack

    user_raw = parsed.get("user")
    if not user_raw:
        return None

    try:
        user = json.loads(user_raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if "id" not in user:
        return None

    return user