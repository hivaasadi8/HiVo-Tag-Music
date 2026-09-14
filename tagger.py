"""
HiVo Tag Music - Advanced Audio Tagger Engine
==============================================
ماژول ویرایش تگ‌های صوتی با پشتیبانی از:
  - فرمت‌ها: MP3, FLAC, M4A, OGG, WAV
  - تگ‌های ReplayGain (نرمال‌سازی صدا)
  - شناسه‌های MusicBrainz (MBID)
  - کاور با کیفیت بالا
"""

import logging
from pathlib import Path
from typing import Optional

from mutagen.mp3 import MP3
from mutagen.id3 import (
    ID3, TIT2, TPE1, TALB, TDRC, TCON, TRCK, APIC, error,
    TXXX, UFID, COMM
)
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

log = logging.getLogger(__name__)


# ============================================================
#                    توابع کمکی
# ============================================================
def _get_mime_type(path: Path) -> str:
    """تشخیص نوع MIME بر اساس پسوند فایل"""
    ext = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


def _read_cover_bytes(cover_path: Path) -> bytes:
    """خواندن بایت‌های عکس کاور"""
    with open(cover_path, "rb") as f:
        return f.read()


# ============================================================
#                    MP3 Tagging
# ============================================================
def _edit_mp3(
    path: Path,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    year: Optional[str] = None,
    genre: Optional[str] = None,
    track: Optional[str] = None,
    cover_path: Optional[str] = None,
    replaygain: Optional[dict] = None,
    mbids: Optional[dict] = None,
    comment: Optional[str] = None,
):
    """ویرایش تگ‌های فایل MP3 (ID3v2.4)"""
    audio = MP3(path, ID3=ID3)

    # ساخت تگ‌ها در صورت نبودن
    try:
        audio.add_tags()
    except error:
        pass

    # --- تگ‌های استاندارد ---
    if title:
        audio.tags.add(TIT2(encoding=3, text=title))
    if artist:
        audio.tags.add(TPE1(encoding=3, text=artist))
    if album:
        audio.tags.add(TALB(encoding=3, text=album))
    if year:
        audio.tags.add(TDRC(encoding=3, text=year))
    if genre:
        audio.tags.add(TCON(encoding=3, text=genre))
    if track:
        audio.tags.add(TRCK(encoding=3, text=track))
    if comment:
        audio.tags.add(COMM(encoding=3, lang="eng", desc="", text=comment))

    # --- تگ‌های ReplayGain (TXXX) ---
    if replaygain:
        rg_map = {
            "track_gain": "replaygain_track_gain",
            "track_peak": "replaygain_track_peak",
            "album_gain": "replaygain_album_gain",
            "album_peak": "replaygain_album_peak",
        }
        for key, tag_desc in rg_map.items():
            if replaygain.get(key):
                audio.tags.add(TXXX(encoding=3, desc=tag_desc, text=[replaygain[key]]))

    # --- شناسه‌های MusicBrainz ---
    if mbids:
        if mbids.get("track_id"):
            audio.tags.add(UFID(owner="http://musicbrainz.org", data=mbids["track_id"].encode()))
        mbid_map = {
            "album_id": "MusicBrainz Album Id",
            "artist_id": "MusicBrainz Artist Id",
            "release_group_id": "MusicBrainz Release Group Id",
            "album_artist_id": "MusicBrainz Album Artist Id",
        }
        for key, tag_desc in mbid_map.items():
            if mbids.get(key):
                audio.tags.add(TXXX(encoding=3, desc=tag_desc, text=[mbids[key]]))

    # --- کاور ---
    if cover_path and Path(cover_path).exists():
        audio.tags.delall("APIC")
        cover_data = _read_cover_bytes(Path(cover_path))
        audio.tags.add(APIC(
            encoding=3,
            mime=_get_mime_type(Path(cover_path)),
            type=3,
            desc="Cover",
            data=cover_data,
        ))

    audio.save()
    log.info(f"✅ MP3 tags saved: {path.name}")


# ============================================================
#                    FLAC Tagging
# ============================================================
def _edit_flac(
    path: Path,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    year: Optional[str] = None,
    genre: Optional[str] = None,
    track: Optional[str] = None,
    cover_path: Optional[str] = None,
    replaygain: Optional[dict] = None,
    mbids: Optional[dict] = None,
    comment: Optional[str] = None,
):
    """ویرایش تگ‌های فایل FLAC (Vorbis Comments)"""
    audio = FLAC(path)

    if title:
        audio["title"] = title
    if artist:
        audio["artist"] = artist
    if album:
        audio["album"] = album
    if year:
        audio["date"] = year
    if genre:
        audio["genre"] = genre
    if track:
        audio["tracknumber"] = track
    if comment:
        audio["comment"] = comment

    # --- ReplayGain ---
    if replaygain:
        if replaygain.get("track_gain"):
            audio["replaygain_track_gain"] = replaygain["track_gain"]
        if replaygain.get("track_peak"):
            audio["replaygain_track_peak"] = replaygain["track_peak"]
        if replaygain.get("album_gain"):
            audio["replaygain_album_gain"] = replaygain["album_gain"]
        if replaygain.get("album_peak"):
            audio["replaygain_album_peak"] = replaygain["album_peak"]

    # --- MusicBrainz ---
    if mbids:
        if mbids.get("track_id"):
            audio["musicbrainz_trackid"] = mbids["track_id"]
        if mbids.get("album_id"):
            audio["musicbrainz_albumid"] = mbids["album_id"]
        if mbids.get("artist_id"):
            audio["musicbrainz_artistid"] = mbids["artist_id"]
        if mbids.get("release_group_id"):
            audio["musicbrainz_releasegroupid"] = mbids["release_group_id"]

    # --- کاور ---
    if cover_path and Path(cover_path).exists():
        audio.clear_pictures()
        picture = Picture()
        picture.type = 3
        picture.mime = _get_mime_type(Path(cover_path))
        picture.desc = "Cover"
        picture.data = _read_cover_bytes(Path(cover_path))
        audio.add_picture(picture)

    audio.save()
    log.info(f"✅ FLAC tags saved: {path.name}")


# ============================================================
#                    MP4 / M4A Tagging
# ============================================================
def _edit_mp4(
    path: Path,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    year: Optional[str] = None,
    genre: Optional[str] = None,
    track: Optional[str] = None,
    cover_path: Optional[str] = None,
    replaygain: Optional[dict] = None,
    mbids: Optional[dict] = None,
    comment: Optional[str] = None,
):
    """ویرایش تگ‌های فایل MP4/M4A (iTunes Atoms)"""
    audio = MP4(path)

    if title:
        audio["\xa9nam"] = [title]
    if artist:
        audio["\xa9ART"] = [artist]
    if album:
        audio["\xa9alb"] = [album]
    if year:
        audio["\xa9day"] = [year]
    if genre:
        audio["\xa9gen"] = [genre]
    if comment:
        audio["\xa9cmt"] = [comment]
    if track:
        try:
            audio["trkn"] = [(int(track), 0)]
        except ValueError:
            audio["trkn"] = [(0, 0)]

    # --- ReplayGain (Freeform tags) ---
    if replaygain:
        if replaygain.get("track_gain"):
            audio["----:com.apple.iTunes:replaygain_track_gain"] = [replaygain["track_gain"].encode()]
        if replaygain.get("track_peak"):
            audio["----:com.apple.iTunes:replaygain_track_peak"] = [replaygain["track_peak"].encode()]
        if replaygain.get("album_gain"):
            audio["----:com.apple.iTunes:replaygain_album_gain"] = [replaygain["album_gain"].encode()]
        if replaygain.get("album_peak"):
            audio["----:com.apple.iTunes:replaygain_album_peak"] = [replaygain["album_peak"].encode()]

    # --- MusicBrainz (Freeform tags) ---
    if mbids:
        if mbids.get("track_id"):
            audio["----:com.apple.iTunes:MusicBrainz Track Id"] = [mbids["track_id"].encode()]
        if mbids.get("album_id"):
            audio["----:com.apple.iTunes:MusicBrainz Album Id"] = [mbids["album_id"].encode()]
        if mbids.get("artist_id"):
            audio["----:com.apple.iTunes:MusicBrainz Artist Id"] = [mbids["artist_id"].encode()]
        if mbids.get("release_group_id"):
            audio["----:com.apple.iTunes:MusicBrainz Release Group Id"] = [mbids["release_group_id"].encode()]

    # --- کاور ---
    if cover_path and Path(cover_path).exists():
        cover_data = _read_cover_bytes(Path(cover_path))
        fmt = MP4Cover.FORMAT_PNG if _get_mime_type(Path(cover_path)) == "image/png" else MP4Cover.FORMAT_JPEG
        audio["covr"] = [MP4Cover(cover_data, imageformat=fmt)]

    audio.save()
    log.info(f"✅ MP4 tags saved: {path.name}")


# ============================================================
#                    OGG Tagging
# ============================================================
def _edit_ogg(
    path: Path,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    year: Optional[str] = None,
    genre: Optional[str] = None,
    track: Optional[str] = None,
    **kwargs,
):
    """ویرایش تگ‌های فایل OGG (Vorbis Comments)"""
    audio = OggVorbis(path)
    if title:
        audio["title"] = title
    if artist:
        audio["artist"] = artist
    if album:
        audio["album"] = album
    if year:
        audio["date"] = year
    if genre:
        audio["genre"] = genre
    if track:
        audio["tracknumber"] = track
    audio.save()
    log.info(f"✅ OGG tags saved: {path.name}")


# ============================================================
#                    WAV Tagging (ID3)
# ============================================================
def _edit_wav(
    path: Path,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    **kwargs,
):
    """ویرایش تگ‌های فایل WAV (ID3)"""
    audio = WAVE(path)
    try:
        audio.add_tags()
    except error:
        pass
    if title:
        audio.tags.add(TIT2(encoding=3, text=title))
    if artist:
        audio.tags.add(TPE1(encoding=3, text=artist))
    if album:
        audio.tags.add(TALB(encoding=3, text=album))
    audio.save()
    log.info(f"✅ WAV tags saved: {path.name}")


# ============================================================
#                    تابع اصلی
# ============================================================
def edit_tags(
    file_path: str,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    year: Optional[str] = None,
    genre: Optional[str] = None,
    track: Optional[str] = None,
    cover_path: Optional[str] = None,
    replaygain: Optional[dict] = None,
    mbids: Optional[dict] = None,
    comment: Optional[str] = None,
) -> bool:
    """
    ویرایش تگ‌های فایل صوتی بر اساس فرمت.

    Args:
        file_path: مسیر فایل صوتی
        title: نام آهنگ
        artist: نام خواننده
        album: نام آلبوم
        year: سال انتشار
        genre: ژانر
        track: شماره ترک
        cover_path: مسیر عکس کاور
        replaygain: دیکشنری شامل track_gain, track_peak, album_gain, album_peak
        mbids: دیکشنری شامل track_id, album_id, artist_id, release_group_id
        comment: توضیحات

    Returns:
        True در صورت موفقیت، در غیر این صورت خطا پرتاب می‌شود.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    handlers = {
        ".mp3": _edit_mp3,
        ".flac": _edit_flac,
        ".m4a": _edit_mp4,
        ".mp4": _edit_mp4,
        ".aac": _edit_mp4,
        ".ogg": _edit_ogg,
        ".wav": _edit_wav,
    }

    handler = handlers.get(ext)
    if not handler:
        raise ValueError(f"فرمت پشتیبانی نمی‌شود: {ext}")

    handler(
        path=path,
        title=title,
        artist=artist,
        album=album,
        year=year,
        genre=genre,
        track=track,
        cover_path=cover_path,
        replaygain=replaygain,
        mbids=mbids,
        comment=comment,
    )
    return True


# ============================================================
#                    تست سریع (اجرای مستقیم)
# ============================================================
if __name__ == "__main__":
    # نمونه تست
    print("🎧 HiVo Tag Music - Tagger Engine")
    print("این ماژول برای ویرایش تگ‌های صوتی استفاده می‌شود.")
    print("نمونه فراخوانی:")
    print("  edit_tags('song.mp3', title='My Song', artist='Artist', cover_path='cover.jpg')")
