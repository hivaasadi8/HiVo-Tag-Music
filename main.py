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


# --- توابع ارتباط با تلگرام ---
def api(method, **params):
    try:
        r = requests.post(f"{API}/{method}", json=params, timeout=60)
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
        r = requests.get(url, timeout=120)
        dest.write_bytes(r.content)
        return dest
    except Exception as e:
        log.error(f"خطا در دانلود: {e}")
        return None


def send_audio(chat_id, path, caption="", cover_path=None):
    try:
        files = {"audio": open(path, "rb")}
        data = {"chat_id": chat_id, "caption": caption}

        if cover_path and Path(cover_path).exists():
            thumb_path = TEMP / "thumb.jpg"
            img = Image.open(cover_path)
            img = img.convert("RGB")
            img.thumbnail((320, 320))
            img.save(thumb_path, "JPEG", quality=85)
            files["thumb"] = open(thumb_path, "rb")

        requests.post(f"{API}/sendAudio", data=data, files=files, timeout=180)
    except Exception as e:
        log.error(f"خطا در ارسال فایل: {e}")
    finally:
        for f in files.values():
            try:
                f.close()
            except Exception:
                pass


# --- دکمه‌های زیبا ---
def main_menu():
    return [
        [{"text": "🎵 راهنما", "callback_data": "help"},
         {"text": "📊 آمار من", "callback_data": "my_stats"}]
    ]


def edit_menu(session):
    def mark(field):
        return "✅ " if session.get(field) else "▫️ "
    return [
        [{"text": f"{mark('title')}🎵 اسم آهنگ", "callback_data": "f_title"},
         {"text": f"{mark('artist')}🎤 خواننده", "callback_data": "f_artist"}],
        [{"text": f"{mark('album')}💿 آلبوم", "callback_data": "f_album"},
         {"text": f"{mark('year')}📅 سال", "callback_data": "f_year"}],
        [{"text": f"{mark('genre')}🎼 ژانر", "callback_data": "f_genre"},
         {"text": f"{mark('track')}🔢 شماره ترک", "callback_data": "f_track"}],
        [{"text": f"{mark('cover')}🖼 کاور", "callback_data": "f_cover"}],
        [{"text": "✅ پیش‌نمایش و تایید", "callback_data": "preview"},
         {"text": "❌ لغو", "callback_data": "cancel"}],
    ]


def preview_menu():
    return [
        [{"text": "✅ بله، اعمال کن", "callback_data": "apply"},
         {"text": "🔙 بازگشت", "callback_data": "back"}]
    ]


# --- هندلرها ---
def cmd_start(chat_id, user):
    store.add_user(user["id"], user.get("first_name", ""))
    text = (
        f"سلام <b>{user.get('first_name','')}</b> 👋\n\n"
        "من ربات <b>ادیت تگ موزیک</b> هستم 🎧\n"
        "فایل موزیکت رو بفرست تا اسم آهنگ، خواننده، کاور و بقیه تگ‌هاش رو عوض کنم.\n\n"
        "📌 فرمت‌های پشتیبانی‌شده: MP3, FLAC, M4A\n"
        "⚠️ حداکثر حجم فایل: 20MB"
    )
    send(chat_id, text, main_menu())


def cmd_help(chat_id):
    text = (
        "📖 <b>راهنمای استفاده</b>\n\n"
        "1️⃣ فایل موزیک رو بفرست\n"
        "2️⃣ روی گزینه‌های مورد نظر بزن و مقدار جدید رو تایپ کن\n"
        "3️⃣ برای کاور، عکس رو بفرست\n"
        "4️⃣ در نهایت روی «پیش‌نمایش و تایید» بزن"
    )
    send(chat_id, text)


def cmd_stats(chat_id, user_id):
    s = store.get_stats()
    me = store.data["users"].get(str(user_id), {})
    text = (
        f"📊 <b>آمار شما</b>\n\n"
        f"👤 کاربر کل: <b>{s['users']}</b>\n"
        f"🎵 فایل پردازش‌شده: <b>{s['files']}</b>\n"
        f"📁 فایل‌های تو: <b>{me.get('files', 0)}</b>"
    )
    send(chat_id, text)


def handle_audio(chat_id, user, msg):
    audio = msg.get("audio") or msg.get("document")
    if not audio:
        return
    size = audio.get("file_size", 0)
    if size > 20 * 1024 * 1024:
        send(chat_id, "❌ فایل بزرگ‌تر از 20MB هست و تلگرام اجازه دانلودش رو نمی‌ده.")
        return

    ext = ".mp3"
    if audio.get("file_name"):
        ext = Path(audio["file_name"]).suffix or ".mp3"
    tmp_name = f"{user['id']}_{int(time.time())}{ext}"
    path = download(audio["file_id"], tmp_name)
    if not path:
        send(chat_id, "❌ خطا در دانلود فایل.")
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
    send(
        chat_id,
        "🎵 <b>فایل دریافت شد!</b>\nحالا گزینه‌هایی که می‌خوای عوض کنی رو انتخاب کن 👇",
        edit_menu(session),
    )


FIELD_NAMES = {
    "f_title": ("title", "📝 <b>اسم آهنگ جدید</b> رو بنویس:"),
    "f_artist": ("artist", "🎤 <b>اسم خواننده جدید</b> رو بنویس:"),
    "f_album": ("album", "💿 <b>اسم آلبوم جدید</b> رو بنویس:"),
    "f_year": ("year", "📅 <b>سال انتشار</b> (مثلاً 2025):"),
    "f_genre": ("genre", "🎼 <b>ژانر</b> (مثلاً Pop, Rock):"),
    "f_track": ("track", "🔢 <b>شماره ترک</b> (مثلاً 1):"),
    "f_cover": ("cover", "🖼 <b>عکس کاور</b> رو بفرست (به‌صورت Photo):"),
}


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
    if data == "cancel":
        answer_cb(cb["id"], "لغو شد")
        store.clear_session(user["id"])
        edit_msg(chat_id, msg_id, "❌ عملیات لغو شد.")
        return

    session = store.get_session(user["id"])
    if not session:
        answer_cb(cb["id"], "سشن منقضی شده، فایل رو دوباره بفرست.")
        return

    if data == "back":
        answer_cb(cb["id"])
        edit_msg(chat_id, msg_id, "🎵 <b>فایل دریافت شد!</b>\nگزینه‌های مورد نظر رو انتخاب کن 👇", edit_menu(session))
        return

    if data == "preview":
        answer_cb(cb["id"])
        p = "📋 <b>پیش‌نمایش تغییرات:</b>\n\n"
        p += f"🎵 اسم آهنگ: <code>{session.get('title') or '---'}</code>\n"
        p += f"🎤 خواننده: <code>{session.get('artist') or '---'}</code>\n"
        p += f"💿 آلبوم: <code>{session.get('album') or '---'}</code>\n"
        p += f"📅 سال: <code>{session.get('year') or '---'}</code>\n"
        p += f"🎼 ژانر: <code>{session.get('genre') or '---'}</code>\n"
        p += f"🔢 ترک: <code>{session.get('track') or '---'}</code>\n"
        p += f"🖼 کاور: {'✅ دارد' if session.get('cover') else '❌ ندارد'}\n\n"
        p += "آیا از اعمال این تغییرات مطمئنی؟"
        edit_msg(chat_id, msg_id, p, preview_menu())
        return

    if data == "apply":
        answer_cb(cb["id"], "در حال پردازش...")
        edit_msg(chat_id, msg_id, "⏳ <b>در حال اعمال تگ‌ها، لطفاً صبر کن...</b>")
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
            send_audio(chat_id, new_name, caption="✅ <b>تگ‌ها با موفقیت اعمال شد!</b>", cover_path=session.get("cover"))
            store.inc_files(user["id"])
            try:
                new_name.unlink()
            except Exception:
                pass
        except Exception as e:
            log.exception("tag error")
            send(chat_id, f"❌ خطا در ادیت: <code>{e}</code>")
        store.clear_session(user["id"])
        return

    if data in FIELD_NAMES:
        field, prompt = FIELD_NAMES[data]
        answer_cb(cb["id"])
        session["awaiting"] = field
        store.set_session(user["id"], session)
        send(chat_id, prompt)
        return


def handle_text(chat_id, user, text):
    session = store.get_session(user["id"])
    if not session or not session.get("awaiting"):
        return False
    field = session["awaiting"]
    session[field] = text.strip()
    session.pop("awaiting", None)
    store.set_session(user["id"], session)
    send(chat_id, f"✅ ثبت شد: <b>{text}</b>\n\nحالا تغییرات دیگه‌ای اعمال کن یا پیش‌نمایش رو بزن.", edit_menu(session))
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
        send(chat_id, "❌ خطا در دانلود کاور")
        return

    try:
        img = Image.open(path)
        img = img.convert("RGB")
        img.thumbnail((1000, 1000))
        img.save(path, "JPEG")
        log.info(f"Cover converted to JPEG: {path}")
    except Exception as e:
        log.error(f"خطا در تبدیل کاور: {e}")
        send(chat_id, "❌ خطا در پردازش عکس کاور")
        return

    session["cover"] = str(path)
    session.pop("awaiting", None)
    store.set_session(user["id"], session)
    send(chat_id, "🖼 <b>کاور با موفقیت ثبت شد!</b>", edit_menu(session))


# --- حلقه اصلی ---
def setup_bot():
    log.info("🚀 شروع راه‌اندازی ربات...")
    api("deleteWebhook", drop_pending_updates=False)
    me = api("getMe")
    if not me.get("ok"):
        log.error("❌ توکن ربات نامعتبر است!")
        sys.exit(1)
    log.info(f"✅ ربات با موفقیت متصل شد: @{me['result']['username']}")


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
                                send(chat_id, f"👑 <b>پنل ادمین</b>\n\n👥 کاربران: {s['users']}\n🎵 فایل‌ها: {s['files']}")
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
