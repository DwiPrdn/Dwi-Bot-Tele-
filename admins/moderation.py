"""
moderation.py

Fitur ala @MissRose_bot: Filters (auto-reply ke kata/frasa tertentu), Notes
(simpen info buat diambil lagi pake trigger word), sama Welcome (pesan
sambutan member baru, custom teks/media).

Dipake sebagai drop-in, dipanggil dari main.py:

    from moderation import register_moderation
    register_moderation(app, load_db, save_db, is_user_admin, OWNER_ID,
                         DB_FILTERS, DB_NOTES, DB_WELCOME)

Modul ini SENGAJA gak import `app` dari main.py langsung (biar gak circular
import) - client & helper2-nya di-inject lewat register_moderation().
"""
import os
import re
import html
import logging
from telethon import events, Button

logger = logging.getLogger("Moderation")

DEFAULT_WELCOME = "Hai {first}, selamat datang di {chatname}! 👋"

_BASE_PATH = os.getenv("BASE_PATH") or os.path.dirname(os.path.abspath(__file__))
SAVED_MEDIA_DIR = os.getenv("SAVED_MEDIA_DIR") or os.path.join(_BASE_PATH, "dbbot", "saved_media")
os.makedirs(SAVED_MEDIA_DIR, exist_ok=True)



async def get_album_messages(client, reply):
    """
    Jika pesan yang di-reply merupakan bagian dari media album (memiliki grouped_id),
    ambil seluruh pesan dalam album tersebut, diurutkan berdasarkan ID pesan.
    """
    if not reply or not getattr(reply, "grouped_id", None):
        return [reply] if reply else []

    gid = reply.grouped_id
    chat_id = reply.chat_id
    candidates = {reply.id: reply}

    try:
        min_id = max(1, reply.id - 15)
        max_id = reply.id + 16
        nearby = await client.get_messages(chat_id, ids=list(range(min_id, max_id)))
        for m in nearby:
            if m and getattr(m, "grouped_id", None) == gid:
                candidates[m.id] = m
    except Exception as e:
        logger.warning(f"Error fetching album messages by ID range: {e}")
        try:
            async for m in client.iter_messages(chat_id, limit=30, offset_id=reply.id + 15):
                if getattr(m, "grouped_id", None) == gid:
                    candidates[m.id] = m
        except Exception as e2:
            logger.warning(f"Fallback iter_messages also failed: {e2}")

    album = sorted(candidates.values(), key=lambda m: m.id)
    return album if album else [reply]


async def save_media_from_message(reply, chat_key, prefix):
    """
    Download single media dari pesan Telegram ke penyimpanan lokal permanen di server.
    Return (local_path, is_voice, is_video_note).
    """
    if not reply or not reply.media:
        return None, False, False

    is_voice = bool(getattr(reply, "voice", False))
    is_video_note = bool(getattr(reply, "video_note", False))

    dest_dir = os.path.join(SAVED_MEDIA_DIR, str(chat_key))
    os.makedirs(dest_dir, exist_ok=True)
    clean_prefix = re.sub(r'[^a-zA-Z0-9_-]', '_', str(prefix))[:30]
    dest_path = os.path.join(dest_dir, f"{clean_prefix}_{reply.id}")

    try:
        local_path = await reply.download_media(file=dest_path)
        return local_path, is_voice, is_video_note
    except Exception as e:
        logger.error(f"Gagal download media untuk disimpan: {e}", exc_info=True)
        return None, is_voice, is_video_note


async def save_media_from_messages(messages, chat_key, prefix):
    """
    Download media dari daftar pesan Telegram (album/media group) ke disk lokal permanen.
    Return list of dicts: [
        {"file_path": str, "is_voice": bool, "is_video_note": bool, "msg_id": int}, ...
    ]
    """
    results = []
    dest_dir = os.path.join(SAVED_MEDIA_DIR, str(chat_key))
    os.makedirs(dest_dir, exist_ok=True)
    clean_prefix = re.sub(r'[^a-zA-Z0-9_-]', '_', str(prefix))[:25]

    for idx, msg in enumerate(messages):
        if not msg or not msg.media:
            continue
        is_voice = bool(getattr(msg, "voice", False))
        is_video_note = bool(getattr(msg, "video_note", False))
        dest_path = os.path.join(dest_dir, f"{clean_prefix}_{msg.id}_{idx}")
        try:
            local_path = await msg.download_media(file=dest_path)
            results.append({
                "file_path": local_path,
                "is_voice": is_voice,
                "is_video_note": is_video_note,
                "msg_id": msg.id
            })
        except Exception as e:
            logger.error(f"Gagal download media album item {msg.id}: {e}")
            results.append({
                "file_path": None,
                "is_voice": is_voice,
                "is_video_note": is_video_note,
                "msg_id": msg.id
            })
    return results


def delete_stored_media_files(entry):
    """Hapus file lokal dari disk server baik untuk single media maupun album."""
    if not isinstance(entry, dict):
        return
    # Single file
    fp = entry.get("file_path")
    if fp and os.path.exists(fp):
        try:
            os.remove(fp)
        except Exception:
            pass
    # Album files
    for f in entry.get("files") or []:
        if isinstance(f, dict):
            p = f.get("file_path")
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


# ============================================================
#  FILLINGS (placeholder kayak {first}, {chatname}, dst di Rose)
# ============================================================

def render_fillings(text: str, user, chat_title: str) -> str:
    if not text:
        return text
    first = getattr(user, "first_name", None) or "User"
    last = getattr(user, "last_name", None) or ""
    fullname = (first + " " + last).strip()
    username = getattr(user, "username", None)

    # Bersihkan nama untuk mention markdown
    clean_first = first.replace('[', '').replace(']', '').replace('`', '') or "User"
    mention = f"[{clean_first}](tg://user?id={user.id})"

    # Escape karakter reserved markdown v1 (_ dan *) agar tidak bentrok formatting
    safe_first = first.replace('_', '\\_').replace('*', '\\*')
    safe_last = last.replace('_', '\\_').replace('*', '\\*')
    safe_fullname = fullname.replace('_', '\\_').replace('*', '\\*')
    safe_username = f"@{username.replace('_', '\\_')}" if username else safe_fullname
    safe_chatname = (chat_title or "grup ini").replace('_', '\\_').replace('*', '\\*')

    replacements = {
        "{first}": safe_first,
        "{last}": safe_last,
        "{fullname}": safe_fullname,
        "{username}": safe_username,
        "{mention}": mention,
        "{chatname}": safe_chatname,
        "{id}": str(user.id),
    }
    for key, val in replacements.items():
        text = text.replace(key, val)
    return text


async def send_stored_media_or_text(event_or_client, target, text, media_ref, buttons=None, reply_to=None):
    """
    Kirim teks atau media tersimpan (mendukung single media maupun album foto/video).
    Mendukung pengiriman media dari file lokal (file_path / album files) agar tetap bisa
    terkirim meskipun pesan/chat aslinya di Telegram sudah dihapus.
    """
    client = event_or_client.client if hasattr(event_or_client, "client") else event_or_client
    if media_ref:
        m_type = media_ref.get("type")

        # 1. Album / Multi-Media
        if m_type == "album" or "files" in media_ref:
            files_meta = media_ref.get("files") or []
            local_paths = [
                f.get("file_path") for f in files_meta
                if isinstance(f, dict) and f.get("file_path") and os.path.exists(f.get("file_path"))
            ]
            # Prioritas 1: Kirim dari file lokal yang sudah tersimpan di server
            if local_paths:
                try:
                    return await client.send_file(
                        target,
                        file=local_paths,
                        caption=text or None,
                        buttons=buttons,
                        parse_mode="md",
                        reply_to=reply_to
                    )
                except Exception as e:
                    logger.error(f"Gagal kirim album dari file lokal: {e}", exc_info=True)

            # Fallback 2: Ambil dari pesan Telegram asli jika file lokal belum lengkap
            chat_id = media_ref.get("chat_id")
            msg_ids = media_ref.get("msg_ids") or [
                f.get("msg_id") for f in files_meta if isinstance(f, dict) and f.get("msg_id")
            ]
            if chat_id and msg_ids:
                try:
                    orig_msgs = await client.get_messages(chat_id, ids=msg_ids)
                    media_objs = [m.media for m in orig_msgs if m and m.media]
                    if media_objs:
                        sent = await client.send_file(
                            target,
                            file=media_objs,
                            caption=text or None,
                            buttons=buttons,
                            parse_mode="md",
                            reply_to=reply_to
                        )
                        # Cache ke lokal
                        try:
                            dest_dir = os.path.join(SAVED_MEDIA_DIR, str(target))
                            os.makedirs(dest_dir, exist_ok=True)
                            for idx, om in enumerate(orig_msgs):
                                if om and om.media and idx < len(files_meta):
                                    c_path = await om.download_media(file=dest_dir)
                                    if c_path and isinstance(files_meta[idx], dict):
                                        files_meta[idx]["file_path"] = c_path
                        except Exception:
                            pass
                        return sent
                except Exception as e:
                    logger.warning(f"Gagal ambil album dari Telegram ({chat_id}, {msg_ids}): {e}")

        # 2. Single Media
        local_path = media_ref.get("file_path")
        is_voice = media_ref.get("is_voice", False)
        is_video_note = media_ref.get("is_video_note", False)

        if local_path and os.path.exists(local_path):
            try:
                return await client.send_file(
                    target, file=local_path, caption=text or None,
                    buttons=buttons, parse_mode="md", reply_to=reply_to,
                    voice_note=is_voice, video_note=is_video_note
                )
            except Exception as e:
                logger.error(f"Gagal kirim media dari file lokal ({local_path}): {e}")

        chat_id = media_ref.get("chat_id")
        msg_id = media_ref.get("msg_id")
        if chat_id and msg_id:
            try:
                orig = await client.get_messages(chat_id, ids=msg_id)
                if orig and orig.media:
                    sent = await client.send_file(
                        target, file=orig.media, caption=text or None,
                        buttons=buttons, parse_mode="md", reply_to=reply_to,
                        voice_note=is_voice, video_note=is_video_note
                    )
                    try:
                        dest_dir = os.path.join(SAVED_MEDIA_DIR, str(target))
                        os.makedirs(dest_dir, exist_ok=True)
                        cached = await orig.download_media(file=dest_dir)
                        if cached:
                            media_ref["file_path"] = cached
                    except Exception:
                        pass
                    return sent
            except Exception as e:
                logger.warning(f"Gagal ambil media tersimpan ({media_ref}): {e} - fallback ke teks.")

    # 3. Teks fallback (jika tidak ada media atau media gagal dimuat)
    if text:
        return await client.send_message(target, text, buttons=buttons, parse_mode="md", reply_to=reply_to)
    return None


# ============================================================
#  PARSER buat /filter <trigger(s)> <reply> - niru sintaks Rose:
#    /filter word reply
#    /filter "phrase" reply
#    /filter (a, b, "c d") reply
# ============================================================

def parse_filter_triggers(raw: str):
    """Return (list_of_triggers_lowercase, sisa_teks_setelahnya) atau (None, None) kalo gagal parse."""
    raw = raw.strip()
    if not raw:
        return None, None

    if raw.startswith("("):
        close = raw.find(")")
        if close == -1:
            return None, None
        inner = raw[1:close]
        rest = raw[close + 1:].strip()
        items = []
        for part in re.findall(r'"([^"]+)"|([^,]+)', inner):
            phrase, word = part
            val = (phrase or word).strip()
            if val:
                items.append(val.lower())
        if not items:
            return None, None
        return items, rest

    if raw.startswith('"'):
        m = re.match(r'"([^"]+)"\s*(.*)', raw, re.DOTALL)
        if not m:
            return None, None
        return [m.group(1).lower()], m.group(2)

    parts = raw.split(None, 1)
    trigger = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""
    return [trigger], rest


def filter_matches(trigger: str, message_text: str) -> bool:
    message_text = (message_text or "").lower()
    if trigger.startswith("exact:"):
        return message_text.strip() == trigger[len("exact:"):].strip()
    if trigger.startswith("prefix:"):
        return message_text.startswith(trigger[len("prefix:"):])
    return trigger in message_text


# ============================================================
#  REGISTER
# ============================================================

def register_moderation(app, load_db, save_db, is_user_admin, OWNER_ID,
                         DB_FILTERS, DB_NOTES, DB_WELCOME):

    async def require_admin(event, allow_private=True):
        if event.is_private:
            if allow_private:
                return True
            await event.reply("⚠️ Perintah ini cuma bisa dipakai di grup.")
            return False
        if not event.is_group:
            return False
        if event.sender_id != OWNER_ID and not await is_user_admin(app, event.chat_id, event.sender_id):
            await event.reply("⛔ Perintah ini hanya dapat dijalankan oleh Admin grup.")
            return False
        return True

    # ---------------- FILTERS ----------------

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!]filter(?:@\w+)?(?:\s+([\s\S]+))?$", re.I)))
    async def cmd_filter(event):
        if not await require_admin(event):
            return
        arg = event.pattern_match.group(1)
        reply = await event.get_reply_message()

        if not arg:
            return await event.reply(
                "⚠️ <b>Panduan Penggunaan Filter</b>\n\n"
                "• <code>/filter &lt;kata&gt; &lt;balasan&gt;</code>\n"
                "• <code>/filter \"frasa panjang\" balasan</code>\n"
                "• <code>/filter (hi, halo, hey) balasan</code>\n\n"
                "Balas pesan atau media dengan <code>/filter &lt;kata&gt;</code> untuk menyimpan balasan otomatis.",
                parse_mode="html"
            )

        triggers, rest = parse_filter_triggers(arg)
        if not triggers:
            return await event.reply("❌ Format filter tidak valid. Silakan periksa kembali.")

        chat_key = str(event.chat_id)
        db = load_db(DB_FILTERS)
        db.setdefault(chat_key, {})

        album_messages = await get_album_messages(event.client, reply)
        saved_reply = rest.strip()
        if not saved_reply:
            for m in album_messages:
                m_text = (m.text or m.message or "").strip()
                if m_text:
                    saved_reply = m_text
                    break

        if len(album_messages) > 1 and any(m.media for m in album_messages):
            safe_trig = re.sub(r'[^a-zA-Z0-9_-]', '_', triggers[0])[:20]
            saved_files = await save_media_from_messages(album_messages, chat_key, f"filter_{safe_trig}")
            entry = {
                "type": "album",
                "reply": saved_reply or None,
                "files": saved_files,
                "chat_id": reply.chat_id,
                "msg_ids": [m.id for m in album_messages]
            }
        elif reply and reply.media:
            safe_trig = re.sub(r'[^a-zA-Z0-9_-]', '_', triggers[0])[:20]
            local_path, is_voice, is_video_note = await save_media_from_message(reply, chat_key, f"filter_{safe_trig}")
            entry = {
                "type": "media",
                "reply": saved_reply or None,
                "file_path": local_path,
                "is_voice": is_voice,
                "is_video_note": is_video_note,
                "chat_id": reply.chat_id,
                "msg_id": reply.id
            }
        elif saved_reply:
            entry = {
                "type": "text",
                "reply": saved_reply,
                "chat_id": None,
                "msg_id": None
            }
        else:
            return await event.reply("❌ Balasannya mana? Kasih teks balasan atau reply ke pesan/media.")

        for t in triggers:
            db[chat_key][t] = entry
        save_db(DB_FILTERS, db)

        shown = ", ".join(f"<code>{html.escape(t)}</code>" for t in triggers)
        await event.reply(f"✅ Filter berhasil disimpan permanen untuk: {shown}", parse_mode="html")

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!]stopall(?:@\w+)?$", re.I)))
    async def cmd_stopall(event):
        if not await require_admin(event):
            return
        db = load_db(DB_FILTERS)
        chat_key = str(event.chat_id)
        for _, entry in db.get(chat_key, {}).items():
            delete_stored_media_files(entry)
        db[chat_key] = {}
        save_db(DB_FILTERS, db)
        scope = "grup ini" if event.is_group else "chat ini"
        await event.reply(f"🗑️ Semua filter di {scope} sudah dihapus.")

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!]stop(?:@\w+)?(?:\s+([\s\S]+))?$", re.I)))
    async def cmd_stop_filter(event):
        if not await require_admin(event):
            return
        arg = event.pattern_match.group(1)
        if not arg:
            return await event.reply("⚠️ Format: <code>/stop &lt;kata&gt;</code> atau <code>/stop \"frasa\"</code>", parse_mode="html")
        triggers, _ = parse_filter_triggers(arg.strip() + " x")
        if not triggers:
            return await event.reply("❌ Format perintah tidak valid. Contoh: <code>/stop kata</code>", parse_mode="html")
        trigger = triggers[0]

        db = load_db(DB_FILTERS)
        chat_key = str(event.chat_id)
        if trigger in db.get(chat_key, {}):
            entry = db[chat_key][trigger]
            delete_stored_media_files(entry)
            del db[chat_key][trigger]
            save_db(DB_FILTERS, db)
            await event.reply(f"🗑️ Filter <code>{html.escape(trigger)}</code> dihapus.", parse_mode="html")
        else:
            scope = "grup ini" if event.is_group else "chat ini"
            await event.reply(f"❌ Filter <code>{html.escape(trigger)}</code> tidak ditemukan di {scope}.", parse_mode="html")

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!]filters(?:@\w+)?$", re.I)))
    async def cmd_list_filters(event):
        if not event.is_group and not event.is_private:
            return
        db = load_db(DB_FILTERS)
        chat_filters = db.get(str(event.chat_id), {})
        scope = "grup ini" if event.is_group else "chat ini"
        if not chat_filters:
            return await event.reply(f"ℹ️ Belum ada filter di {scope}.")
        listing = "\n".join(f"• <code>{html.escape(t)}</code>" for t in sorted(chat_filters))
        await event.reply(f"📋 <b>Filter aktif di {scope}:</b>\n{listing}", parse_mode="html")

    # Auto-reply listener - HARUS didaftar belakangan & jangan nabrak command lain.
    @app.on(events.NewMessage())
    async def filter_autoreply(event):
        if (not event.is_group and not event.is_private) or not event.raw_text:
            return
        if re.match(r"^[/!#]", event.raw_text):
            return
        db = load_db(DB_FILTERS)
        chat_filters = db.get(str(event.chat_id), {})
        if not chat_filters:
            return
        for trigger, entry in chat_filters.items():
            if filter_matches(trigger, event.raw_text):
                chat = await event.get_chat()
                sender = await event.get_sender()

                if isinstance(entry, int):
                    # legacy format (entry = msg_id)
                    media_ref = {"chat_id": event.chat_id, "msg_id": entry}
                    text = None
                elif isinstance(entry, dict):
                    text = render_fillings(entry.get("reply"), sender, getattr(chat, "title", None))
                    media_ref = dict(entry) if entry.get("type") in ("media", "album") else None
                else:
                    text = str(entry)
                    media_ref = None

                try:
                    await send_stored_media_or_text(event, event.chat_id, text, media_ref, reply_to=event.id)
                except Exception as e:
                    logger.error(f"Gagal kirim balasan filter '{trigger}': {e}")
                break  # satu pesan cuma mancing 1 filter, biar gak spam kalo kena banyak match

    # ---------------- NOTES ----------------

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!]save(?:@\w+)?(?:\s+(\S+))?(?:\s+([\s\S]+))?$", re.I)))
    async def cmd_save_note(event):
        if not await require_admin(event):
            return
        name = event.pattern_match.group(1)
        rest = event.pattern_match.group(2) or ""
        reply = await event.get_reply_message()

        if not name:
            return await event.reply("⚠️ Format: <code>/save &lt;namanote&gt; &lt;isi&gt;</code> (atau balas pesan/media + <code>/save &lt;namanote&gt;</code>)", parse_mode="html")
        name = name.lower()
        if name.startswith("__"):
            return await event.reply("❌ Nama note tidak boleh diawali dengan garis bawah (__).")

        chat_key = str(event.chat_id)
        db = load_db(DB_NOTES)
        db.setdefault(chat_key, {})

        album_messages = await get_album_messages(event.client, reply)
        saved_text = rest.strip()
        if not saved_text:
            for m in album_messages:
                m_text = (m.text or m.message or "").strip()
                if m_text:
                    saved_text = m_text
                    break

        if len(album_messages) > 1 and any(m.media for m in album_messages):
            saved_files = await save_media_from_messages(album_messages, chat_key, f"note_{name}")
            db[chat_key][name] = {
                "type": "album",
                "text": saved_text or None,
                "files": saved_files,
                "chat_id": reply.chat_id,
                "msg_ids": [m.id for m in album_messages]
            }
        elif reply and reply.media:
            local_path, is_voice, is_video_note = await save_media_from_message(reply, chat_key, f"note_{name}")
            db[chat_key][name] = {
                "type": "media",
                "text": saved_text or None,
                "file_path": local_path,
                "is_voice": is_voice,
                "is_video_note": is_video_note,
                "chat_id": reply.chat_id,
                "msg_id": reply.id
            }
        elif saved_text:
            db[chat_key][name] = {
                "type": "text",
                "text": saved_text,
                "chat_id": None,
                "msg_id": None
            }
        else:
            return await event.reply("❌ Isi note-nya mana? Kasih teks atau reply ke pesan/media.")

        save_db(DB_NOTES, db)
        await event.reply(f"✅ Note <code>{html.escape(name)}</code> tersimpan permanen. Ambil lagi pakai <code>/get {html.escape(name)}</code> atau <code>#{html.escape(name)}</code>.", parse_mode="html")

    async def _deliver_note(event, name, silent_if_missing=False):
        db = load_db(DB_NOTES)
        chat_key = str(event.chat_id)
        chat_data = db.get(chat_key, {})
        clean_name = name.lower()

        if clean_name.startswith("__"):
            return

        reply_setting = chat_data.get("__settings__", {}).get("reply", True)

        note = chat_data.get(clean_name)
        if not note:
            if silent_if_missing or not reply_setting:
                return
            return await event.reply(f"❌ Note <code>{html.escape(name)}</code> tidak ditemukan.", parse_mode="html")

        chat = await event.get_chat()
        sender = await event.get_sender()
        text = render_fillings(note.get("text"), sender, getattr(chat, "title", None))
        media_ref = dict(note) if note.get("type") in ("media", "album") else None

        # Pengaturan reply: Jika membalas pesan user lain, reply ke pesan tersebut.
        # Jika tidak, cek apakah settings reply aktif (default: True).
        # Jika reply dinonaktifkan via /notereply off, kirim note tanpa reply_to (None).
        reply_msg = await event.get_reply_message()
        if reply_msg:
            target_reply_id = reply_msg.id
        elif reply_setting:
            target_reply_id = event.id
        else:
            target_reply_id = None

        await send_stored_media_or_text(event, event.chat_id, text, media_ref, reply_to=target_reply_id)

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!]get(?:@\w+)?\s+(\S+)$", re.I)))
    async def cmd_get_note(event):
        if not event.is_group and not event.is_private:
            return
        await _deliver_note(event, event.pattern_match.group(1), silent_if_missing=False)

    @app.on(events.NewMessage(pattern=r"^#(\S+)$"))
    async def cmd_hashtag_note(event):
        if not event.is_group and not event.is_private:
            return
        await _deliver_note(event, event.pattern_match.group(1), silent_if_missing=True)

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!]notes(?:@\w+)?$", re.I)))
    async def cmd_list_notes(event):
        if not event.is_group and not event.is_private:
            return
        db = load_db(DB_NOTES)
        chat_key = str(event.chat_id)
        chat_data = db.get(chat_key, {})
        filtered = [n for n in chat_data if not n.startswith("__")]
        reply_setting = chat_data.get("__settings__", {}).get("reply", True)
        scope = "grup ini" if event.is_group else "chat ini"

        if not filtered:
            if not reply_setting:
                return
            return await event.reply(f"ℹ️ Belum ada note di {scope}.")

        listing = "\n".join(f"• <code>#{html.escape(n)}</code>" for n in sorted(filtered))
        text = f"📋 <b>Note tersimpan di {scope}:</b>\n{listing}"
        if reply_setting:
            await event.reply(text, parse_mode="html")
        else:
            await app.send_message(event.chat_id, text, parse_mode="html")

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!]clear(?:@\w+)?\s+(\S+)$", re.I)))
    async def cmd_clear_note(event):
        if not await require_admin(event):
            return
        name = event.pattern_match.group(1).lower()
        if name.startswith("__"):
            return await event.reply("❌ Note tidak valid.")
        db = load_db(DB_NOTES)
        chat_key = str(event.chat_id)
        if name in db.get(chat_key, {}):
            note = db[chat_key][name]
            delete_stored_media_files(note)
            del db[chat_key][name]
            save_db(DB_NOTES, db)
            await event.reply(f"🗑️ Note <code>{html.escape(name)}</code> berhasil dihapus.", parse_mode="html")
        else:
            await event.reply(f"❌ Note <code>{html.escape(name)}</code> tidak ditemukan.", parse_mode="html")

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!](?:notereply|notesreply|notes?\s+reply)(?:@\w+)?(?:\s+(on|off))?$", re.I)))
    async def cmd_notereply(event):
        if not await require_admin(event):
            return
        arg = event.pattern_match.group(1)
        chat_key = str(event.chat_id)
        db = load_db(DB_NOTES)
        chat_data = db.setdefault(chat_key, {})
        settings = chat_data.setdefault("__settings__", {})

        if not arg:
            current_status = settings.get("reply", True)
            status_str = "AKTIF (membalas pesan pemanggil)" if current_status else "NONAKTIF (tanpa reply)"
            return await event.reply(
                f"ℹ️ Status Note Reply saat ini: <b>{status_str}</b>\n\n"
                "Gunakan <code>/notereply on</code> atau <code>/notereply off</code> untuk mengubahnya.",
                parse_mode="html"
            )

        new_val = (arg.lower() == "on")
        settings["reply"] = new_val
        save_db(DB_NOTES, db)
        if new_val:
            await event.reply("✅ Note Reply <b>diaktifkan</b>. Note akan membalas pesan pemanggil.", parse_mode="html")
        else:
            await event.reply("✅ Note Reply <b>dinonaktifkan</b>. Note akan dikirim langsung tanpa membalas pesan.", parse_mode="html")

    # ---------------- WELCOME ----------------

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!]welcome(?:@\w+)?(?:\s+(on|off|noformat))?$", re.I)))
    async def cmd_welcome_toggle(event):
        if not event.is_group:
            return await event.reply("⚠️ Perintah ini cuma bisa dipakai di grup.")
        arg = event.pattern_match.group(1)
        db = load_db(DB_WELCOME)
        chat_key = str(event.chat_id)
        entry = db.get(chat_key, {"enabled": True, "type": "text", "text": DEFAULT_WELCOME, "chat_id": None, "msg_id": None})

        if arg in ("on", "off"):
            if event.sender_id != OWNER_ID and not await is_user_admin(app, event.chat_id, event.sender_id):
                return await event.reply("⛔ Hanya Admin yang dapat mengubah pengaturan welcome.")
            entry["enabled"] = (arg == "on")
            db[chat_key] = entry
            save_db(DB_WELCOME, db)
            return await event.reply(f"✅ Welcome message berhasil di-{'aktifkan' if arg == 'on' else 'nonaktifkan'}.")

        noformat = (arg == "noformat")
        text = entry.get("text") or DEFAULT_WELCOME
        if noformat:
            return await event.reply(f"```\n{text}\n```", parse_mode="md")

        chat = await event.get_chat()
        sender = await event.get_sender()
        rendered = render_fillings(text, sender, getattr(chat, "title", None))
        media_ref = dict(entry) if entry.get("type") in ("media", "album") else None
        await send_stored_media_or_text(event, event.chat_id, rendered, media_ref)

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!]setwelcome(?:@\w+)?(?:\s+([\s\S]+))?$", re.I)))
    async def cmd_set_welcome(event):
        if not await require_admin(event, allow_private=False):
            return
        text = event.pattern_match.group(1)
        reply = await event.get_reply_message()

        db = load_db(DB_WELCOME)
        chat_key = str(event.chat_id)
        prev = db.get(chat_key, {})

        album_messages = await get_album_messages(event.client, reply)
        saved_text = (text or "").strip()
        if not saved_text:
            for m in album_messages:
                m_text = (m.text or m.message or "").strip()
                if m_text:
                    saved_text = m_text
                    break

        if len(album_messages) > 1 and any(m.media for m in album_messages):
            saved_files = await save_media_from_messages(album_messages, chat_key, "welcome")
            db[chat_key] = {
                "enabled": prev.get("enabled", True),
                "type": "album",
                "text": saved_text or None,
                "files": saved_files,
                "chat_id": reply.chat_id,
                "msg_ids": [m.id for m in album_messages]
            }
        elif reply and reply.media:
            local_path, is_voice, is_video_note = await save_media_from_message(reply, chat_key, "welcome")
            db[chat_key] = {
                "enabled": prev.get("enabled", True),
                "type": "media",
                "text": saved_text or None,
                "file_path": local_path,
                "is_voice": is_voice,
                "is_video_note": is_video_note,
                "chat_id": reply.chat_id,
                "msg_id": reply.id
            }
        elif saved_text:
            db[chat_key] = {
                "enabled": prev.get("enabled", True),
                "type": "text",
                "text": saved_text,
                "chat_id": None,
                "msg_id": None
            }
        else:
            return await event.reply(
                "⚠️ <b>Panduan Set Welcome</b>\n\n"
                "• Gunakan: <code>/setwelcome &lt;teks&gt;</code>\n"
                "• Atau balas pesan/media dengan <code>/setwelcome &lt;teks opsional&gt;</code>\n\n"
                "<b>Placeholder yang didukung:</b>\n"
                "<code>{first}</code>, <code>{last}</code>, <code>{fullname}</code>, <code>{username}</code>, <code>{mention}</code>, <code>{chatname}</code>, <code>{id}</code>",
                parse_mode="html"
            )

        save_db(DB_WELCOME, db)
        await event.reply("✅ Welcome message disimpan permanen.")

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!]resetwelcome(?:@\w+)?$", re.I)))
    async def cmd_reset_welcome(event):
        if not await require_admin(event, allow_private=False):
            return
        db = load_db(DB_WELCOME)
        chat_key = str(event.chat_id)
        prev = db.get(chat_key, {})
        delete_stored_media_files(prev)
        db[chat_key] = {"enabled": prev.get("enabled", True), "type": "text",
                         "text": DEFAULT_WELCOME, "chat_id": None, "msg_id": None}
        save_db(DB_WELCOME, db)
        await event.reply("✅ Welcome message dikembalikan ke default.")

    logger.info("✅ Moderation module (filters/notes/welcome) registered.")
