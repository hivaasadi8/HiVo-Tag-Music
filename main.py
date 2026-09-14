import os
import json
import time
import logging
from pathlib import Path
import requests
from tagger import edit_tags
from store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

TOKEN = os.environ["TELEGRAM_TOKEN"]
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
API = f"https://api.telegram.org/bot{TOKEN}"
OFFSET_FILE = Path("offset.json")
TEMP = Path("tmp")
TEMP.mkdir(exist_ok=True)

store = Store("state.json")


# ---------- Telegram helpers ----------
def api(method, **params):
    try:
        r = requests.post(f"{API}/{method}", json=params, timeout=60)
        return r.json()
    except Exception as e:
        log.error(f"API error {method}: {e}")
        return {}


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
        return json.loads(OFFSET_FILE.read_text()).get("offset", 0)
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
    r = requests.get(url, timeout=120)
    dest.write_bytes(r.content)
    return dest


def send_audio(chat_id, path, caption=""):
    with open(path, "rb") as f:
        requests.post(
            f"{API}/sendAudio",
            data={"chat_id": chat_id, "caption": caption},
            files={"audio": f},
            timeout=180
        )


# ---------- Keyboards ----------
def main_menu():
    return [
        [{"text": "🎵 راهنما", "callback_data": "help"},
         {"text": "📊 آمار من", "callback_data": "my_stats"}],
    ]


def edit_menu(session):
    def mark(field):
        return "✅ " if session.get(field) else "▫️ "
    return [
        [{"text": f"{mark('title')}اسم آهنگ", "callback_data": "f_title"},
         {"text": f"{mark('artist')}خواننده", "callback_data": "f_artist"}],
        [{"text": f"{mark('album')}آلبوم", "callback_data": "f_album"},
         {"text": f"{mark('year')}سال", "callback_data": "f_year"}],
        [{"text": f"{mark('genre')}ژانر", "callback_data": "f_genre"},
         {"text": f"{mark('track')}شماره ترک", "callback_data": "f_track"}],
        [{"text": f"{mark('cover')}کاور 🖼", "callback_data": "f_cover"}],
        [{"text": "✅ اعمال تگ‌ها", "callback_data": "apply"},
         {"text": "❌ لغو", "callback_data": "cancel"}],
    ]


# ---------- Command handlers ----------
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
        "📖 <b>راهنما</b>\n\n"
        "1️⃣ فایل موزیک رو بفرست\n"
        "2️⃣ روی گزینه‌های مورد نظر بزن و مقدار جدید رو تایپ کن\n"
        "3️⃣ برای کاور، عکس رو بفرست\n"
        "4️⃣ آخرش روی «اعمال تگ‌ها» بزن تا فایل ادیت‌شده رو بگیری"
    )
    send(chat_id, text)


def cmd_stats(chat_id, user_id):
    s = store.get_stats()
    me = store.data["users"].get(str(user_id), {})
    text = (
        f"📊 <b>آمار</b>\n\n"
        f"👤 کاربر کل: <b>{s['users']}</b>\n"
        f"🎵 فایل پردازش‌شده: <b>{s['files']}</b>\n\n"
        f"📁 فایل‌های تو: <b>{me.get('files', 0)}</b>"
    )
    send(chat_id, text)


# ---------- File handler ----------
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
    tmp_path = TEMP / f"{user['id']}_{int(time.time())}{ext}"
    path = download(audio["file_id"], tmp_path.name)
    if not path:
        send(chat_id, "❌ خطا در دانلود فایل.")
        return

    session = {
        "file": str(path),
        "orig_name": audio.get("file_name", "music" + ext),
        "title": audio.get("title"),
        "artist": audio.get("performer"),
        "album": None, "year": None, "genre": None, "track": None,
        "cover": None
    }
    store.set_session(user["id"], session)

    send(
        chat_id,
        "🎵 فایل دریافت شد!\nحالا گزینه‌هایی که می‌خوای عوض کنی رو انتخاب کن 👇",
        edit_menu(session)
    )


# ---------- Callback handler ----------
FIELD_NAMES = {
    "f_title": ("title", "📝 اسم آهنگ جدید رو بنویس:"),
    "f_artist": ("artist", "🎤 اسم خواننده جدید رو بنویس:"),
    "f_album": ("album", "💿 اسم آلبوم جدید رو بنویس:"),
    "f_year": ("year", "📅 سال انتشار (مثلاً 2025):"),
    "f_genre": ("genre", "🎼 ژانر (مثلاً Pop, Rock):"),
    "f_track": ("track", "🔢 شماره ترک (مثلاً 1):"),
    "f_cover": ("cover", "🖼 عکس کاور رو بفرست (به‌صورت Photo یا Document):"),
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

    if data == "apply":
        answer_cb(cb["id"], "در حال پردازش...")
        edit_msg(chat_id, msg_id, "⏳ در حال اعمال تگ‌ها...")
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
            name = session["orig_name"]
            out = Path(session["file"])
            new_name = TEMP / f"tagged_{name}"
            out.rename(new_name)
            send_audio(chat_id, new_name, caption="✅ تگ‌ها با موفقیت اعمال شد")
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


# ---------- Text / Photo handler ----------
def handle_text(chat_id, user, text):
    session = store.get_session(user["id"])
    if not session or not session.get("awaiting"):
        return False
    field = session["awaiting"]
    session[field] = text.strip()
    session.pop("awaiting", None)
    store.set_session(user["id"], session)
    send(chat_id, f"✅ ثبت شد: <b>{text}</b>", edit_menu(session))
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
    session["cover"] = str(path)
    session.pop("awaiting", None)
    store.set_session(user["id"], session)
    send(chat_id, "🖼 کاور ثبت شد", edit_menu(session))


# ---------- Main loop ----------
def main():
    offset = get_offset()
    start = time.time()
    log.info(f"Bot started. offset={offset}")

    while time.time() - start < 355 * 60:  # ~5 ساعت و 55 دقیقه
        try:
            r = requests.get(
                f"{API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=60,
            ).json()
        except Exception as e:
            log.error(f"getUpdates error: {e}")
            time.sleep(5)
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
                log.exception(f"update error: {e}")

            save_offset(offset)

        save_offset(offset)

    log.info("Bot run finished.")


if __name__ == "__main__":
    main()
