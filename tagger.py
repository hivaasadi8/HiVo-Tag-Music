from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON, TRCK, APIC, error
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover
from pathlib import Path


def edit_tags(file_path, title=None, artist=None, album=None,
              year=None, genre=None, track=None, cover_path=None):
    """تگ فایل موزیک رو بر اساس فرمت ادیت می‌کنه"""
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".mp3":
        _edit_mp3(path, title, artist, album, year, genre, track, cover_path)
    elif ext == ".flac":
        _edit_flac(path, title, artist, album, year, genre, track, cover_path)
    elif ext in (".m4a", ".mp4", ".aac"):
        _edit_mp4(path, title, artist, album, year, genre, track, cover_path)
    else:
        raise ValueError(f"فرمت پشتیبانی نمی‌شه: {ext}")

    return True


def _edit_mp3(path, title, artist, album, year, genre, track, cover):
    audio = MP3(path, ID3=ID3)
    try:
        audio.add_tags()
    except error:
        pass

    if title:  audio.tags.add(TIT2(encoding=3, text=title))
    if artist: audio.tags.add(TPE1(encoding=3, text=artist))
    if album:  audio.tags.add(TALB(encoding=3, text=album))
    if year:   audio.tags.add(TDRC(encoding=3, text=year))
    if genre:  audio.tags.add(TCON(encoding=3, text=genre))
    if track:  audio.tags.add(TRCK(encoding=3, text=track))

    if cover and Path(cover).exists():
        audio.tags.delall("APIC")
        mime = "image/png" if Path(cover).suffix.lower() == ".png" else "image/jpeg"
        with open(cover, "rb") as f:
            audio.tags.add(APIC(encoding=3, mime=mime, type=3,
                                desc="Cover", data=f.read()))
    audio.save()


def _edit_flac(path, title, artist, album, year, genre, track, cover):
    audio = FLAC(path)
    if title:  audio["title"] = title
    if artist: audio["artist"] = artist
    if album:  audio["album"] = album
    if year:   audio["date"] = year
    if genre:  audio["genre"] = genre
    if track:  audio["tracknumber"] = track

    if cover and Path(cover).exists():
        audio.clear_pictures()
        pic = Picture()
        pic.type = 3
        pic.mime = "image/png" if Path(cover).suffix.lower() == ".png" else "image/jpeg"
        pic.data = Path(cover).read_bytes()
        audio.add_picture(pic)
    audio.save()


def _edit_mp4(path, title, artist, album, year, genre, track, cover):
    audio = MP4(path)
    if title:  audio["\xa9nam"] = [title]
    if artist: audio["\xa9ART"] = [artist]
    if album:  audio["\xa9alb"] = [album]
    if year:   audio["\xa9day"] = [year]
    if genre:  audio["\xa9gen"] = [genre]
    if track:  audio["trkn"] = [(int(track), 0)]

    if cover and Path(cover).exists():
        fmt = MP4Cover.FORMAT_PNG if Path(cover).suffix.lower() == ".png" else MP4Cover.FORMAT_JPEG
        audio["covr"] = [MP4Cover(Path(cover).read_bytes(), imageformat=fmt)]
    audio.save()
