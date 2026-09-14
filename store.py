"""
HiVo Tag Music - Persistent Storage Engine
==========================================
لایه ذخیره‌سازی داده‌ها روی فایل JSON با قابلیت‌های:
  - Thread-Safe با قفل داخلی
  - نوشتن اتمیک (Atomic Write)
  - پشتیبان‌گیری خودکار
  - مدیریت کاربران، آمار، سشن‌ها و کانفیگ
  - آماده برای مهاجرت به SQLite/Postgres

ساختار فایل state.json:
{
    "version": "2.0",
    "users": {
        "123456": {
            "name": "Ali",
            "lang": "fa",
            "files": 5,
            "joined": 1699999999,
            "last_seen": 1700000000,
            "formats": {"mp3": 3, "flac": 2}
        }
    },
    "stats": {
        "total_files": 42,
        "total_users": 12,
        "daily": {"2025-01-15": 5, "2025-01-16": 3}
    },
    "sessions": {
        "123456": {"file": "/tmp/...", "title": "..."}
    },
    "config": {
        "lock_enabled": false,
        "channel_username": "@HiVoChannel",
        "channel_link": "https://t.me/HiVoChannel"
    }
}
"""

import json
import logging
import shutil
import time
from pathlib import Path
from threading import Lock
from typing import Any, Optional

log = logging.getLogger(__name__)

# نسخه‌ی فعلی ساختار داده
SCHEMA_VERSION = "2.0"

# ساختار پیش‌فرض فایل ذخیره‌سازی
DEFAULT_STATE = {
    "version": SCHEMA_VERSION,
    "users": {},
    "stats": {
        "total_files": 0,
        "total_users": 0,
        "daily": {},
    },
    "sessions": {},
    "config": {
        "lock_enabled": False,
        "channel_username": "",
        "channel_link": "",
    },
}


# ============================================================
#                    Store (کلاس اصلی)
# ============================================================
class Store:
    """
    لایه‌ی ذخیره‌سازی داده‌ها روی فایل JSON.

    این کلاس thread-safe است و از نوشتن اتمیک و پشتیبان‌گیری خودکار
    پشتیبانی می‌کند.
    """

    def __init__(self, path: str = "state.json", auto_backup: bool = True):
        """
        Args:
            path: مسیر فایل JSON
            auto_backup: آیا قبل از هر ذخیره، نسخه‌ی پشتیبان گرفته شود؟
        """
        self.path = Path(path)
        self.backup_path = self.path.with_suffix(".json.bak")
        self.auto_backup = auto_backup
        self._lock = Lock()
        self.data = self._load()

    # --------------------------------------------------------
    #                بارگذاری و ذخیره‌سازی
    # --------------------------------------------------------
    def _load(self) -> dict:
        """بارگذاری داده‌ها از فایل یا ساخت فایل جدید"""
        if not self.path.exists():
            log.info(f"📁 ساخت فایل ذخیره‌سازی جدید: {self.path}")
            self._write_atomic(DEFAULT_STATE)
            return json.loads(json.dumps(DEFAULT_STATE))

        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
            # مهاجرت به نسخه‌ی جدید در صورت نیاز
            data = self._migrate(data)
            return data
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            log.error(f"❌ فایل ذخیره‌سازی خراب است: {e}")
            # تلاش برای بازیابی از نسخه‌ی پشتیبان
            if self.backup_path.exists():
                try:
                    log.info("🔄 بازیابی از نسخه‌ی پشتیبان...")
                    data = json.loads(self.backup_path.read_text(encoding="utf-8"))
                    self._write_atomic(data)
                    return data
                except Exception as e2:
                    log.error(f"❌ بازیابی هم شکست خورد: {e2}")
            # در نهایت، ساخت فایل جدید
            log.warning("⚠️ ساخت فایل ذخیره‌سازی جدید از صفر")
            self._write_atomic(DEFAULT_STATE)
            return json.loads(json.dumps(DEFAULT_STATE))

    def _migrate(self, data: dict) -> dict:
        """مهاجرت داده‌های قدیمی به ساختار جدید"""
        if data.get("version") == SCHEMA_VERSION:
            return data

        log.info(f"🔄 مهاجرت از نسخه {data.get('version', '?')} به {SCHEMA_VERSION}")

        # اطمینان از وجود کلیدهای اصلی
        for key, default in DEFAULT_STATE.items():
            if key not in data:
                data[key] = json.loads(json.dumps(default))

        # اطمینان از وجود کلیدهای آمار
        for key, default in DEFAULT_STATE["stats"].items():
            if key not in data["stats"]:
                data["stats"][key] = default

        # اطمینان از وجود کلیدهای کانفیگ
        for key, default in DEFAULT_STATE["config"].items():
            if key not in data["config"]:
                data["config"][key] = default

        # اضافه کردن فیلدهای جدید به کاربران
        for uid, user in data.get("users", {}).items():
            user.setdefault("lang", "fa")
            user.setdefault("formats", {})
            user.setdefault("last_seen", user.get("joined") or int(time.time()))

        data["version"] = SCHEMA_VERSION
        self._write_atomic(data)
        return data

    def _write_atomic(self, data: dict) -> None:
        """نوشتن اتمیک در فایل برای جلوگیری از خرابی"""
        try:
            # پشتیبان‌گیری
            if self.auto_backup and self.path.exists():
                try:
                    shutil.copy2(self.path, self.backup_path)
                except Exception as e:
                    log.warning(f"⚠️ پشتیبان‌گیری شکست خورد: {e}")

            # نوشتن در فایل موقت
            temp_path = self.path.with_suffix(".json.tmp")
            temp_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # جایگزینی اتمیک
            temp_path.replace(self.path)
        except Exception as e:
            log.error(f"❌ خطا در نوشتن فایل: {e}")

    def save(self) -> None:
        """ذخیره‌ی داده‌ها روی فایل (thread-safe)"""
        with self._lock:
            self._write_atomic(self.data)

    # --------------------------------------------------------
    #                    کاربران
    # --------------------------------------------------------
    def add_user(self, user_id: int, name: str = "") -> bool:
        """
        اضافه کردن کاربر جدید.

        Returns:
            True اگر کاربر جدید باشد، False اگر از قبل وجود داشته باشد.
        """
        uid = str(user_id)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {
                "name": name,
                "lang": "fa",
                "files": 0,
                "joined": int(time.time()),
                "last_seen": int(time.time()),
                "formats": {},
            }
            self.data["stats"]["total_users"] = len(self.data["users"])
            self.save()
            return True
        else:
            self.data["users"][uid]["last_seen"] = int(time.time())
            if name:
                self.data["users"][uid]["name"] = name
            self.save()
            return False

    def get_user(self, user_id: int) -> Optional[dict]:
        """گرفتن اطلاعات یه کاربر"""
        return self.data["users"].get(str(user_id))

    def get_all_users(self) -> dict:
        """گرفتن همه‌ی کاربران"""
        return dict(self.data["users"])

    def delete_user(self, user_id: int) -> bool:
        """حذف یه کاربر"""
        uid = str(user_id)
        if uid in self.data["users"]:
            del self.data["users"][uid]
            self.data["stats"]["total_users"] = len(self.data["users"])
            self.save()
            return True
        return False

    def set_user_lang(self, user_id: int, lang: str) -> None:
        """تنظیم زبان کاربر"""
        uid = str(user_id)
        self.data["users"].setdefault(uid, {})
        self.data["users"][uid]["lang"] = lang
        self.save()

    def get_user_lang(self, user_id: int, default: str = "fa") -> str:
        """گرفتن زبان کاربر"""
        return self.data["users"].get(str(user_id), {}).get("lang", default)

    def inc_files(self, user_id: int, file_format: str = "mp3") -> None:
        """
        افزایش تعداد فایل‌های پردازش‌شده‌ی کاربر.

        Args:
            user_id: آیدی کاربر
            file_format: فرمت فایل (mp3, flac, m4a, ...)
        """
        uid = str(user_id)
        self.data["users"].setdefault(uid, {
            "name": "", "lang": "fa", "files": 0,
            "joined": int(time.time()), "last_seen": int(time.time()),
            "formats": {},
        })
        user = self.data["users"][uid]
        user["files"] = user.get("files", 0) + 1
        user["last_seen"] = int(time.time())

        fmt = file_format.lower().lstrip(".")
        user.setdefault("formats", {})
        user["formats"][fmt] = user["formats"].get(fmt, 0) + 1

        # آمار کلی
        self.data["stats"]["total_files"] = self.data["stats"].get("total_files", 0) + 1
        self.data["stats"]["total_users"] = len(self.data["users"])

        # آمار روزانه
        today = time.strftime("%Y-%m-%d")
        self.data["stats"].setdefault("daily", {})
        self.data["stats"]["daily"][today] = self.data["stats"]["daily"].get(today, 0) + 1

        # فقط ۳۰ روز آخر رو نگه دار
        if len(self.data["stats"]["daily"]) > 30:
            sorted_days = sorted(self.data["stats"]["daily"].keys())
            for old_day in sorted_days[:-30]:
                del self.data["stats"]["daily"][old_day]

        self.save()

    # --------------------------------------------------------
    #                    آمار
    # --------------------------------------------------------
    def get_stats(self) -> dict:
        """گرفتن آمار کلی"""
        return {
            "users": len(self.data["users"]),
            "files": self.data["stats"].get("total_files", 0),
            "daily": self.data["stats"].get("daily", {}),
        }

    def get_user_stats(self, user_id: int) -> dict:
        """گرفتن آمار یه کاربر خاص"""
        u = self.get_user(user_id) or {}
        return {
            "files": u.get("files", 0),
            "joined": u.get("joined"),
            "last_seen": u.get("last_seen"),
            "formats": u.get("formats", {}),
        }

    def reset_stats(self) -> None:
        """ریست کردن آمار کلی (کاربران دست‌نخورده)"""
        self.data["stats"] = {
            "total_files": 0,
            "total_users": len(self.data["users"]),
            "daily": {},
        }
        self.save()

    # --------------------------------------------------------
    #                    سشن‌ها
    # --------------------------------------------------------
    def set_session(self, user_id: int, session: dict) -> None:
        """ذخیره‌ی سشن کاربر"""
        self.data["sessions"][str(user_id)] = session
        self.save()

    def get_session(self, user_id: int) -> Optional[dict]:
        """گرفتن سشن کاربر"""
        return self.data["sessions"].get(str(user_id))

    def clear_session(self, user_id: int) -> None:
        """حذف سشن کاربر"""
        self.data["sessions"].pop(str(user_id), None)
        self.save()

    def clear_all_sessions(self) -> None:
        """حذف همه‌ی سشن‌ها (مثلاً موقع ری‌استارت)"""
        self.data["sessions"] = {}
        self.save()

    # --------------------------------------------------------
    #                    کانفیگ
    # --------------------------------------------------------
    def get_config(self, key: str = None, default: Any = None) -> Any:
        """گرفتن یه مقدار از کانفیگ یا کل کانفیگ"""
        if key is None:
            return dict(self.data.get("config", {}))
        return self.data.get("config", {}).get(key, default)

    def set_config(self, **kwargs) -> None:
        """تنظیم مقادیر کانفیگ"""
        self.data.setdefault("config", {})
        self.data["config"].update(kwargs)
        self.save()

    # --------------------------------------------------------
    #                Import / Export
    # --------------------------------------------------------
    def export_data(self) -> str:
        """خروجی گرفتن از داده‌ها به‌صورت JSON"""
        return json.dumps(self.data, ensure_ascii=False, indent=2)

    def import_data(self, json_str: str, merge: bool = False) -> bool:
        """
        وارد کردن داده‌ها از JSON.

        Args:
            json_str: رشته‌ی JSON
            merge: اگه True باشه، با داده‌های فعلی ادغام می‌شه
        """
        try:
            data = json.loads(json_str)
            if merge:
                self._merge_data(data)
            else:
                self.data = self._migrate(data)
            self.save()
            return True
        except Exception as e:
            log.error(f"❌ خطا در import: {e}")
            return False

    def _merge_data(self, new_data: dict) -> None:
        """ادغام داده‌های جدید با داده‌های فعلی"""
        # کاربران
        for uid, u in new_data.get("users", {}).items():
            if uid in self.data["users"]:
                self.data["users"][uid]["files"] = self.data["users"][uid].get("files", 0) + u.get("files", 0)
            else:
                self.data["users"][uid] = u

        # آمار
        self.data["stats"]["total_files"] = self.data["stats"].get("total_files", 0) + new_data.get("stats", {}).get("total_files", 0)
        self.data["stats"]["total_users"] = len(self.data["users"])

        # کانفیگ (کانفیگ جدید جایگزین می‌شه)
        if new_data.get("config"):
            self.data.setdefault("config", {}).update(new_data["config"])

    def backup(self, backup_path: str = None) -> str:
        """ساخت نسخه‌ی پشتیبان دستی"""
        if backup_path is None:
            backup_path = f"state_backup_{int(time.time())}.json"
        shutil.copy2(self.path, backup_path)
        log.info(f"💾 نسخه‌ی پشتیبان ساخته شد: {backup_path}")
        return backup_path
