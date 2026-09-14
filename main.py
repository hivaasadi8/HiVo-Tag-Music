"""
HiVo Tag Music - Telegram Bot
=============================
ربات حرفه‌ای ویرایش تگ موزیک با:
  - پشتیبانی از MP3, FLAC, M4A, OGG, WAV
  - جستجوی چندمنبعی (iTunes + YouTube Music + MusicBrainz)
  - ReplayGain, MBID, Comment
  - قفل عضویت و پنل ادمین
  - رابط کاربری دوزبانه
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
import requests
from PIL import Image
from tagger import edit_tags
from store import Store

# ============================================================
#                    تنظیمات اولیه
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
if not TOKEN:
    log.error("❌ TELEGRAM_TOKEN پیدا نشد!")
    sys.exit(1)

ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
API = f"https://api.telegram.org/bot{TOKEN}"
OFFSET_FILE = Path("offset.json")
TEMP = Path("tmp")
TEMP.mkdir(exist_ok=True)
store = Store("state.json")
session_http = requests.Session()
MB_HEADERS = {"User-Agent": "HiVoTagMusic/2.0 (github.com/hivaasadi8)"}

SUPPORTED_FORMATS = {".mp3", ".flac", ".m4a", ".mp4", ".aac", ".ogg", ".wav"}
MAX_FILE_SIZE = 20 * 1024 * 1024

membership_cache = {}


# ============================================================
#                    توابع کمکی
# ============================================================
def human_size(b):
    b = float(b)
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def short_name(name, maxlen=32):
    return name if len(name) <= maxlen else name[:maxlen - 3] + "..."


def clean_filename(name):
    """حذف کاراکترهای غیرمجاز از اسم فایل"""
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        name = name.replace(ch, "_")
    return name.strip()


# ============================================================
#              تنظیمات قفل عضویت
# ============================================================
def get_lock_config():
    return store.get_config()


def save_lock_config(**kwargs):
    store.set_config(**kwargs)


def is_user_member(user_id, force_check=False):
    cfg = get_lock_config()
    if not cfg.get("lock_enabled") or not cfg.get("channel_username"):
        return True

    cached = membership_cache.get(user_id)
    if cached and not force_check:
        if time.time() - cached["time"] < 300:
            return cached["is_member"]

    try:
        r = session_http.post(
            f"{API}/getChatMember",
            json={"chat_id": cfg["channel_username"], "user_id": user_id},
            timeout=15,
        ).json()
        if not r.get("ok"):
            log.error(f"getChatMember: {r}")
            return True
        status = r["result"].get("status", "left")
        is_member = status in ("creator", "administrator", "member")
        membership_cache[user_id] = {"is_member": is_member, "time": time.time()}
        return is_member
    except Exception as e:
        log.error(f"membership error: {e}")
        return True


def send_join_lock(chat_id, lang="fa"):
    cfg = get_lock_config()
    text = (
        "<b>🔒 قفل عضویت</b>\n\n"
        "برای استفاده از ربات، ابتدا در کانال زیر عضو شو 👇\n\n"
        "<i>بعد از عضویت، روی «✅ عضو شدم» بزن.</i>"
    ) if lang == "fa" else (
        "<b>🔒 Membership Lock</b>\n\n"
        "To use the bot, join our channel first 👇\n\n"
        "<i>After joining, tap «✅ I Joined».</i>"
    )
    keyboard = []
    if cfg.get("channel_link"):
        keyboard.append([{
            "text": "📢 عضویت در کانال" if lang == "fa" else "📢 Join Channel",
            "url": cfg["channel_link"],
        }])
    keyboard.append([{
        "text": "✅ عضو شدم" if lang == "fa" else "✅ I Joined",
        "callback_data": "check_membership",
    }])
    send(chat_id, text, keyboard)


# ============================================================
#              پنل ادمین
# ============================================================
def admin_menu():
    cfg = get_lock_config()
    status = "🟢 فعال" if cfg.get("lock_enabled") else "🔴 غیرفعال"
    ch = cfg.get("channel_username") or "تنظیم نشده"
    link = cfg.get("channel_link") or "تنظیم نشده"
    stats = store.get_stats()

    text = (
        f"<b>👑 پنل مدیریت</b>\n\n"
        f"<blockquote>"
        f"<b>🔒 وضعیت قفل:</b> {status}\n"
        f"<b>📢 کانال:</b> <code>{ch}</code>\n"
        f"<b>🔗 لینک:</b> <code>{link}</code>"
        f"</blockquote>\n"
        f"<blockquote>"
        f"<b>📊 آمار سریع:</b>\n"
        f"├ 👥 کاربران: <b>{stats['users']}</b>\n"
        f"└ 🎵 فایل‌ها: <b>{stats['files']}</b>"
        f"</blockquote>\n\n"
        f"<i>یکی از گزینه‌ها رو انتخاب کن 👇</i>"
    )

    toggle_btn = (
        {"text": "🔴 غیرفعال کردن قفل", "callback_data": "admin_toggle"}
        if cfg.get("lock_enabled") else
        {"text": "🟢 فعال کردن قفل", "callback_data": "admin_toggle"}
    )

    keyboard = [
        [toggle_btn],
        [{"text": "📢 تنظیم کانال", "callback_data": "admin_set_channel"}],
        [{"text": "🔗 تنظیم لینک", "callback_data": "admin_set_link"}],
        [{"text": "🧪 تست قفل", "callback_data": "admin_test"}],
        [{"text": "📊 آمار کامل", "callback_data": "admin_stats"}],
        [{"text": "📤 خروجی داده‌ها", "callback_data": "admin_export"}],
        [{"text": "🔄 ریست آمار", "callback_data": "admin_reset"}],
        [{"text": "🔙 بستن پنل", "callback_data": "admin_close"}],
    ]
    return text, keyboard


# ============================================================
#              ترجمه‌ها
# ============================================================
TEXTS = {
    "fa": {
        "btn_help": "📖 راهنما",
        "btn_stats": "📊 آمار من",
        "btn_about": "👑 درباره ما",
        "btn_lang": "🌐 تغییر زبان",
        "btn_back": "🔙 بازگشت",
        "btn_cancel": "❌ انصراف",
        "btn_preview": "👁 پیش‌نمایش",
        "btn_apply": "✨ اعمال کن",
        "btn_search": "🔍 جستجوی خودکار",
        "btn_title": "🎵 اسم آهنگ",
        "btn_artist": "🎤 خواننده",
        "btn_album": "💿 آلبوم",
        "btn_year": "📅 سال",
        "btn_genre": "🎼 ژانر",
        "btn_track": "🔢 ترک",
        "btn_cover": "🖼 کاور",
        "btn_replaygain": "🎚 نرمال‌سازی",
        "btn_mbid": "🆔 شناسه MusicBrainz",
        "btn_comment": "💬 توضیحات",
        "welcome": "<b>سلام {name} عزیز 👋</b>\n\nبه <b>HiVo Tag Music</b> خوش آمدی 🎧\nمن می‌تونم فایل موزیکت رو به یه اثر حرفه‌ای تبدیل کنم.\n\n<blockquote><b>✨ قابلیت‌های من:</b>\n├ 🎵 ویرایش کامل تگ‌های صوتی\n├ 🖼 افزودن کاور با کیفیت بالا\n├ 🎚 نرمال‌سازی صدا (ReplayGain)\n├ 🆔 پشتیبانی از MusicBrainz\n├ 🔍 جستجوی چندمنبعی\n├ 🌐 پشتیبانی دوزبانه\n└ ⚡ پردازش سریع و امن</blockquote>\n\n<i>برای شروع، فایل موزیکت رو بفرست 👇</i>",
        "help": "<b>📖 راهنمای کامل</b>\n\n<blockquote><b>🎯 مراحل:</b>\n<b>۱.</b> فایل موزیک رو بفرست\n<b>۲.</b> گزینه‌ها رو ویرایش کن یا از جستجو استفاده کن\n<b>۳.</b> کاور و بقیه فیلدها رو پر کن\n<b>۴.</b> پیش‌نمایش رو ببین و تایید کن\n<b>۵.</b> فایل نهایی رو دریافت کن</blockquote>\n\n<b>📌 فرمت‌های پشتیبانی‌شده:</b>\n<code>MP3 • FLAC • M4A • OGG • WAV</code>\n\n<b>⚠️ حداکثر حجم:</b> <code>20MB</code>",
        "about": "<b>👑 درباره HiVo Tag Music</b>\n\n<blockquote>ربات حرفه‌ای ویرایش تگ موزیک که کاملاً رایگان است.</blockquote>\n\n<b>🔧 تکنولوژی:</b>\n├ Python 3.11\n├ Telegram Bot API\n├ Mutagen Engine\n├ iTunes + YouTube Music + MusicBrainz\n└ GitHub Actions\n\n<i>ساخته شده با ❤️ برای موزیک‌دوستان</i>",
        "stats": "<b>📊 آمار شما</b>\n\n<blockquote><b>🌍 آمار کلی:</b>\n├ 👥 کاربران: <b>{users}</b>\n└ 🎵 فایل‌ها: <b>{files}</b></blockquote>\n<blockquote><b>👤 آمار شما:</b>\n├ 📛 نام: <b>{name}</b>\n├ 🌐 زبان: <b>{lang}</b>\n├ 📁 فایل‌ها: <b>{my_files}</b>\n└ 📅 عضو از: <b>{joined}</b></blockquote>",
        "file_too_large": "<b>❌ فایل بزرگ‌تر از 20MB</b>\n\n<i>تلگرام اجازه دانلود فایل‌های بزرگ‌تر رو نمی‌ده.</i>",
        "unsupported_format": "<b>❌ فرمت پشتیبانی نمی‌شه</b>\n\n<i>فرمت‌های مجاز: MP3, FLAC, M4A, OGG, WAV</i>",
        "downloading": "📥 <b>در حال دریافت فایل...</b>\n<i>لطفاً صبر کن</i>",
        "download_error": "❌ <b>خطا در دریافت فایل</b>",
        "file_received": "<b>✅ فایل دریافت شد!</b>\n\n{header}\n\n<i>گزینه‌ها رو انتخاب کن 👇</i>",
        "search_prompt": "🔍 <b>جستجوی خودکار</b>\n\n<i>اسم آهنگ و خواننده رو بنویس.</i>\n\n<b>مثال:</b> <code>Shape of You Ed Sheeran</code>",
        "searching": "🔄 <b>در حال جستجو در منابع...</b>\n<i>iTunes → YouTube Music → MusicBrainz</i>",
        "search_empty": "❌ <b>چیزی پیدا نشد!</b>\n\n<i>می‌تونی اطلاعات رو دستی وارد کنی 👇</i>",
        "search_results": "🎯 <b>{count} نتیجه پیدا شد</b>\n\n<i>روی نتیجه مورد نظرت بزن 👇</i>",
        "search_applied": "✅ <b>اطلاعات اعمال شد!</b>\n\n<blockquote>📡 منبع: <b>{source}</b></blockquote>",
        "preview": "<b>👁 پیش‌نمایش نهایی</b>\n\n<blockquote>🎵 <b>اسم آهنگ:</b> <code>{title}</code>\n🎤 <b>خواننده:</b> <code>{artist}</code>\n💿 <b>آلبوم:</b> <code>{album}</code>\n📅 <b>سال:</b> <code>{year}</code>\n🎼 <b>ژانر:</b> <code>{genre}</code>\n🔢 <b>ترک:</b> <code>{track}</code>\n🖼 <b>کاور:</b> {cover}\n🎚 <b>ReplayGain:</b> {rg}\n🆔 <b>MBID:</b> {mbid}\n💬 <b>توضیحات:</b> {comment}</blockquote>\n\n<i>از اعمال تغییرات مطمئنی؟</i>",
        "cover_yes": "✅ دارد",
        "cover_no": "❌ ندارد",
        "yes": "✅ بله",
        "no": "❌ خیر",
        "applying": "⏳ <b>[۱/۳] اعمال تگ‌ها...</b>\n<i>موتور Mutagen در حال کاره</i>",
        "uploading": "✅ <b>[۲/۳] تگ‌ها اعمال شد</b>\n\n📤 <b>[۳/۳] آپلود فایل...</b>\n<blockquote>📦 حجم: <b>{size}</b></blockquote>",
        "success": "✨ <b>عملیات با موفقیت انجام شد!</b>\n\n<i>ممنون از HiVo Tag Music 🎧</i>",
        "upload_error": "❌ <b>خطا در آپلود فایل</b>",
        "cancelled": "❌ <b>عملیات لغو شد</b>",
        "session_expired": "⚠️ سشن منقضی شده، فایل رو دوباره بفرست",
        "saved_field": "✅ <b>ثبت شد:</b> <code>{value}</code>\n\n<i>تغییرات دیگه‌ای اعمال کن یا پیش‌نمایش رو بزن 👇</i>",
        "cover_saved": "🖼 <b>کاور ثبت شد!</b>",
        "cover_error": "❌ خطا در پردازش کاور",
        "lang_changed": "✅ <b>زبان تغییر کرد</b>\n\n🌐 زبان فعلی: <b>فارسی</b>",
        "lang_menu": "🌐 <b>زبان مورد نظرت رو انتخاب کن:</b>",
        "caption_success": "✅ <b>تگ‌ها با موفقیت اعمال شد!</b>\n\n<blockquote>🎵 <b>{title}</b>\n🎤 {artist}\n💿 {album}</blockquote>\n\n<i>HiVo Tag Music 🎧</i>",
        "prompt_title": "🎵 <b>اسم جدید آهنگ:</b>\n\n<i>مثال: Shape of You</i>",
        "prompt_artist": "🎤 <b>اسم جدید خواننده:</b>\n\n<i>مثال: Ed Sheeran</i>",
        "prompt_album": "💿 <b>اسم جدید آلبوم:</b>\n\n<i>مثال: Divide</i>",
        "prompt_year": "📅 <b>سال انتشار:</b>\n\n<i>مثال: 2017</i>",
        "prompt_genre": "🎼 <b>ژانر:</b>\n\n<i>مثال: Pop, Rock</i>",
        "prompt_track": "🔢 <b>شماره ترک:</b>\n\n<i>مثال: 1</i>",
        "prompt_cover": "🖼 <b>عکس کاور رو بفرست</b>\n\n<i>به‌صورت Photo یا Document</i>",
        "prompt_comment": "💬 <b>توضیحات رو بنویس:</b>\n\n<i>مثال: Live version, Remastered 2024</i>",
        "file_header": "<blockquote><b>🎧 فایل در حال ویرایش</b>\n├ 📛 نام: <code>{name}</code>\n├ 📦 حجم: <code>{size}</code>\n├ 🎼 فرمت: <code>{fmt}</code>\n└ ✏️ تغییرات: <b>{count}</b> مورد</blockquote>",
        "welcome_back": "✅ <b>خوش اومدی!</b>\n\n<i>حالا می‌تونی از ربات استفاده کنی 🎧</i>",
        "not_joined": "❌ <b>هنوز عضو نشدی!</b>\n\n<i>اول عضو کانال شو، بعد دوباره بزن.</i>",
        "admin_no_access": "⛔ شما ادمین نیستید.",
        "admin_saved_channel": "✅ <b>کانال ذخیره شد!</b>\n\n📢 <code>{value}</code>",
        "admin_saved_link": "✅ <b>لینک ذخیره شد!</b>\n\n🔗 <code>{value}</code>",
        "admin_set_channel_prompt": "📢 <b>یوزرنیم کانال رو بفرست</b>\n\n<i>مثال: @HiVoChannel</i>\n\n<i>نکته: ربات باید ادمین کانال باشه.</i>",
        "admin_set_link_prompt": "🔗 <b>لینک کانال رو بفرست</b>\n\n<i>مثال: https://t.me/HiVoChannel</i>",
        "admin_toggled_on": "🟢 قفل فعال شد!",
        "admin_toggled_off": "🔴 قفل غیرفعال شد!",
        "admin_need_channel": "⚠️ اول باید کانال رو تنظیم کنی!",
        "admin_test_member": "✅ شما عضو کانال هستید.",
        "admin_test_not_member": "❌ شما عضو کانال نیستید.",
        "admin_test_disabled": "🔴 قفل غیرفعاله.",
        "admin_stats_text": "<b>📊 آمار کامل ربات</b>\n\n<blockquote><b>🌍 کلی:</b>\n├ 👥 کاربران: <b>{users}</b>\n└ 🎵 فایل‌ها: <b>{files}</b></blockquote>\n<blockquote><b>📅 ۷ روز اخیر:</b>\n{daily}</blockquote>\n<blockquote><b>⚙️ وضعیت:</b>\n├ 🔒 قفل: <b>{lock}</b>\n└ 📢 کانال: <code>{channel}</code></blockquote>",
        "admin_reset_confirm": "⚠️ <b>مطمئنی؟</b>\n\nآمار کلی ریست میشه ولی کاربران دست‌نخورده می‌مونن.",
        "admin_reset_done": "✅ آمار ریست شد.",
        "admin_export_ready": "📤 <b>خروجی داده‌ها آماده‌ست.</b>\n\n<i>فایل در پیام بعدی ارسال میشه.</i>",
        "replaygain_prompt": "🎚 <b>تنظیم ReplayGain</b>\n\n<i>مقدارها رو با فرمت زیر بفرست:</i>\n\n<code>track_gain=-6.5 dB</code>\n<code>track_peak=0.98</code>\n<code>album_gain=-5.0 dB</code>\n<code>album_peak=0.95</code>\n\n<i>هر خط یه مقدار. خطوط خالی نادیده گرفته میشن.</i>",
        "replaygain_saved": "✅ <b>ReplayGain ثبت شد!</b>",
        "mbid_prompt": "🆔 <b>شناسه‌های MusicBrainz</b>\n\n<i>هر شناسه رو با فرمت زیر بفرست:</i>\n\n<code>track_id=xxxx-xxxx</code>\n<code>album_id=xxxx-xxxx</code>\n<code>artist_id=xxxx-xxxx</code>\n\n<i>هر خط یه شناسه.</i>",
        "mbid_saved": "✅ <b>شناسه‌ها ثبت شد!</b>",
    },
    "en": {
        "btn_help": "📖 Help",
        "btn_stats": "📊 My Stats",
        "btn_about": "👑 About",
        "btn_lang": "🌐 Language",
        "btn_back": "🔙 Back",
        "btn_cancel": "❌ Cancel",
        "btn_preview": "👁 Preview",
        "btn_apply": "✨ Apply",
        "btn_search": "🔍 Auto Search",
        "btn_title": "🎵 Title",
        "btn_artist": "🎤 Artist",
        "btn_album": "💿 Album",
        "btn_year": "📅 Year",
        "btn_genre": "🎼 Genre",
        "btn_track": "🔢 Track",
        "btn_cover": "🖼 Cover",
        "btn_replaygain": "🎚 ReplayGain",
        "btn_mbid": "🆔 MusicBrainz ID",
        "btn_comment": "💬 Comment",
        "welcome": "<b>Hello {name} 👋</b>\n\nWelcome to <b>HiVo Tag Music</b> 🎧\n\n<blockquote><b>✨ Features:</b>\n├ 🎵 Full tag editing\n├ 🖼 High-quality cover art\n├ 🎚 ReplayGain support\n├ 🆔 MusicBrainz IDs\n├ 🔍 Multi-source search\n├ 🌐 Multi-language\n└ ⚡ Fast & secure</blockquote>\n\n<i>Send your music file to start 👇</i>",
        "help": "<b>📖 Guide</b>\n\n<blockquote><b>🎯 Steps:</b>\n<b>1.</b> Send music file\n<b>2.</b> Edit options or use search\n<b>3.</b> Fill cover & other fields\n<b>4.</b> Preview & confirm\n<b>5.</b> Get edited file</blockquote>\n\n<b>📌 Supported:</b> <code>MP3 • FLAC • M4A • OGG • WAV</code>\n<b>⚠️ Max size:</b> <code>20MB</code>",
        "about": "<b>👑 About HiVo Tag Music</b>\n\n<blockquote>Professional music tag editor. Free.</blockquote>\n\n<i>Made with ❤️ for music lovers</i>",
        "stats": "<b>📊 Your Stats</b>\n\n<blockquote><b>🌍 Global:</b>\n├ 👥 Users: <b>{users}</b>\n└ 🎵 Files: <b>{files}</b></blockquote>\n<blockquote><b>👤 You:</b>\n├ 📛 Name: <b>{name}</b>\n├ 🌐 Lang: <b>{lang}</b>\n├ 📁 Files: <b>{my_files}</b>\n└ 📅 Joined: <b>{joined}</b></blockquote>",
        "file_too_large": "<b>❌ File > 20MB</b>",
        "unsupported_format": "<b>❌ Unsupported format</b>\n\n<i>Supported: MP3, FLAC, M4A, OGG, WAV</i>",
        "downloading": "📥 <b>Downloading...</b>",
        "download_error": "❌ <b>Download failed</b>",
        "file_received": "<b>✅ File received!</b>\n\n{header}",
        "search_prompt": "🔍 <b>Auto Search</b>\n\nType song + artist.\n\n<b>e.g.</b> <code>Shape of You Ed Sheeran</code>",
        "searching": "🔄 <b>Searching...</b>",
        "search_empty": "❌ <b>Nothing found!</b>",
        "search_results": "🎯 <b>{count} results</b>",
        "search_applied": "✅ <b>Applied!</b>\n\n<blockquote>📡 Source: <b>{source}</b></blockquote>",
        "preview": "<b>👁 Preview</b>\n\n<blockquote>🎵 <b>Title:</b> <code>{title}</code>\n🎤 <b>Artist:</b> <code>{artist}</code>\n💿 <b>Album:</b> <code>{album}</code>\n📅 <b>Year:</b> <code>{year}</code>\n🎼 <b>Genre:</b> <code>{genre}</code>\n🔢 <b>Track:</b> <code>{track}</code>\n🖼 <b>Cover:</b> {cover}\n🎚 <b>ReplayGain:</b> {rg}\n🆔 <b>MBID:</b> {mbid}\n💬 <b>Comment:</b> {comment}</blockquote>",
        "cover_yes": "✅ Yes",
        "cover_no": "❌ No",
        "yes": "✅ Yes",
        "no": "❌ No",
        "applying": "⏳ <b>[1/3] Applying tags...</b>",
        "uploading": "✅ <b>[2/3] Applied</b>\n\n📤 <b>[3/3] Uploading...</b>\n<blockquote>📦 Size: <b>{size}</b></blockquote>",
        "success": "✨ <b>Done!</b>\n\n<i>Thanks for using HiVo Tag Music 🎧</i>",
        "upload_error": "❌ <b>Upload failed</b>",
        "cancelled": "❌ <b>Cancelled</b>",
        "session_expired": "⚠️ Session expired",
        "saved_field": "✅ <b>Saved:</b> <code>{value}</code>",
        "cover_saved": "🖼 <b>Cover saved!</b>",
        "cover_error": "❌ Cover error",
        "lang_changed": "✅ <b>Language changed</b>\n\n🌐 Current: <b>English</b>",
        "lang_menu": "🌐 <b>Choose language:</b>",
        "caption_success": "✅ <b>Tags applied!</b>\n\n<blockquote>🎵 <b>{title}</b>\n🎤 {artist}\n💿 {album}</blockquote>\n\n<i>HiVo Tag Music 🎧</i>",
        "prompt_title": "🎵 <b>New title:</b>",
        "prompt_artist": "🎤 <b>New artist:</b>",
        "prompt_album": "💿 <b>New album:</b>",
        "prompt_year": "📅 <b>Year:</b>",
        "prompt_genre": "🎼 <b>Genre:</b>",
        "prompt_track": "🔢 <b>Track:</b>",
        "prompt_cover": "🖼 <b>Send cover</b>",
        "prompt_comment": "💬 <b>Write comment:</b>\n\n<i>e.g. Live version, Remastered 2024</i>",
        "file_header": "<blockquote><b>🎧 Editing</b>\n├ 📛 <code>{name}</code>\n├ 📦 <code>{size}</code>\n├ 🎼 <code>{fmt}</code>\n└ ✏️ <b>{count}</b> changes</blockquote>",
        "welcome_back": "✅ <b>Welcome!</b>",
        "not_joined": "❌ <b>Not joined!</b>",
        "admin_no_access": "⛔ Admin only.",
        "admin_saved_channel": "✅ Channel saved: <code>{value}</code>",
        "admin_saved_link": "✅ Link saved: <code>{value}</code>",
        "admin_set_channel_prompt": "📢 Send channel username (e.g. @HiVoChannel)",
        "admin_set_link_prompt": "🔗 Send channel link",
        "admin_toggled_on": "🟢 Lock enabled!",
        "admin_toggled_off": "🔴 Lock disabled!",
        "admin_need_channel": "⚠️ Set channel first!",
        "admin_test_member": "✅ You are member.",
        "admin_test_not_member": "❌ You are NOT member.",
        "admin_test_disabled": "🔴 Lock disabled.",
        "admin_stats_text": "<b>📊 Full Stats</b>\n\n<blockquote>👥 Users: <b>{users}</b>\n🎵 Files: <b>{files}</b></blockquote>\n<blockquote><b>📅 Last 7 days:</b>\n{daily}</blockquote>\n<blockquote>🔒 Lock: <b>{lock}</b>\n📢 Channel: <code>{channel}</code></blockquote>",
        "admin_reset_confirm": "⚠️ <b>Are you sure?</b>",
        "admin_reset_done": "✅ Stats reset.",
        "admin_export_ready": "📤 <b>Export ready.</b>",
        "replaygain_prompt": "🎚 <b>ReplayGain Settings</b>\n\n<i>Send values in this format:</i>\n\n<code>track_gain=-6.5 dB</code>\n<code>track_peak=0.98</code>\n<code>album_gain=-5.0 dB</code>\n<code>album_peak=0.95</code>",
        "replaygain_saved": "✅ <b>ReplayGain saved!</b>",
        "mbid_prompt": "🆔 <b>MusicBrainz IDs</b>\n\n<code>track_id=xxxx</code>\n<code>album_id=xxxx</code>\n<code>artist_id=xxxx</code>",
        "mbid_saved": "✅ <b>MBIDs saved!</b>",
    },
}


def T(key, lang="fa", **kwargs):
    text = TEXTS.get(lang, TEXTS["fa"]).get(key, key)
    try:
        return text.format(**kwargs) if kwargs else text
    except Exception:
        return text


def get_user_lang(user_id):
    return store.get_user_lang(user_id)


def set_user_lang(user_id, lang):
    store.set_user_lang(user_id, lang)


# ============================================================
#                    Telegram API
# ============================================================
def api(method, **params):
    try:
        r = session_http.post(f"{API}/{method}", json=params, timeout=60)
        res = r.json()
        if not res.get("ok"):
            log.error(f"⚠️ API error {method}: {res}")
        return res
    except Exception as e:
        log.error(f"❌ Network error {method}: {e}")
        return {"ok": False}


def send(chat_id, text, keyboard=None, parse_mode="HTML"):
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if keyboard:
        data["reply_markup"] = {"inline_keyboard": keyboard}
    return api("sendMessage", **data)


def send_photo_file(chat_id, photo_path, caption, keyboard=None, parse_mode="HTML"):
    data = {"chat_id": chat_id, "caption": caption, "parse_mode": parse_mode}
    if keyboard:
        data["reply_markup"] = {"inline_keyboard": keyboard}
    try:
        with open(photo_path, "rb") as f:
            requests.post(f"{API}/sendPhoto", data=data, files={"photo": f}, timeout=60)
    except Exception as e:
        log.error(f"sendPhoto error: {e}")


def send_document(chat_id, doc_path, caption=""):
    try:
        with open(doc_path, "rb") as f:
            requests.post(
                f"{API}/sendDocument",
                data={"chat_id": chat_id, "caption": caption},
                files={"document": f},
                timeout=120,
            )
    except Exception as e:
        log.error(f"sendDocument error: {e}")


def edit_msg(chat_id, msg_id, text, keyboard=None):
    data = {"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = {"inline_keyboard": keyboard}
    return api("editMessageText", **data)


def answer_cb(cb_id, text=""):
    api("answerCallbackQuery", callback_query_id=cb_id, text=text)


def get_offset():
    if OFFSET_FILE.exists():
        try:
            return json.loads(OFFSET_FILE.read_text()).get("offset", 0)
        except Exception:
            return 0
    return 0


def save_offset(o):
    OFFSET_FILE.write_text(json.dumps({"offset": o}))


def download(file_id, name):
    info = api("getFile", file_id=file_id)
    if not info.get("ok"):
        return None
    path = info["result"]["file_path"]
    url = f"https://api.telegram.org/file/bot{TOKEN}/{path}"
    dest = TEMP / name
    try:
        r = session_http.get(url, timeout=180)
        dest.write_bytes(r.content)
        return dest
    except Exception as e:
        log.error(f"download error: {e}")
        return None


def send_audio(chat_id, path, caption="", cover_path=None, title=None, performer=None):
    for attempt in range(3):
        files = {}
        try:
            log.info(f"📤 Upload try {attempt+1}")
            files = {"audio": open(path, "rb")}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
            if title:
                data["title"] = title[:64]
            if performer:
                data["performer"] = performer[:64]

            if cover_path and Path(cover_path).exists():
                thumb_path = TEMP / "thumb.jpg"
                img = Image.open(cover_path)
                img = img.convert("RGB")
                img.thumbnail((320, 320))
                img.save(thumb_path, "JPEG", quality=82)
                files["thumb"] = open(thumb_path, "rb")

            r = session_http.post(f"{API}/sendAudio", data=data, files=files, timeout=300)
            for f in files.values():
                try:
                    f.close()
                except Exception:
                    pass
            if r.status_code == 200:
                return True
            log.error(f"Send error: {r.text}")
        except Exception as e:
            log.error(f"❌ Upload error: {e}")
            for f in files.values():
                try:
                    f.close()
                except Exception:
                    pass
        time.sleep(2)
    return False


# ============================================================
#                    جستجو
# ============================================================
def search_itunes(query, limit=5):
    try:
        r = session_http.get(
            "https://itunes.apple.com/search",
            params={"term": query, "media": "music", "entity": "song", "limit": limit},
            timeout=20,
        )
        if r.status_code != 200:
            return []
        out = []
        for item in r.json().get("results", [])[:limit]:
            artwork = item.get("artworkUrl100", "").replace("100x100", "1000x1000")
            out.append({
                "title": item.get("trackName", "Unknown"),
                "artist": item.get("artistName", "Unknown"),
                "album": item.get("collectionName", ""),
                "year": (item.get("releaseDate", "") or "")[:4],
                "genre": item.get("primaryGenreName", ""),
                "artwork_url": artwork,
            })
        return out
    except Exception as e:
        log.error(f"iTunes: {e}")
        return []


def search_ytmusic(query, limit=5):
    try:
        from ytmusicapi import YTMusic
        yt = YTMusic()
        results = yt.search(query, filter="songs", limit=limit)
        out = []
        for item in results[:limit]:
            if item.get("resultType") != "song":
                continue
            artists = item.get("artists", [])
            artist = artists[0]["name"] if artists else "Unknown"
            album = item.get("album", {})
            album_name = album.get("name", "") if isinstance(album, dict) else ""
            year = str(album.get("year", "")) if isinstance(album, dict) and album.get("year") else ""
            thumbs = item.get("thumbnails", [])
            artwork = thumbs[-1]["url"] if thumbs else ""
            out.append({
                "title": item.get("title", "Unknown"),
                "artist": artist,
                "album": album_name,
                "year": year,
                "genre": "",
                "artwork_url": artwork,
            })
        return out
    except Exception as e:
        log.error(f"YTM: {e}")
        return []


def search_musicbrainz(query, limit=5):
    try:
        r = session_http.get(
            "https://musicbrainz.org/ws/2/recording/",
            params={"query": query, "fmt": "json", "limit": limit},
            headers=MB_HEADERS,
            timeout=20,
        )
        if r.status_code != 200:
            return []
        out = []
        for rec in r.json().get("recordings", [])[:limit]:
            artist = rec["artist-credit"][0].get("name", "") if rec.get("artist-credit") else ""
            releases = rec.get("releases", [])
            release = releases[0] if releases else {}
            tags = rec.get("tags", [])
            out.append({
                "title": rec.get("title", "Unknown"),
                "artist": artist or "Unknown",
                "album": release.get("title", ""),
                "year": (release.get("date", "") or "")[:4],
                "genre": tags[0]["name"] if tags else "",
                "artwork_url": "",
                "mbid": rec.get("id", ""),
            })
        return out
    except Exception as e:
        log.error(f"MB: {e}")
        return []


def search_all_sources(query, limit=5):
    for name, fn in [("iTunes", search_itunes), ("YouTube Music", search_ytmusic), ("MusicBrainz", search_musicbrainz)]:
        results = fn(query, limit)
        if results:
            return results, name
    return [], ""


def fetch_cover_art(artwork_url, dest_path):
    if not artwork_url:
        return False
    try:
        r = session_http.get(artwork_url, timeout=40, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 1000:
            with open(dest_path, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        log.error(f"Cover: {e}")
    return False


# ============================================================
#                    منوها
# ============================================================
def main_menu(lang="fa"):
    return [
        [{"text": T("btn_help", lang), "callback_data": "help"}],
        [{"text": T("btn_stats", lang), "callback_data": "my_stats"},
         {"text": T("btn_about", lang), "callback_data": "about"}],
        [{"text": T("btn_lang", lang), "callback_data": "lang_menu"}],
    ]


def lang_menu():
    return [
        [{"text": "🇮🇷 فارسی", "callback_data": "setlang_fa"},
         {"text": "🇬🇧 English", "callback_data": "setlang_en"}],
        [{"text": "🔙", "callback_data": "back_main"}],
    ]


def session_header(session, lang="fa"):
    name = short_name(session.get("orig_name", "---"), 30)
    try:
        size = human_size(Path(session["file"]).stat().st_size) if Path(session["file"]).exists() else "---"
    except Exception:
        size = "---"
    fmt = Path(session.get("orig_name", "music.mp3")).suffix.lstrip(".").upper() or "—"
    count = sum(1 for f in ["title", "artist", "album", "year", "genre", "track", "comment"] if session.get(f))
    if session.get("cover"):
        count += 1
    if session.get("replaygain"):
        count += 1
    if session.get("mbids"):
        count += 1
    return T("file_header", lang, name=name, size=size, fmt=fmt, count=count)


def edit_menu(session, lang="fa"):
    def btn(field, emoji, key):
        mark = "✅" if session.get(field) else "◽️"
        return {"text": f"{emoji} {T(key, lang)} {mark}", "callback_data": f"f_{field}"}

    return [
        [btn("title", "🎵", "btn_title"), btn("artist", "🎤", "btn_artist")],
        [btn("album", "💿", "btn_album"), btn("year", "📅", "btn_year")],
        [btn("genre", "🎼", "btn_genre"), btn("track", "🔢", "btn_track")],
        [btn("cover", "🖼", "btn_cover"), btn("comment", "💬", "btn_comment")],
        [btn("replaygain", "🎚", "btn_replaygain"), btn("mbids", "🆔", "btn_mbid")],
        [{"text": T("btn_search", lang), "callback_data": "search"}],
        [{"text": T("btn_preview", lang), "callback_data": "preview"}],
        [{"text": T("btn_cancel", lang), "callback_data": "cancel"}],
    ]


def preview_menu(lang="fa"):
    return [
        [{"text": T("btn_apply", lang), "callback_data": "apply"}],
        [{"text": T("btn_back", lang), "callback_data": "back"}],
        [{"text": T("btn_cancel", lang), "callback_data": "cancel"}],
    ]


def search_results_menu(results, lang="fa"):
    rows = []
    for i, r in enumerate(results):
        title = short_name(f"{r['title']} - {r['artist']}", 50)
        rows.append([{"text": f"{i+1}. {title}", "callback_data": f"sr_{i}"}])
    rows.append([{"text": T("btn_cancel", lang), "callback_data": "cancel"}])
    return rows


# ============================================================
#                    دستورات
# ============================================================
def cmd_start(chat_id, user):
    store.add_user(user["id"], user.get("first_name", ""))
    lang = get_user_lang(user["id"])

    if not is_user_member(user["id"]):
        send_join_lock(chat_id, lang)
        return

    text = T("welcome", lang, name=user.get("first_name", ""))
    banner = Path("banner.jpg")
    if banner.exists():
        send_photo_file(chat_id, str(banner), text, main_menu(lang))
    else:
        send(chat_id, text, main_menu(lang))


def cmd_help(chat_id, user):
    if not is_user_member(user["id"]):
        send_join_lock(chat_id, get_user_lang(user["id"]))
        return
    lang = get_user_lang(user["id"])
    send(chat_id, T("help", lang), main_menu(lang))


def cmd_about(chat_id, user):
    if not is_user_member(user["id"]):
        send_join_lock(chat_id, get_user_lang(user["id"]))
        return
    lang = get_user_lang(user["id"])
    send(chat_id, T("about", lang), main_menu(lang))


def cmd_stats(chat_id, user):
    if not is_user_member(user["id"]):
        send_join_lock(chat_id, get_user_lang(user["id"]))
        return
    lang = get_user_lang(user["id"])
    s = store.get_stats()
    us = store.get_user_stats(user["id"])
    me = store.get_user(user["id"]) or {}
    lang_name = "فارسی" if lang == "fa" else "English"

    joined_ts = us.get("joined")
    if joined_ts:
        joined = time.strftime("%Y-%m-%d", time.localtime(joined_ts))
    else:
        joined = "—"

    text = T("stats", lang,
             users=s["users"], files=s["files"],
             name=me.get("name", "—"),
             my_files=us.get("files", 0),
             lang=lang_name, joined=joined)
    send(chat_id, text, main_menu(lang))


def cmd_admin(chat_id, user):
    if user["id"] != ADMIN_ID:
        send(chat_id, T("admin_no_access", get_user_lang(user["id"])))
        return
    text, keyboard = admin_menu()
    send(chat_id, text, keyboard)


def handle_audio(chat_id, user, msg):
    lang = get_user_lang(user["id"])
    if not is_user_member(user["id"]):
        send_join_lock(chat_id, lang)
        return

    audio = msg.get("audio") or msg.get("document")
    if not audio:
        return

    size = audio.get("file_size", 0)
    if size > MAX_FILE_SIZE:
        send(chat_id, T("file_too_large", lang), main_menu(lang))
        return

    ext = ".mp3"
    if audio.get("file_name"):
        ext = Path(audio["file_name"]).suffix.lower() or ".mp3"

    if ext not in SUPPORTED_FORMATS:
        send(chat_id, T("unsupported_format", lang), main_menu(lang))
        return

    tmp_name = f"{user['id']}_{int(time.time())}{ext}"
    send(chat_id, T("downloading", lang))

    path = download(audio["file_id"], tmp_name)
    if not path:
        send(chat_id, T("download_error", lang))
        return

    session = {
        "file": str(path),
        "orig_name": audio.get("file_name", "music" + ext),
        "title": audio.get("title"),
        "artist": audio.get("performer"),
        "album": None, "year": None, "genre": None, "track": None,
        "cover": None, "comment": None,
        "replaygain": None, "mbids": None,
    }
    store.set_session(user["id"], session)
    send(chat_id, T("file_received", lang, header=session_header(session, lang)), edit_menu(session, lang))


FIELD_KEYS = {
    "f_title": ("title", "prompt_title"),
    "f_artist": ("artist", "prompt_artist"),
    "f_album": ("album", "prompt_album"),
    "f_year": ("year", "prompt_year"),
    "f_genre": ("genre", "prompt_genre"),
    "f_track": ("track", "prompt_track"),
    "f_cover": ("cover", "prompt_cover"),
    "f_comment": ("comment", "prompt_comment"),
    "f_replaygain": ("replaygain", "replaygain_prompt"),
    "f_mbids": ("mbids", "mbid_prompt"),
}


# ============================================================
#                    Callback Handler
# ============================================================
def handle_callback(cb):
    chat_id = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]
    user = cb["from"]
    data = cb["data"]
    lang = get_user_lang(user["id"])
    is_admin = (user["id"] == ADMIN_ID)

    # ============ پنل ادمین ============
    if data.startswith("admin_"):
        if not is_admin:
            answer_cb(cb["id"], T("admin_no_access", lang))
            return

        if data == "admin_close":
            answer_cb(cb["id"])
            edit_msg(chat_id, msg_id, "👑 <b>پنل بسته شد.</b>")
            return

        if data == "admin_toggle":
            cfg = get_lock_config()
            if not cfg.get("channel_username") and not cfg.get("lock_enabled"):
                answer_cb(cb["id"], T("admin_need_channel", lang))
                return
            new_state = not cfg.get("lock_enabled")
            save_lock_config(lock_enabled=new_state)
            answer_cb(cb["id"], T("admin_toggled_on" if new_state else "admin_toggled_off", lang))
            text, keyboard = admin_menu()
            edit_msg(chat_id, msg_id, text, keyboard)
            return

        if data == "admin_set_channel":
            answer_cb(cb["id"])
            store.data.setdefault("admin_awaiting", {})[str(user["id"])] = "channel_username"
            store.save()
            edit_msg(chat_id, msg_id, T("admin_set_channel_prompt", lang))
            return

        if data == "admin_set_link":
            answer_cb(cb["id"])
            store.data.setdefault("admin_awaiting", {})[str(user["id"])] = "channel_link"
            store.save()
            edit_msg(chat_id, msg_id, T("admin_set_link_prompt", lang))
            return

        if data == "admin_test":
            if not get_lock_config().get("lock_enabled"):
                answer_cb(cb["id"], T("admin_test_disabled", lang))
                return
            if is_user_member(user["id"], force_check=True):
                answer_cb(cb["id"], T("admin_test_member", lang))
            else:
                answer_cb(cb["id"], T("admin_test_not_member", lang))
            return

        if data == "admin_stats":
            s = store.get_stats()
            cfg = get_lock_config()
            daily = s.get("daily", {})
            sorted_days = sorted(daily.keys())[-7:]
            daily_lines = "\n".join([f"├ {d}: <b>{daily[d]}</b>" for d in sorted_days]) or "├ —"
            answer_cb(cb["id"])
            text = T("admin_stats_text", lang,
                     users=s["users"], files=s["files"],
                     lock="🟢" if cfg.get("lock_enabled") else "🔴",
                     channel=cfg.get("channel_username") or "—",
                     daily=daily_lines)
            send(chat_id, text)
            return

        if data == "admin_export":
            answer_cb(cb["id"], "📤")
            export_path = TEMP / f"export_{int(time.time())}.json"
            export_path.write_text(store.export_data(), encoding="utf-8")
            send_document(chat_id, str(export_path), caption="📤 <b>خروجی داده‌های ربات</b>")
            try:
                export_path.unlink()
            except Exception:
                pass
            return

        if data == "admin_reset":
            answer_cb(cb["id"])
            edit_msg(chat_id, msg_id, T("admin_reset_confirm", lang), [
                [{"text": "✅ بله", "callback_data": "admin_reset_yes"},
                 {"text": "❌ خیر", "callback_data": "admin_close"}],
            ])
            return

        if data == "admin_reset_yes":
            store.reset_stats()
            answer_cb(cb["id"], T("admin_reset_done", lang))
            text, keyboard = admin_menu()
            edit_msg(chat_id, msg_id, text, keyboard)
            return
        return

    # ============ چک عضویت ============
    if data not in ("check_membership", "help"):
        if not is_user_member(user["id"]) and not is_admin:
            answer_cb(cb["id"], T("not_joined", lang))
            send_join_lock(chat_id, lang)
            return

    if data == "check_membership":
        if is_user_member(user["id"], force_check=True):
            answer_cb(cb["id"], "✅")
            edit_msg(chat_id, msg_id, T("welcome_back", lang), main_menu(lang))
        else:
            answer_cb(cb["id"], T("not_joined", lang))
            send_join_lock(chat_id, lang)
        return

    if data == "back_main":
        answer_cb(cb["id"])
        edit_msg(chat_id, msg_id, T("welcome", lang, name=user.get("first_name", "")), main_menu(lang))
        return
    if data == "help":
        answer_cb(cb["id"])
        send(chat_id, T("help", lang), main_menu(lang))
        return
    if data == "my_stats":
        answer_cb(cb["id"])
        cmd_stats(chat_id, user)
        return
    if data == "about":
        answer_cb(cb["id"])
        send(chat_id, T("about", lang), main_menu(lang))
        return
    if data == "lang_menu":
        answer_cb(cb["id"])
        edit_msg(chat_id, msg_id, T("lang_menu", lang), lang_menu())
        return
    if data.startswith("setlang_"):
        new_lang = data.split("_", 1)[1]
        if new_lang in ("fa", "en"):
            set_user_lang(user["id"], new_lang)
            answer_cb(cb["id"], "✅")
            edit_msg(chat_id, msg_id, T("lang_changed", new_lang), main_menu(new_lang))
        return

    if data == "cancel":
        answer_cb(cb["id"], "❌")
        store.clear_session(user["id"])
        edit_msg(chat_id, msg_id, T("cancelled", lang))
        return

    session = store.get_session(user["id"])
    if not session:
        answer_cb(cb["id"], T("session_expired", lang))
        return

    if data == "back":
        answer_cb(cb["id"])
        edit_msg(chat_id, msg_id,
                 T("file_received", lang, header=session_header(session, lang)),
                 edit_menu(session, lang))
        return

    if data == "search":
        answer_cb(cb["id"])
        session["awaiting"] = "search_query"
        store.set_session(user["id"], session)
        send(chat_id, T("search_prompt", lang))
        return

    if data.startswith("sr_"):
        try:
            idx = int(data.split("_", 1)[1])
        except Exception:
            answer_cb(cb["id"], "❌")
            return
        results = session.get("search_results", [])
        if idx >= len(results):
            answer_cb(cb["id"], "❌")
            return
        r = results[idx]
        answer_cb(cb["id"], "✅")

        session.update({
            "title": r["title"],
            "artist": r["artist"],
            "album": r["album"],
            "year": r["year"],
        })
        if r.get("genre"):
            session["genre"] = r["genre"]
        if r.get("mbid"):
            session["mbids"] = {"track_id": r["mbid"]}

        edit_msg(chat_id, msg_id, T("searching", lang))
        cover_path = TEMP / f"cover_mb_{user['id']}.jpg"
        if r.get("artwork_url") and fetch_cover_art(r["artwork_url"], cover_path):
            try:
                img = Image.open(cover_path)
                img = img.convert("RGB")
                img.thumbnail((800, 800))
                img.save(cover_path, "JPEG", quality=88)
                session["cover"] = str(cover_path)
            except Exception as e:
                log.error(f"cover: {e}")

        store.set_session(user["id"], session)
        source = session.get("search_source", "")
        text = f"{T('search_applied', lang, source=source)}\n\n{session_header(session, lang)}"
        edit_msg(chat_id, msg_id, text, edit_menu(session, lang))
        return

    if data == "preview":
        answer_cb(cb["id"])
        cover_status = T("cover_yes", lang) if session.get("cover") else T("cover_no", lang)
        rg_status = T("yes", lang) if session.get("replaygain") else T("no", lang)
        mbid_status = T("yes", lang) if session.get("mbids") else T("no", lang)
        text = T("preview", lang,
                 title=session.get("title") or "—",
                 artist=session.get("artist") or "—",
                 album=session.get("album") or "—",
                 year=session.get("year") or "—",
                 genre=session.get("genre") or "—",
                 track=session.get("track") or "—",
                 cover=cover_status,
                 rg=rg_status,
                 mbid=mbid_status,
                 comment=session.get("comment") or "—")
        edit_msg(chat_id, msg_id, text, preview_menu(lang))
        return

    if data == "apply":
        answer_cb(cb["id"], "⏳")
        edit_msg(chat_id, msg_id, T("applying", lang))
        try:
            # ✅ استفاده از قابلیت‌های جدید tagger.py
            edit_tags(
                file_path=session["file"],
                title=session.get("title"),
                artist=session.get("artist"),
                album=session.get("album"),
                year=session.get("year"),
                genre=session.get("genre"),
                track=session.get("track"),
                cover_path=session.get("cover"),
                replaygain=session.get("replaygain"),
                mbids=session.get("mbids"),
                comment=session.get("comment"),
            )
            out = Path(session["file"])
            user_temp = TEMP / str(user["id"])
            user_temp.mkdir(exist_ok=True)

            final_title = (session.get("title") or "").strip()
            if final_title:
                clean_name = f"{final_title}{out.suffix}"
            else:
                clean_name = session.get("orig_name") or f"music{out.suffix}"
            clean_name = clean_filename(clean_name)

            new_name = user_temp / clean_name
            out.rename(new_name)

            size_str = human_size(new_name.stat().st_size)
            edit_msg(chat_id, msg_id, T("uploading", lang, size=size_str))

            caption = T("caption_success", lang,
                        title=session.get("title") or "Music",
                        artist=session.get("artist") or "—",
                        album=session.get("album") or "—")

            success = send_audio(
                chat_id, new_name,
                caption=caption,
                cover_path=session.get("cover"),
                title=session.get("title"),
                performer=session.get("artist"),
            )

            if success:
                # ✅ آپدیت آمار با فرمت فایل
                ext = out.suffix.lstrip(".").lower()
                store.inc_files(user["id"], ext)
                edit_msg(chat_id, msg_id, T("success", lang))
            else:
                edit_msg(chat_id, msg_id, T("upload_error", lang))

            try:
                new_name.unlink()
            except Exception:
                pass
        except Exception as e:
            log.exception("tag error")
            send(chat_id, f"❌ <code>{e}</code>")
        store.clear_session(user["id"])
        return

    if data in FIELD_KEYS:
        field, prompt_key = FIELD_KEYS[data]
        answer_cb(cb["id"])
        session["awaiting"] = field
        store.set_session(user["id"], session)
        send(chat_id, T(prompt_key, lang))
        return


# ============================================================
#                    متن و عکس
# ============================================================
def handle_text(chat_id, user, text):
    lang = get_user_lang(user["id"])
    is_admin = (user["id"] == ADMIN_ID)

    # === چک awaiting ادمین ===
    if is_admin:
        admin_awaiting = store.data.setdefault("admin_awaiting", {})
        waiting_for = admin_awaiting.get(str(user["id"]))
        if waiting_for:
            value = text.strip()
            if waiting_for == "channel_username":
                if not value.startswith("@"):
                    value = "@" + value
                save_lock_config(channel_username=value)
                admin_awaiting.pop(str(user["id"]), None)
                store.save()
                send(chat_id, T("admin_saved_channel", lang, value=value))
                return True
            if waiting_for == "channel_link":
                save_lock_config(channel_link=value)
                admin_awaiting.pop(str(user["id"]), None)
                store.save()
                send(chat_id, T("admin_saved_link", lang, value=value))
                return True

    if not is_user_member(user["id"]) and not is_admin:
        send_join_lock(chat_id, lang)
        return False

    session = store.get_session(user["id"])
    if not session or not session.get("awaiting"):
        return False
    field = session["awaiting"]
    text = text.strip()

    # === جستجو ===
    if field == "search_query":
        session.pop("awaiting", None)
        store.set_session(user["id"], session)
        send(chat_id, T("searching", lang))
        results, source = search_all_sources(text, limit=5)
        if not results:
            send(chat_id, T("search_empty", lang), edit_menu(session, lang))
            return True
        session["search_results"] = results
        session["search_source"] = source
        store.set_session(user["id"], session)
        send(chat_id, T("search_results", lang, count=len(results)), search_results_menu(results, lang))
        return True

    # === ReplayGain ===
    if field == "replaygain":
        rg = {}
        for line in text.splitlines():
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip().lower().replace(" ", "_")
                v = v.strip()
                if k in ("track_gain", "track_peak", "album_gain", "album_peak"):
                    rg[k] = v
        session["replaygain"] = rg if rg else None
        session.pop("awaiting", None)
        store.set_session(user["id"], session)
        send(chat_id, T("replaygain_saved", lang), edit_menu(session, lang))
        return True

    # === MBID ===
    if field == "mbids":
        mb = {}
        for line in text.splitlines():
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip().lower().replace(" ", "_")
                v = v.strip()
                if k in ("track_id", "album_id", "artist_id", "release_group_id"):
                    mb[k] = v
        session["mbids"] = mb if mb else None
        session.pop("awaiting", None)
        store.set_session(user["id"], session)
        send(chat_id, T("mbid_saved", lang), edit_menu(session, lang))
        return True

    # === فیلدهای معمولی ===
    session[field] = text
    session.pop("awaiting", None)
    store.set_session(user["id"], session)
    send(chat_id, T("saved_field", lang, value=text), edit_menu(session, lang))
    return True


def handle_photo(chat_id, user, msg):
    lang = get_user_lang(user["id"])
    if not is_user_member(user["id"]) and user["id"] != ADMIN_ID:
        send_join_lock(chat_id, lang)
        return

    session = store.get_session(user["id"])
    if not session:
        return
    photo = msg["photo"][-1] if msg.get("photo") else msg.get("document")
    if not photo:
        return

    path = download(photo["file_id"], f"cover_{user['id']}.jpg")
    if not path:
        send(chat_id, T("cover_error", lang))
        return

    try:
        img = Image.open(path)
        img = img.convert("RGB")
        img.thumbnail((800, 800))
        img.save(path, "JPEG", quality=88)
    except Exception as e:
        log.error(f"cover: {e}")
        send(chat_id, T("cover_error", lang))
        return

    session["cover"] = str(path)
    session.pop("awaiting", None)
    store.set_session(user["id"], session)
    send(chat_id, T("cover_saved", lang), edit_menu(session, lang))


# ============================================================
#                    Setup + Main
# ============================================================
def setup_bot():
    log.info("🚀 Setup...")
    api("deleteWebhook", drop_pending_updates=False)
    me = api("getMe")
    if not me.get("ok"):
        log.error("❌ Invalid token!")
        sys.exit(1)
    log.info(f"✅ Connected: @{me['result']['username']}")

    cfg = get_lock_config()
    log.info(f"🔒 Lock: {'ON' if cfg.get('lock_enabled') else 'OFF'} | Channel: {cfg.get('channel_username') or '—'}")

    api("setMyCommands", commands=[
        {"command": "start", "description": "🏠 شروع"},
        {"command": "help", "description": "📖 راهنما"},
        {"command": "stats", "description": "📊 آمار"},
        {"command": "admin", "description": "👑 پنل ادمین"},
    ])
    api("setChatMenuButton", menu_button={"type": "commands"})
    log.info("✅ Menu configured.")


def main():
    setup_bot()
    offset = get_offset()
    start = time.time()
    log.info(f"🤖 Running. offset={offset}")

    while time.time() - start < 355 * 60:
        try:
            r = requests.get(
                f"{API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40,
            ).json()
            if not r.get("ok"):
                log.error(f"getUpdates: {r.get('description', '?')}")
                time.sleep(10)
                continue

            for upd in r.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    if "message" in upd:
                        m = upd["message"]
                        chat_id = m["chat"]["id"]
                        user = m["from"]
                        store.add_user(user["id"], user.get("first_name", ""))

                        if "text" in m:
                            t = m["text"]
                            if t.startswith("/start"):
                                cmd_start(chat_id, user)
                            elif t.startswith("/help"):
                                cmd_help(chat_id, user)
                            elif t.startswith("/stats"):
                                cmd_stats(chat_id, user)
                            elif t.startswith("/admin"):
                                cmd_admin(chat_id, user)
                            else:
                                handle_text(chat_id, user, t)

                        elif "audio" in m or "document" in m:
                            handle_audio(chat_id, user, m)
                        elif "photo" in m:
                            handle_photo(chat_id, user, m)

                    elif "callback_query" in upd:
                        handle_callback(upd["callback_query"])
                except Exception as e:
                    log.exception(f"update error: {e}")
                save_offset(offset)

        except requests.exceptions.Timeout:
            time.sleep(5)
        except Exception as e:
            log.error(f"loop error: {e}")
            time.sleep(5)

    log.info("🛑 Finished.")


if __name__ == "__main__":
    main()
