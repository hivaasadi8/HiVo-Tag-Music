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

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
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
MB_HEADERS = {"User-Agent": "HiVoTagMusic/1.0 (github.com/hivaasadi8/MusicTaggerBot)"}


# ============================================================
#                    ترجمه‌ها (FA / EN)
# ============================================================
TEXTS = {
    "fa": {
        "btn_help": "📖 راهنمای استفاده",
        "btn_stats": "📊 آمار من",
        "btn_about": "👑 درباره ما",
        "btn_lang": "🌐 تغییر زبان",
        "btn_back": "🔙 بازگشت به ویرایش",
        "btn_cancel": "❌ انصراف از ادیت",
        "btn_preview": "👁 پیش‌نمایش و تایید نهایی",
        "btn_apply": "✨ بله، اعمال کن",
        "btn_search": "🔍 جستجوی خودکار",
        "btn_title": "🎵 اسم آهنگ",
        "btn_artist": "🎤 خواننده",
        "btn_album": "💿 آلبوم",
        "btn_year": "📅 سال انتشار",
        "btn_genre": "🎼 ژانر",
        "btn_track": "🔢 شماره ترک",
        "btn_cover": "🖼 کاور آهنگ",
        "welcome": "<b>سلام {name} عزیز 👋</b>\n\nبه <b>HiVo Tag Music</b> خوش آمدی 🎧\nمن می‌تونم فایل موزیکت رو به یه اثر حرفه‌ای تبدیل کنم.\n\n<blockquote><b>✨ قابلیت‌های من:</b>\n├ ویرایش کامل تگ‌های صوتی\n├ افزودن کاور با کیفیت بالا\n├ 🔍 جستجوی چندمنبعی (iTunes + YouTube Music + MusicBrainz + SoundCloud)\n├ 🌐 پشتیبانی چندزبانه (فارسی/انگلیسی)\n└ پردازش سریع و امن</blockquote>\n\n<i>برای شروع، فایل موزیکت رو بفرست 👇</i>",
        "help": "<b>📖 راهنمای کامل استفاده</b>\n\n<blockquote><b>مرحله ۱:</b> فایل موزیک رو بفرست\n<b>مرحله ۲:</b> روی گزینه‌ها بزن یا از جستجوی خودکار استفاده کن\n<b>مرحله ۳:</b> برای کاور، عکس رو بفرست\n<b>مرحله ۴:</b> پیش‌نمایش رو ببین و تایید کن\n<b>مرحله ۵:</b> فایل نهایی رو دریافت کن</blockquote>\n\n<b>💡 نکات:</b>\n├ حداکثر حجم فایل: <b>20MB</b>\n├ 🔍 جستجوی چندمنبعی برای پیدا کردن اطلاعات\n├ 🌐 با دکمه زبان، بین فارسی و انگلیسی سوییچ کن\n└ همه تغییرات خودکار ذخیره می‌شه",
        "about": "<b>👑 درباره HiVo Tag Music</b>\n\n<blockquote>این ربات برای ویرایش حرفه‌ای تگ‌های موزیک طراحی شده و کاملاً رایگان است.</blockquote>\n\n<b>🔧 تکنولوژی:</b>\n├ Python + Telegram Bot API\n├ موتور Mutagen\n├ 🔍 iTunes + YouTube Music + MusicBrainz + SoundCloud\n└ GitHub Actions (میزبانی)\n\n<i>ساخته شده با ❤️ برای موزیک‌دوستان</i>",
        "stats": "<b>📊 آمار و اطلاعات</b>\n\n<blockquote><b>🌍 آمار کلی:</b>\n├ کاربران: <b>{users}</b>\n└ فایل‌ها: <b>{files}</b></blockquote>\n<blockquote><b>👤 آمار شما:</b>\n├ نام: <b>{name}</b>\n├ زبان: <b>{lang}</b>\n└ فایل‌های شما: <b>{my_files}</b></blockquote>",
        "file_too_large": "<b>❌ فایل بزرگ‌تر از 20MB است</b>\n\n<i>تلگرام اجازه دانلود فایل‌های بزرگ‌تر رو به ربات‌ها نمی‌ده.</i>",
        "downloading": "📥 <b>در حال دریافت فایل...</b>\n<i>لطفاً صبر کن</i>",
        "download_error": "❌ <b>خطا در دریافت فایل</b>\nدوباره تلاش کن.",
        "file_received": "<b>✅ فایل با موفقیت دریافت شد!</b>\n\n{header}\n\n<i>حالا گزینه‌ها رو انتخاب کن یا از جستجوی خودکار استفاده کن 👇</i>",
        "search_prompt": "🔍 <b>جستجوی خودکار در منابع موزیک</b>\n\n<i>اسم آهنگ و خواننده رو بنویس تا اطلاعات و کاور رو از بین iTunes، YouTube Music، MusicBrainz و SoundCloud پیدا کنم.</i>\n\n<b>مثال:</b> <code>Shape of You Ed Sheeran</code>",
        "searching": "🔄 <b>در حال جستجو در منابع...</b>\n<i>iTunes → YouTube Music → MusicBrainz → SoundCloud</i>",
        "search_empty": "❌ <b>متاسفانه اطلاعاتی پیدا نشد!</b>\n\n<i>می‌تونی اطلاعات رو دستی وارد کنی. روی دکمه‌های زیر بزن و هر فیلد رو پر کن 👇</i>",
        "search_results": "🎯 <b>{count} نتیجه پیدا شد</b>\n\n<i>روی نتیجه مورد نظرت بزن 👇</i>",
        "search_applied": "✅ <b>اطلاعات با موفقیت اعمال شد!</b>\n\n<i>منبع: {source}</i>\n\n<i>می‌تونی تغییرات دیگه‌ای بدی یا پیش‌نمایش رو بزنی.</i>",
        "preview": "<b>👁 پیش‌نمایش تغییرات نهایی</b>\n\n<blockquote>🎵 <b>اسم آهنگ:</b> <code>{title}</code>\n🎤 <b>خواننده:</b> <code>{artist}</code>\n💿 <b>آلبوم:</b> <code>{album}</code>\n📅 <b>سال:</b> <code>{year}</code>\n🎼 <b>ژانر:</b> <code>{genre}</code>\n🔢 <b>شماره ترک:</b> <code>{track}</code>\n🖼 <b>کاور:</b> {cover}</blockquote>\n\n<i>آیا از اعمال مطمئنی؟</i>",
        "cover_yes": "✅ تنظیم شده",
        "cover_no": "❌ تنظیم نشده",
        "applying": "⏳ <b>[۱/۳] در حال اعمال تگ‌ها...</b>\n<i>موتور Mutagen در حال کاره</i>",
        "uploading": "✅ <b>[۲/۳] تگ‌ها اعمال شد</b>\n\n📤 <b>[۳/۳] در حال آپلود فایل...</b>\n<blockquote>حجم: <b>{size}</b>\n<i>بسته به سرعت گیت‌هاب، ۱ تا ۲ دقیقه طول می‌کشه</i></blockquote>",
        "success": "✨ <b>عملیات با موفقیت به پایان رسید!</b>\n\n<i>ممنون که از HiVo Tag Music استفاده کردی 🎧</i>",
        "upload_error": "❌ <b>خطا در آپلود فایل به تلگرام</b>\n\n<i>دوباره تلاش کن.</i>",
        "cancelled": "❌ <b>عملیات لغو شد</b>\n\n<i>هر وقت خواستی، فایل جدید بفرست.</i>",
        "session_expired": "⚠️ سشن منقضی شده، فایل رو دوباره بفرست",
        "saved_field": "✅ <b>ثبت شد:</b> <code>{value}</code>\n\n<i>تغییرات دیگه‌ای اعمال کن یا پیش‌نمایش رو بزن 👇</i>",
        "cover_saved": "🖼 <b>کاور با موفقیت ثبت شد!</b>\n\n<i>حالا تغییرات دیگه‌ای بده یا پیش‌نمایش رو بزن 👇</i>",
        "cover_error": "❌ خطا در پردازش عکس کاور",
        "lang_changed": "✅ <b>زبان با موفقیت تغییر کرد</b>\n\n🌐 زبان فعلی: <b>فارسی</b>",
        "lang_menu": "🌐 <b>زبان مورد نظرت رو انتخاب کن:</b>",
        "caption_success": "✅ <b>تگ‌ها با موفقیت اعمال شد!</b>\n\n<blockquote>🎵 <b>{title}</b>\n🎤 {artist}\n💿 {album}</blockquote>\n\n<i>HiVo Tag Music 🎧</i>",
        "prompt_title": "🎵 <b>اسم جدید آهنگ:</b>\n\n<i>مثال: Shape of You</i>",
        "prompt_artist": "🎤 <b>اسم جدید خواننده:</b>\n\n<i>مثال: Ed Sheeran</i>",
        "prompt_album": "💿 <b>اسم جدید آلبوم:</b>\n\n<i>مثال: Divide</i>",
        "prompt_year": "📅 <b>سال انتشار:</b>\n\n<i>مثال: 2017</i>",
        "prompt_genre": "🎼 <b>ژانر موزیک:</b>\n\n<i>مثال: Pop, Rock</i>",
        "prompt_track": "🔢 <b>شماره ترک:</b>\n\n<i>مثال: 1</i>",
        "prompt_cover": "🖼 <b>عکس کاور رو بفرست</b>\n\n<i>به‌صورت Photo یا Document</i>",
        "file_header": "<blockquote><b>🎧 فایل در حال ویرایش</b>\n├ نام: <code>{name}</code>\n├ حجم: <code>{size}</code>\n└ تغییرات: <b>{count}</b> مورد</blockquote>",
    },
    "en": {
        "btn_help": "📖 Help",
        "btn_stats": "📊 My Stats",
        "btn_about": "👑 About",
        "btn_lang": "🌐 Change Language",
        "btn_back": "🔙 Back to Edit",
        "btn_cancel": "❌ Cancel",
        "btn_preview": "👁 Preview & Confirm",
        "btn_apply": "✨ Yes, Apply",
        "btn_search": "🔍 Auto Search",
        "btn_title": "🎵 Title",
        "btn_artist": "🎤 Artist",
        "btn_album": "💿 Album",
        "btn_year": "📅 Year",
        "btn_genre": "🎼 Genre",
        "btn_track": "🔢 Track No.",
        "btn_cover": "🖼 Cover Art",
        "welcome": "<b>Hello {name} 👋</b>\n\nWelcome to <b>HiVo Tag Music</b> 🎧\nI can turn your music file into a professional piece.\n\n<blockquote><b>✨ Features:</b>\n├ Full audio tag editing\n├ High-quality cover art\n├ 🔍 Multi-source search (iTunes + YouTube Music + MusicBrainz + SoundCloud)\n├ 🌐 Multi-language (FA/EN)\n└ Fast & secure processing</blockquote>\n\n<i>To start, just send your music file 👇</i>",
        "help": "<b>📖 Complete Guide</b>\n\n<blockquote><b>Step 1:</b> Send your music file\n<b>Step 2:</b> Tap options or use auto-search\n<b>Step 3:</b> Send cover as photo\n<b>Step 4:</b> Preview & confirm\n<b>Step 5:</b> Receive edited file</blockquote>\n\n<b>💡 Tips:</b>\n├ Max file size: <b>20MB</b>\n├ 🔍 Multi-source search for info\n├ 🌐 Toggle FA/EN anytime\n└ Changes are saved automatically",
        "about": "<b>👑 About HiVo Tag Music</b>\n\n<blockquote>A bot specially designed for professional music tag editing. Completely free.</blockquote>\n\n<b>🔧 Tech Stack:</b>\n├ Python + Telegram Bot API\n├ Mutagen engine\n├ 🔍 iTunes + YouTube Music + MusicBrainz + SoundCloud\n└ Hosted on GitHub Actions\n\n<i>Made with ❤️ for music lovers</i>",
        "stats": "<b>📊 Stats & Info</b>\n\n<blockquote><b>🌍 Global:</b>\n├ Users: <b>{users}</b>\n└ Files: <b>{files}</b></blockquote>\n<blockquote><b>👤 You:</b>\n├ Name: <b>{name}</b>\n├ Language: <b>{lang}</b>\n└ Your files: <b>{my_files}</b></blockquote>",
        "file_too_large": "<b>❌ File larger than 20MB</b>\n\n<i>Telegram doesn't allow bots to download larger files.</i>",
        "downloading": "📥 <b>Downloading file...</b>\n<i>Please wait</i>",
        "download_error": "❌ <b>Download failed</b>\nPlease try again.",
        "file_received": "<b>✅ File received!</b>\n\n{header}\n\n<i>Tap options or use auto-search 👇</i>",
        "search_prompt": "🔍 <b>Multi-Source Auto Search</b>\n\n<i>Type the song name and artist to fetch info and cover from iTunes, YouTube Music, MusicBrainz and SoundCloud.</i>\n\n<b>Example:</b> <code>Shape of You Ed Sheeran</code>",
        "searching": "🔄 <b>Searching sources...</b>\n<i>iTunes → YouTube Music → MusicBrainz → SoundCloud</i>",
        "search_empty": "❌ <b>No results found!</b>\n\n<i>You can enter info manually. Tap the buttons below to fill each field 👇</i>",
        "search_results": "🎯 <b>{count} results found</b>\n\n<i>Tap the one you want 👇</i>",
        "search_applied": "✅ <b>Info applied!</b>\n\n<i>Source: {source}</i>\n\n<i>Make more changes or preview.</i>",
        "preview": "<b>👁 Final Preview</b>\n\n<blockquote>🎵 <b>Title:</b> <code>{title}</code>\n🎤 <b>Artist:</b> <code>{artist}</code>\n💿 <b>Album:</b> <code>{album}</code>\n📅 <b>Year:</b> <code>{year}</code>\n🎼 <b>Genre:</b> <code>{genre}</code>\n🔢 <b>Track:</b> <code>{track}</code>\n🖼 <b>Cover:</b> {cover}</blockquote>\n\n<i>Are you sure?</i>",
        "cover_yes": "✅ Set",
        "cover_no": "❌ Not set",
        "applying": "⏳ <b>[1/3] Applying tags...</b>\n<i>Mutagen engine is working</i>",
        "uploading": "✅ <b>[2/3] Tags applied</b>\n\n📤 <b>[3/3] Uploading file...</b>\n<blockquote>Size: <b>{size}</b>\n<i>May take 1-2 min depending on GitHub speed</i></blockquote>",
        "success": "✨ <b>Operation completed!</b>\n\n<i>Thanks for using HiVo Tag Music 🎧</i>",
        "upload_error": "❌ <b>Upload failed</b>\n\n<i>Please try again.</i>",
        "cancelled": "❌ <b>Cancelled</b>\n\n<i>Send a new file anytime.</i>",
        "session_expired": "⚠️ Session expired, send the file again",
        "saved_field": "✅ <b>Saved:</b> <code>{value}</code>\n\n<i>Make more changes or preview 👇</i>",
        "cover_saved": "🖼 <b>Cover saved!</b>\n\n<i>Make more changes or preview 👇</i>",
        "cover_error": "❌ Cover processing failed",
        "lang_changed": "✅ <b>Language changed</b>\n\n🌐 Current: <b>English</b>",
        "lang_menu": "🌐 <b>Choose your language:</b>",
        "caption_success": "✅ <b>Tags applied successfully!</b>\n\n<blockquote>🎵 <b>{title}</b>\n🎤 {artist}\n💿 {album}</blockquote>\n\n<i>HiVo Tag Music 🎧</i>",
        "prompt_title": "🎵 <b>New title:</b>\n\n<i>e.g. Shape of You</i>",
        "prompt_artist": "🎤 <b>New artist:</b>\n\n<i>e.g. Ed Sheeran</i>",
        "prompt_album": "💿 <b>New album:</b>\n\n<i>e.g. Divide</i>",
        "prompt_year": "📅 <b>Release year:</b>\n\n<i>e.g. 2017</i>",
        "prompt_genre": "🎼 <b>Genre:</b>\n\n<i>e.g. Pop, Rock</i>",
        "prompt_track": "🔢 <b>Track number:</b>\n\n<i>e.g. 1</i>",
        "prompt_cover": "🖼 <b>Send cover image</b>\n\n<i>As Photo or Document</i>",
        "file_header": "<blockquote><b>🎧 File being edited</b>\n├ Name: <code>{name}</code>\n├ Size: <code>{size}</code>\n└ Changes: <b>{count}</b></blockquote>",
    },
}


def T(key, lang="fa", **kwargs):
    text = TEXTS.get(lang, TEXTS["fa"]).get(key, key)
    try:
        return text.format(**kwargs) if kwargs else text
    except Exception:
        return text


def get_user_lang(user_id):
    u = store.data["users"].get(str(user_id), {})
    return u.get("lang", "fa")


def set_user_lang(user_id, lang):
    uid = str(user_id)
    if uid in store.data["users"]:
        store.data["users"][uid]["lang"] = lang
        store.save()


def human_size(b):
    b = float(b)
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def short_name(name, maxlen=32):
    return name if len(name) <= maxlen else name[:maxlen - 3] + "..."


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


def send_audio(chat_id, path, caption="", cover_path=None):
    for attempt in range(3):
        files = {}
        try:
            log.info(f"📤 Upload try {attempt+1} ({human_size(Path(path).stat().st_size)})")
            files = {"audio": open(path, "rb")}
            data = {
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
            }
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
                log.info("✅ Sent.")
                return True
            log.error(f"Send error: {r.text}")
        except Exception as e:
            log.error(f"❌ Upload error (try {attempt+1}): {e}")
            for f in files.values():
                try:
                    f.close()
                except Exception:
                    pass
        time.sleep(2)
    return False


# ============================================================
#            جستجوی چندمنبعی (Multi-Source Search)
# ============================================================

def search_itunes(query, limit=5):
    url = "https://itunes.apple.com/search"
    params = {"term": query, "media": "music", "entity": "song", "limit": limit}
    try:
        r = session_http.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return []
        out = []
        for item in r.json().get("results", [])[:limit]:
            artwork = item.get("artworkUrl100", "")
            if artwork:
                artwork = artwork.replace("100x100", "1000x1000")
            out.append({
                "title": item.get("trackName", "Unknown"),
                "artist": item.get("artistName", "Unknown"),
                "album": item.get("collectionName", ""),
                "year": (item.get("releaseDate", "") or "")[:4],
                "genre": item.get("primaryGenreName", ""),
                "release_id": item.get("collectionId", ""),
                "artwork_url": artwork,
                "length": item.get("trackTimeMillis", 0),
            })
        return out
    except Exception as e:
        log.error(f"iTunes error: {e}")
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
            year = ""
            if album.get("year"):
                year = str(album["year"])
            thumbnails = item.get("thumbnails", [])
            artwork = thumbnails[-1]["url"] if thumbnails else ""
            out.append({
                "title": item.get("title", "Unknown"),
                "artist": artist,
                "album": album_name,
                "year": year,
                "genre": "",
                "release_id": item.get("videoId", ""),
                "artwork_url": artwork,
                "length": item.get("duration_seconds", 0),
            })
        return out
    except ImportError:
        log.warning("ytmusicapi نصب نیست.")
        return []
    except Exception as e:
        log.error(f"YouTube Music error: {e}")
        return []


def search_musicbrainz(query, limit=5):
    url = "https://musicbrainz.org/ws/2/recording/"
    params = {"query": query, "fmt": "json", "limit": limit}
    try:
        r = session_http.get(url, params=params, headers=MB_HEADERS, timeout=20)
        if r.status_code != 200:
            return []
        out = []
        for rec in r.json().get("recordings", [])[:limit]:
            artist = ""
            if rec.get("artist-credit"):
                artist = rec["artist-credit"][0].get("name", "")
            releases = rec.get("releases", [])
            release = releases[0] if releases else {}
            tags = rec.get("tags", [])
            genre = tags[0]["name"] if tags else ""
            out.append({
                "title": rec.get("title", "Unknown"),
                "artist": artist or "Unknown",
                "album": release.get("title", ""),
                "year": (release.get("date", "") or "")[:4],
                "genre": genre,
                "release_id": release.get("id", ""),
                "artwork_url": "",
                "length": rec.get("length", 0),
            })
        return out
    except Exception as e:
        log.error(f"MusicBrainz error: {e}")
        return []


def search_soundcloud(query, limit=5):
    return []


def search_all_sources(query, limit=5):
    log.info(f"🔍 Searching all sources: {query}")
    for name, fn in [("iTunes", search_itunes), ("YouTube Music", search_ytmusic),
                     ("MusicBrainz", search_musicbrainz), ("SoundCloud", search_soundcloud)]:
        results = fn(query, limit)
        if results:
            log.info(f"✅ {name} found {len(results)}")
            return results, name
    log.info("❌ No results.")
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
        log.error(f"Cover fetch error: {e}")
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
    name = session.get("orig_name", "---")
    name = short_name(name, 30)
    try:
        size = human_size(Path(session["file"]).stat().st_size) if Path(session["file"]).exists() else "---"
    except Exception:
        size = "---"
    count = sum(1 for f in ["title", "artist", "album", "year", "genre", "track"] if session.get(f))
    if session.get("cover"):
        count += 1
    return T("file_header", lang, name=name, size=size, count=count)


def edit_menu(session, lang="fa"):
    def btn(field, emoji, key):
        mark = "✅" if session.get(field) else "◽️"
        return {"text": f"{emoji} {T(key, lang)} {mark}", "callback_data": f"f_{field}"}

    return [
        [btn("title", "🎵", "btn_title"), btn("artist", "🎤", "btn_artist")],
        [btn("album", "💿", "btn_album"), btn("year", "📅", "btn_year")],
        [btn("genre", "🎼", "btn_genre"), btn("track", "🔢", "btn_track")],
        [btn("cover", "🖼", "btn_cover")],
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
    text = T("welcome", lang, name=user.get("first_name", ""))
    banner = Path("banner.jpg")
    if banner.exists():
        send_photo_file(chat_id, str(banner), text, main_menu(lang))
    else:
        send(chat_id, text, main_menu(lang))


def cmd_help(chat_id, user):
    lang = get_user_lang(user["id"])
    send(chat_id, T("help", lang), main_menu(lang))


def cmd_about(chat_id, user):
    lang = get_user_lang(user["id"])
    send(chat_id, T("about", lang), main_menu(lang))


def cmd_stats(chat_id, user):
    lang = get_user_lang(user["id"])
    s = store.get_stats()
    me = store.data["users"].get(str(user["id"]), {})
    lang_name = "فارسی" if lang == "fa" else "English"
    text = T("stats", lang,
             users=s["users"], files=s["files"],
             name=me.get("name", "---"),
             my_files=me.get("files", 0),
             lang=lang_name)
    send(chat_id, text, main_menu(lang))


def handle_audio(chat_id, user, msg):
    lang = get_user_lang(user["id"])
    audio = msg.get("audio") or msg.get("document")
    if not audio:
        return
    size = audio.get("file_size", 0)
    if size > 20 * 1024 * 1024:
        send(chat_id, T("file_too_large", lang), main_menu(lang))
        return

    ext = ".mp3"
    if audio.get("file_name"):
        ext = Path(audio["file_name"]).suffix or ".mp3"

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
        "album": None,
        "year": None,
        "genre": None,
        "track": None,
        "cover": None,
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
        text = T("file_received", lang, header=session_header(session, lang))
        edit_msg(chat_id, msg_id, text, edit_menu(session, lang))
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
        session["title"] = r["title"]
        session["artist"] = r["artist"]
        session["album"] = r["album"]
        session["year"] = r["year"]
        if r.get("genre"):
            session["genre"] = r["genre"]

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
                log.error(f"cover process error: {e}")

        store.set_session(user["id"], session)
        source = session.get("search_source", "")
        text = f"{T('search_applied', lang, source=source)}\n\n{session_header(session, lang)}"
        edit_msg(chat_id, msg_id, text, edit_menu(session, lang))
        return

    if data == "preview":
        answer_cb(cb["id"])
        cover_status = T("cover_yes", lang) if session.get("cover") else T("cover_no", lang)
        text = T("preview", lang,
                 title=session.get("title") or "---",
                 artist=session.get("artist") or "---",
                 album=session.get("album") or "---",
                 year=session.get("year") or "---",
                 genre=session.get("genre") or "---",
                 track=session.get("track") or "---",
                 cover=cover_status)
        edit_msg(chat_id, msg_id, text, preview_menu(lang))
        return

    if data == "apply":
        answer_cb(cb["id"], "⏳")
        edit_msg(chat_id, msg_id, T("applying", lang))
        try:
            edit_tags(
                file_path=session["file"],
                title=session.get("title"),
                artist=session.get("artist"),
                album=session.get("album"),
                year=session.get("year"),
                genre=session.get("genre"),
                track=session.get("track"),
                cover_path=session.get("cover"),
            )
            out = Path(session["file"])
            # ✅ اسم فایل حفظ می‌شه، فقط داخل پوشه‌ی مخصوص همون کاربر ذخیره می‌شه
            user_temp = TEMP / str(user["id"])
            user_temp.mkdir(exist_ok=True)
            original_name = session.get("orig_name") or ("music" + out.suffix)
            new_name = user_temp / original_name
            out.rename(new_name)

            size_str = human_size(new_name.stat().st_size)
            edit_msg(chat_id, msg_id, T("uploading", lang, size=size_str))

            caption = T("caption_success", lang,
                        title=session.get("title") or "Music",
                        artist=session.get("artist") or "---",
                        album=session.get("album") or "---")

            success = send_audio(chat_id, new_name, caption=caption, cover_path=session.get("cover"))

            if success:
                store.inc_files(user["id"])
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
    session = store.get_session(user["id"])
    if not session or not session.get("awaiting"):
        return False
    field = session["awaiting"]
    text = text.strip()

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

    session[field] = text
    session.pop("awaiting", None)
    store.set_session(user["id"], session)
    send(chat_id, T("saved_field", lang, value=text), edit_menu(session, lang))
    return True


def handle_photo(chat_id, user, msg):
    lang = get_user_lang(user["id"])
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
        log.error(f"cover error: {e}")
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
    api("setMyCommands", commands=[
        {"command": "start", "description": "🏠 / شروع"},
        {"command": "help", "description": "📖 / راهنما"},
        {"command": "stats", "description": "📊 / آمار"},
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
                log.info(f"📩 Update {offset}")
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
                            elif t.startswith("/admin") and user["id"] == ADMIN_ID:
                                s = store.get_stats()
                                send(chat_id, f"👑 <b>Admin</b>\n\n👥 {s['users']}\n🎵 {s['files']}")
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
