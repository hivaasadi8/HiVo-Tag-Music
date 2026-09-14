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

# --- تنظیم لاگ ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
if not TOKEN:
    log.error("❌ خطا: متغیر TELEGRAM_TOKEN پیدا نشد!")
    sys.exit(1)

ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
API = f"https://api.telegram.org/bot{TOKEN}"
OFFSET_FILE = Path("offset.json")
TEMP = Path("tmp")
TEMP.mkdir(exist_ok=True)
store = Store("state.json")
session_http = requests.Session()


# ============================================================
#                    توابع کمکی
# ============================================================
def human_size(b):
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def human_duration(seconds):
    if not seconds:
        return "---"
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


# ============================================================
#                    توابع ارتباط با تلگرام
# ============================================================
def api(method, **params):
    try:
        r = session_http.post(f"{API}/{method}", json=params, timeout=60)
        res = r.json()
        if not res.get("ok"):
            log.error(f"⚠️ خطای API در {method}: {res}")
        return res
    except Exception as e:
        log.error(f"❌ خطای شبکه در {method}: {e}")
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
        log.error(f"خطا در ارسال عکس: {e}")


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
        log.error(f"خطا در دانلود: {e}")
        return None


def send_audio(chat_id, path, caption="", cover_path=None):
    """ارسال فایل با تلاش مجدد"""
    for attempt in range(3):
        files = {}
        try:
            log.info(f"📤 تلاش {attempt+1} برای آپلود ({human_size(Path(path).stat().st_size)})...")
            files = {"audio": open(path, "rb")}
            data = {"chat_id": chat_id, "caption": caption}

            if cover_path and Path(cover_path).exists():
                thumb_path = TEMP / "thumb.jpg"
                img = Image.open(cover_path)
                img = img.convert("RGB")
                img.thumbnail((320, 320))
                img.save(thumb_path, "JPEG", quality=80)
                files["thumb"] = open(thumb_path, "rb")

            r = session_http.post(f"{API}/sendAudio", data=data, files=files, timeout=300)

            for f in files.values():
                try:
                    f.close()
                except Exception:
                    pass

            if r.status_code == 200:
                log.info("✅ فایل ارسال شد.")
                return True
            log.error(f"خطا در ارسال: {r.text}")
        except Exception as e:
            log.error(f"❌ خطای شبکه در آپلود (تلاش {attempt+1}): {e}")
            for f in files.values():
                try:
                    f.close()
                except Exception:
                    pass
        time.sleep(2)
    return False


# ============================================================
#                    منوها و کارت‌ها
# ============================================================
def main_menu():
    return [
        [{"text": "🎵 راهنمای استفاده", "callback_data": "help"}],
        [{"text": "📊 آمار من", "callback_data": "my_stats"},
         {"text": "👑 درباره ما", "callback_data": "about"}],
    ]


def session_header(session):
    """هدیه کارت اطلاعات فایل - طراحی لوکس"""
    name = session.get("orig_name", "---")
    if len(name) > 30:
        name = name[:27] + "..."
    size = human_size(Path(session["file"]).stat().st_size) if Path(session["file"]).exists() else "---"
    
    filled = sum(1 for f in ["title", "artist", "album", "year", "genre", "track"] if session.get(f))
    if session.get("cover"):
        filled += 1
    
    return (
        f"<blockquote>"
        f"<b>🎧 فایل در حال ویرایش</b>\n"
        f"├ نام: <code>{name}</code>\n"
        f"├ حجم: <code>{size}</code>\n"
        f"└ تغییرات: <b>{filled}</b> مورد"
        f"</blockquote>"
    )


def edit_menu(session):
    """منوی ادیت با طراحی لوکس و نشانگر وضعیت"""
    def btn(field, emoji, label):
        mark = "✅" if session.get(field) else "◽️"
        return {"text": f"{emoji} {label} {mark}", "callback_data": f"f_{field}"}

    return [
        [btn("title", "🎵", "اسم آهنگ"), btn("artist", "🎤", "خواننده")],
        [btn("album", "💿", "آلبوم"), btn("year", "📅", "سال انتشار")],
        [btn("genre", "🎼", "ژانر"), btn("track", "🔢", "شماره ترک")],
        [btn("cover", "🖼", "کاور آهنگ")],
        [{"text": "👁 پیش‌نمایش و تایید نهایی", "callback_data": "preview"}],
        [{"text": "❌ انصراف از ادیت", "callback_data": "cancel"}],
    ]


def preview_menu():
    return [
        [{"text": "✨ بله، اعمال کن", "callback_data": "apply"}],
        [{"text": "🔙 بازگشت به ویرایش", "callback_data": "back"}],
        [{"text": "❌ انصراف", "callback_data": "cancel"}],
    ]


# ============================================================
#                    هندلرهای دستورات
# ============================================================
def cmd_start(chat_id, user):
    store.add_user(user["id"], user.get("first_name", ""))
    text = (
        f"<b>سلام {user.get('first_name','')} عزیز 👋</b>\n\n"
        f"به <b>HiVo Tag Music</b> خوش آمدی 🎧\n"
        f"من می‌تونم فایل موزیکت رو به یه اثر حرفه‌ای تبدیل کنم.\n\n"
        f"<blockquote>"
        f"<b>✨ قابلیت‌های من:</b>\n"
        f"├ ویرایش کامل تگ‌های صوتی\n"
        f"├ افزودن کاور با کیفیت بالا\n"
        f"├ پشتیبانی از MP3, FLAC, M4A\n"
        f"└ پردازش سریع و امن"
        f"</blockquote>\n\n"
        f"<i>برای شروع، فقط فایل موزیکت رو بفرست 👇</i>"
    )
    banner = Path("banner.jpg")
    if banner.exists():
        send_photo_file(chat_id, str(banner), text, main_menu())
    else:
        send(chat_id, text, main_menu())


def cmd_help(chat_id):
    text = (
        f"<b>📖 راهنمای کامل استفاده</b>\n\n"
        f"<blockquote>"
        f"<b>مرحله ۱:</b> فایل موزیک رو بفرست\n"
        f"<b>مرحله ۲:</b> روی گزینه‌ها بزن و مقدار جدید رو تایپ کن\n"
        f"<b>مرحله ۳:</b> برای کاور، عکس رو به‌صورت Photo بفرست\n"
        f"<b>مرحله ۴:</b> پیش‌نمایش رو ببین و تایید کن\n"
        f"<b>مرحله ۵:</b> فایل نهایی رو دریافت کن"
        f"</blockquote>\n\n"
        f"<b>💡 نکات مهم:</b>\n"
        f"├ حداکثر حجم فایل: <b>20MB</b>\n"
        f"├ سرعت آپلود بسته به حجم فایل متغیره\n"
        f"└ همه تغییرات به‌صورت خودکار ذخیره می‌شه\n\n"
        f"<i>اگه سوالی داری، به ادمین پیام بده 💬</i>"
    )
    send(chat_id, text, main_menu())


def cmd_about(chat_id):
    text = (
        f"<b>👑 درباره HiVo Tag Music</b>\n\n"
        f"<blockquote>"
        f"این ربات به‌صورت اختصاصی برای ویرایش حرفه‌ای\n"
        f"تگ‌های موزیک طراحی شده و کاملاً رایگان است.\n"
        f"</blockquote>\n\n"
        f"<b>🔧 تکنولوژی:</b>\n"
        f"├ Python + Telegram Bot API\n"
        f"├ موتور پردازش Mutagen\n"
        f"└ میزبانی روی GitHub Actions\n\n"
        f"<i>ساخته شده با ❤️ برای موزیک‌دوستان</i>"
    )
    send(chat_id, text, main_menu())


def cmd_stats(chat_id, user_id):
    s = store.get_stats()
    me = store.data["users"].get(str(user_id), {})
    text = (
        f"<b>📊 آمار و اطلاعات</b>\n\n"
        f"<blockquote>"
        f"<b>🌍 آمار کلی ربات:</b>\n"
        f"├ کاربران: <b>{s['users']}</b>\n"
        f"└ فایل‌های پردازش‌شده: <b>{s['files']}</b>"
        f"</blockquote>\n"
        f"<blockquote>"
        f"<b>👤 آمار شخصی شما:</b>\n"
        f"├ نام: <b>{me.get('name', '---')}</b>\n"
        f"└ فایل‌های شما: <b>{me.get('files', 0)}</b>"
        f"</blockquote>"
    )
    send(chat_id, text, main_menu())


# ============================================================
#                    هندلر فایل صوتی
# ============================================================
def handle_audio(chat_id, user, msg):
    audio = msg.get("audio") or msg.get("document")
    if not audio:
        return
    size = audio.get("file_size", 0)
    if size > 20 * 1024 * 1024:
        send(
            chat_id,
            "<b>❌ فایل بزرگ‌تر از 20MB است</b>\n\n"
            "<i>متاسفانه تلگرام اجازه دانلود فایل‌های بزرگ‌تر رو به ربات‌ها نمی‌ده.</i>",
        )
        return

    ext = ".mp3"
    if audio.get("file_name"):
        ext = Path(audio["file_name"]).suffix or ".mp3"

    tmp_name = f"{user['id']}_{int(time.time())}{ext}"
    send(chat_id, "📥 <b>در حال دریافت فایل...</b>\n<i>لطفاً صبر کن</i>")

    path = download(audio["file_id"], tmp_name)
    if not path:
        send(chat_id, "❌ <b>خطا در دریافت فایل</b>\nلطفاً دوباره تلاش کن.")
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

    text = (
        f"<b>✅ فایل با موفقیت دریافت شد!</b>\n\n"
        f"{session_header(session)}\n\n"
        f"<i>حالا روی گزینه‌هایی که می‌خوای عوض کنی بزن 👇</i>"
    )
    send(chat_id, text, edit_menu(session))


FIELD_NAMES = {
    "f_title": ("title", "🎵 <b>اسم جدید آهنگ</b> رو بنویس:\n\n<i>مثال: Shape of You</i>"),
    "f_artist": ("artist", "🎤 <b>اسم جدید خواننده</b> رو بنویس:\n\n<i>مثال: Ed Sheeran</i>"),
    "f_album": ("album", "💿 <b>اسم جدید آلبوم</b> رو بنویس:\n\n<i>مثال: Divide</i>"),
    "f_year": ("year", "📅 <b>سال انتشار</b> رو بنویس:\n\n<i>مثال: 2017</i>"),
    "f_genre": ("genre", "🎼 <b>ژانر موزیک</b> رو بنویس:\n\n<i>مثال: Pop, Rock, Hip-Hop</i>"),
    "f_track": ("track", "🔢 <b>شماره ترک</b> رو بنویس:\n\n<i>مثال: 1</i>"),
    "f_cover": ("cover", "🖼 <b>عکس کاور</b> رو بفرست\n\n<i>به‌صورت Photo یا Document</i>"),
}


# ============================================================
#                    هندلر دکمه‌ها
# ============================================================
def handle_callback(cb):
    chat_id = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]
    user = cb["from"]
    data = cb["data"]

    if data == "help":
        answer_cb(cb["id"])
        cmd_help(chat_id)
        return
    if data == "my_stats":
        answer_cb(cb["id"])
        cmd_stats(chat_id, user["id"])
        return
    if data == "about":
        answer_cb(cb["id"])
        cmd_about(chat_id)
        return
    if data == "cancel":
        answer_cb(cb["id"], "❌ لغو شد")
        store.clear_session(user["id"])
        edit_msg(chat_id, msg_id, "❌ <b>عملیات لغو شد</b>\n\n<i>هر وقت خواستی، فایل جدید بفرست.</i>")
        return

    session = store.get_session(user["id"])
    if not session:
        answer_cb(cb["id"], "⚠️ سشن منقضی شده، فایل رو دوباره بفرست")
        return

    if data == "back":
        answer_cb(cb["id"])
        edit_msg(
            chat_id,
            msg_id,
            f"<b>🎧 فایل در حال ویرایش</b>\n\n{session_header(session)}\n\n<i>گزینه‌های مورد نظر رو انتخاب کن 👇</i>",
            edit_menu(session),
        )
        return

    if data == "preview":
        answer_cb(cb["id"])
        p = f"<b>👁 پیش‌نمایش تغییرات نهایی</b>\n\n"
        p += "<blockquote>"
        p += f"🎵 <b>اسم آهنگ:</b> <code>{session.get('title') or '---'}</code>\n"
        p += f"🎤 <b>خواننده:</b> <code>{session.get('artist') or '---'}</code>\n"
        p += f"💿 <b>آلبوم:</b> <code>{session.get('album') or '---'}</code>\n"
        p += f"📅 <b>سال:</b> <code>{session.get('year') or '---'}</code>\n"
        p += f"🎼 <b>ژانر:</b> <code>{session.get('genre') or '---'}</code>\n"
        p += f"🔢 <b>شماره ترک:</b> <code>{session.get('track') or '---'}</code>\n"
        p += f"🖼 <b>کاور:</b> {'✅ تنظیم شده' if session.get('cover') else '❌ تنظیم نشده'}"
        p += "</blockquote>\n\n"
        p += "<i>آیا از اعمال این تغییرات اطمینان داری؟</i>"
        edit_msg(chat_id, msg_id, p, preview_menu())
        return

    if data == "apply":
        answer_cb(cb["id"], "⏳ در حال پردازش...")

        # مرحله ۱: ادیت تگ‌ها
        edit_msg(chat_id, msg_id, "⏳ <b>[۱/۳] در حال اعمال تگ‌ها...</b>\n<i>موتور Mutagen در حال کاره</i>")
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
            new_name = TEMP / f"tagged_{session['orig_name']}"
            out.rename(new_name)

            # مرحله ۲: آپلود
            size_str = human_size(new_name.stat().st_size)
            edit_msg(
                chat_id,
                msg_id,
                f"✅ <b>[۲/۳] تگ‌ها اعمال شد</b>\n\n"
                f"📤 <b>[۳/۳] در حال آپلود فایل...</b>\n"
                f"<blockquote>حجم فایل: <b>{size_str}</b>\n"
                f"<i>بسته به سرعت گیت‌هاب، ممکنه ۱ تا ۲ دقیقه طول بکشه</i></blockquote>",
            )

            success = send_audio(
                chat_id,
                new_name,
                caption=(
                    f"✅ <b>تگ‌ها با موفقیت اعمال شد!</b>\n\n"
                    f"<blockquote>"
                    f"🎵 <b>{session.get('title') or session.get('orig_name', 'Music')}</b>\n"
                    f"🎤 {session.get('artist') or 'نامشخص'}\n"
                    f"</blockquote>"
                ),
                cover_path=session.get("cover"),
            )

            if success:
                store.inc_files(user["id"])
                edit_msg(
                    chat_id,
                    msg_id,
                    "✨ <b>عملیات با موفقیت به پایان رسید!</b>\n\n"
                    "<i>ممنون که از HiVo Tag Music استفاده کردی 🎧</i>",
                )
            else:
                edit_msg(
                    chat_id,
                    msg_id,
                    "❌ <b>خطا در آپلود فایل به تلگرام</b>\n\n"
                    "<i>لطفاً دوباره فایل رو بفرست و مجدداً تلاش کن.</i>",
                )

            try:
                new_name.unlink()
            except Exception:
                pass

        except Exception as e:
            log.exception("tag error")
            send(chat_id, f"❌ <b>خطا در پردازش:</b>\n<code>{e}</code>")

        store.clear_session(user["id"])
        return

    if data in FIELD_NAMES:
        field, prompt = FIELD_NAMES[data]
        answer_cb(cb["id"])
        session["awaiting"] = field
        store.set_session(user["id"], session)
        send(chat_id, prompt)
        return


# ============================================================
#                    هندلر متن و عکس
# ============================================================
def handle_text(chat_id, user, text):
    session = store.get_session(user["id"])
    if not session or not session.get("awaiting"):
        return False
    field = session["awaiting"]
    session[field] = text.strip()
    session.pop("awaiting", None)
    store.set_session(user["id"], session)

    send(
        chat_id,
        f"✅ <b>ثبت شد:</b> <code>{text}</code>\n\n"
        f"<i>تغییرات دیگه‌ای اعمال کن یا پیش‌نمایش رو بزن 👇</i>",
        edit_menu(session),
    )
    return True


def handle_photo(chat_id, user, msg):
    session = store.get_session(user["id"])
    if not session:
        return
    photo = msg["photo"][-1] if msg.get("photo") else msg.get("document")
    if not photo:
        return

    path = download(photo["file_id"], f"cover_{user['id']}.jpg")
    if not path:
        send(chat_id, "❌ خطا در دریافت کاور")
        return

    try:
        img = Image.open(path)
        img = img.convert("RGB")
        img.thumbnail((800, 800))
        img.save(path, "JPEG", quality=88)
        log.info(f"Cover optimized: {path} ({human_size(path.stat().st_size)})")
    except Exception as e:
        log.error(f"خطا در تبدیل کاور: {e}")
        send(chat_id, "❌ خطا در پردازش عکس کاور")
        return

    session["cover"] = str(path)
    session.pop("awaiting", None)
    store.set_session(user["id"], session)
    send(
        chat_id,
        "🖼 <b>کاور با موفقیت ثبت شد!</b>\n\n<i>حالا می‌تونی تغییرات دیگه‌ای بدی یا پیش‌نمایش رو بزنی 👇</i>",
        edit_menu(session),
    )


# ============================================================
#                    راه‌اندازی و حلقه اصلی
# ============================================================
def setup_bot():
    log.info("🚀 شروع راه‌اندازی ربات...")
    api("deleteWebhook", drop_pending_updates=False)

    me = api("getMe")
    if not me.get("ok"):
        log.error("❌ توکن ربات نامعتبر است!")
        sys.exit(1)
    log.info(f"✅ ربات متصل شد: @{me['result']['username']}")

    # --- منوی دستورات ---
    api(
        "setMyCommands",
        commands=[
            {"command": "start", "description": "🏠 شروع مجدد"},
            {"command": "help", "description": "📖 راهنمای استفاده"},
            {"command": "stats", "description": "📊 آمار ربات"},
        ],
    )

    # --- دکمه منوی شیشه‌ای ---
    api(
        "setChatMenuButton",
        menu_button={"type": "commands"},
    )
    log.info("✅ منو و دکمه‌ها تنظیم شد.")


def main():
    setup_bot()
    offset = get_offset()
    start = time.time()
    log.info(f"🤖 ربات در حال اجراست. offset={offset}")

    while time.time() - start < 355 * 60:
        try:
            r = requests.get(
                f"{API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40,
            ).json()

            if not r.get("ok"):
                log.error(f"❌ خطای getUpdates: {r.get('description', 'Unknown')}")
                time.sleep(10)
                continue

            for upd in r.get("result", []):
                offset = upd["update_id"] + 1
                log.info(f"📩 آپدیت دریافت شد: {offset}")

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
                                cmd_help(chat_id)
                            elif t.startswith("/stats"):
                                cmd_stats(chat_id, user["id"])
                            elif t.startswith("/admin") and user["id"] == ADMIN_ID:
                                s = store.get_stats()
                                send(
                                    chat_id,
                                    f"👑 <b>پنل ادمین</b>\n\n"
                                    f"<blockquote>"
                                    f"👥 کاربران: <b>{s['users']}</b>\n"
                                    f"🎵 فایل‌ها: <b>{s['files']}</b>"
                                    f"</blockquote>",
                                )
                            else:
                                handle_text(chat_id, user, t)

                        elif "audio" in m or "document" in m:
                            handle_audio(chat_id, user, m)
                        elif "photo" in m:
                            handle_photo(chat_id, user, m)

                    elif "callback_query" in upd:
                        handle_callback(upd["callback_query"])

                except Exception as e:
                    log.exception(f"❌ خطا در پردازش آپدیت: {e}")

                save_offset(offset)

        except requests.exceptions.Timeout:
            log.warning("⏳ تایم‌اوت، تلاش مجدد...")
            time.sleep(5)
        except Exception as e:
            log.error(f"❌ خطای کلی: {e}")
            time.sleep(5)

    log.info("🛑 زمان اجرا تمام شد.")


if __name__ == "__main__":
    main()
