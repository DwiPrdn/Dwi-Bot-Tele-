"""
verify.py

Gerbang verifikasi member baru berbasis AI (Gemini). Alur (v2 - DM based):

  1. Member baru join -> LANGSUNG di-mute total di grup (send_messages=False,
     tetep gitu sampe lolos) + dikirimin welcome message dengan tombol URL
     "Verify Here" yang deep-link ke DM bot (https://t.me/<bot>?start=verify_..).

     PENTING: ini WAJIB pake DM, bukan tombol inline di grup. Bot ini pake
     Bot API token (bukan userbot), dan Telegram gak ngasih bot proaktif
     nge-DM orang yang belom pernah /start bot itu duluan - satu2nya cara
     buka DM adalah user sendiri yang mencet deep-link. Lagipula user yang
     di-mute gak bisa ngetik apa2 di grup buat balesin pertanyaan verifikasi.

  2. User mencet "Verify Here" -> kebuka DM bot -> otomatis kekirim /start
     verify_<chatid>_<userid> -> bot nanya (Bahasa Inggris) bahasa apa yang
     mau dipake buat verifikasi, tombol Indonesian/English + "Other language".
  3a. Pilih Indo/English -> langsung dikasih pertanyaan random (Gemini-
      generated, beda tiap kali, dalam bahasa yang dipilih).
  3b. Pilih "Other language" -> user tinggal balas chat (di DM) pake bahasa
      yang dia mau, baru abis itu dikasih pertanyaan dalam bahasa itu.
  4. Jawaban dinilai Gemini (bukan exact-match, toleran ke variasi jawaban
     manusia). Bener -> di-unmute di GRUP asal, bisa chat. Salah -> pertanyaan
     baru, max 3x percobaan baru di-kick dari grup.
  5. Background sweep ngebuang member yang gak nyelesain verifikasi dalam
     waktu tertentu (default 5 menit, samain sama teks welcome-nya user) ->
     di-kick dari grup. Berbasis timestamp di DB, tahan restart bot.

Dipake sebagai drop-in dari main.py - DUA titik integrasi:

  1) Registrasi biasa:
        from verify import register_verify, verify_timeout_loop
        register_verify(app, load_db, save_db, is_user_admin, OWNER_ID,
                         GEMINI_KEYS, MODEL_NAME,
                         DB_VERIFY_SETTINGS, DB_VERIFY_PENDING, DB_WELCOME)
        ...
        app.loop.create_task(verify_timeout_loop(app, load_db, save_db, DB_VERIFY_PENDING))

  2) WAJIB juga disambungin ke handler /start yang UDAH ADA di main.py
     (biar /start verify_xxx gak kepotong sama handler /start umum), taro
     di paling atas fungsi cmd_start yang udah ada:

        from verify import handle_verify_deeplink
        ...
        @app.on(events.NewMessage(pattern=r'^[/!](start|help)'))
        async def cmd_start(event):
            parts = event.raw_text.split(None, 1)
            if len(parts) > 1 and parts[1].startswith("verify_"):
                if await handle_verify_deeplink(event, parts[1], app, load_db, save_db,
                                                 DB_VERIFY_PENDING, GEMINI_KEYS, MODEL_NAME):
                    return
            ... (kode /start yang lama, gak berubah)

SENGAJA gak reuse call_gemini() dari main.py - itu functionnya udah dipatok
buat persona AI-chat (Alya/Gavin + anti-jailbreak system prompt gede), yang
gak nyambung & bisa ngerecokin flow verifikasi keamanan ini. Di sini manggil
Gemini API langsung, system instruction sendiri, response dipaksa JSON pake
responseSchema biar gak perlu parsing teks bebas yang rapuh.
"""
import os
import re
import json
import time
import random
import logging
import aiohttp
from telethon import events, Button

try:
    from admins.moderation import render_fillings, send_stored_media_or_text, DEFAULT_WELCOME
except ImportError:
    from moderation import render_fillings, send_stored_media_or_text, DEFAULT_WELCOME

logger = logging.getLogger("Verify")

# Nge-generate pertanyaan itu stateless tiap panggilan - Gemini gak inget
# udah pernah nanya apa sebelumnya, jadi kalo cuma dikasih prompt polos dia
# gampang balik ke pola "aman" yang itu2 aja (kucing/apel/2+2). Buat maksa
# variasi: (1) kasih tema acak tiap panggilan, (2) kasih daftar pertanyaan
# yang barusan dipake biar model sengaja ngehindarin itu.
#
# List-nya DIPERSIST ke disk (bukan cuma in-memory) - soalnya kalo cuma
# in-memory, tiap kali bot di-restart (yang kejadian TERUS pas develop/testing
# begini) daftarnya ke-reset kosong, jadi kesannya "pertanyaannya itu2 mulu"
# padahal mekanismenya udah ada. Path-nya dipatok ke lokasi file verify.py
# sendiri (bukan relative ke cwd) - biar gak kena masalah working-directory
# pas jalan lewat systemd (sama kayak kasus debug_full.html dulu).
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_RECENT_Q_FILE = os.path.join(_MODULE_DIR, "verify_recent_questions.json")
_RECENT_CAP = 12
_RECENT_WELCOMES: dict = {}


def _load_recent_questions():
    try:
        with open(_RECENT_Q_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"Gagal baca recent-questions cache, mulai kosong: {e}")
    return []


def _save_recent_questions(lst):
    try:
        with open(_RECENT_Q_FILE, "w", encoding="utf-8") as f:
            json.dump(lst, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Gagal nyimpen recent-questions cache: {e}")


_recent_questions = _load_recent_questions()

TOPIC_HINTS = [
    "animals", "food and cooking", "family relationships", "weather and seasons",
    "colors", "counting and numbers", "clocks and time", "shapes", "money and prices",
    "sports and games", "household objects", "transportation", "school or work",
    "opposites", "simple sequences/patterns", "fruits and vegetables", "body parts",
    "days of the week", "music and instruments", "nature and plants",
]

MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 5 * 60   # 5 menit - samain ama teks welcome yg biasa lu pake
WARNING_SECONDS = 60      # kasih 1x warning pas sisa waktu segini
SWEEP_INTERVAL = 15       # cek member telat tiap 15 detik (biar warning & kick presisi)

QUESTION_SYSTEM_PROMPT = """You are a CAPTCHA question generator for a Telegram group anti-spam-bot gate.

Generate ONE short, simple, unambiguous question that:
- A real human (any background, casual chatter) can answer in a few seconds.
- Is genuinely hard for a dumb spam-join script to answer correctly without understanding meaning (i.e. NOT solvable by regex/keyword matching alone) - use everyday common sense, simple word-problem arithmetic, or "what comes next" style logic, NOT trivia that requires niche/specialist knowledge.
- Has ONE clear, short, unambiguous correct answer (a word, a short phrase, or a number).
- Is different each time you're asked - vary the topic/phrasing, don't reuse the same question pattern repeatedly. The user message may include a suggested theme and/or a list of recently-used questions to avoid - actually use the theme, and make sure your question is meaningfully different (not just reworded) from anything in that avoid-list.
- Avoid anything culturally, politically, religiously sensitive or offensive.
- Must be written ENTIRELY in the requested target language (translate/localize the question naturally, don't just append a translation).
- Plain text only - do NOT use markdown formatting (no *asterisks*, _underscores_, `backticks`, # headings, or any other styling).

Respond ONLY with the JSON object matching the given schema. "question" is what gets shown to the user. "answer_context" is a short internal note (in English, hidden from the user) describing what a correct answer must contain, so another model can later judge a free-text answer against it."""

JUDGE_SYSTEM_PROMPT = """You are a lenient answer-checker for a Telegram group CAPTCHA gate.

You will be given: the question that was asked, an internal note on what a correct answer requires, and the user's free-text reply. Decide if the user's reply demonstrates a genuine correct understanding.

Be LENIENT: accept typos, casual phrasing, partial sentences, answers in a different script/language than the question (as long as the meaning is right), and answers embedded in a longer sentence. Only mark it wrong if the core answer is actually incorrect, missing, or the message is clearly unrelated/gibberish/spam.

Respond ONLY with the JSON object matching the given schema."""


def _strip_markdown_noise(text: str) -> str:
    """Captcha question mestinya plain text - kadang Gemini nyelipin *emphasis*,
    `code`, atau # heading walau udah diinstruksiin jangan. Ini jaring pengaman
    biar apapun yang lolos tetep tampil bersih (ga ada tanda mentah keliatan)."""
    if not text:
        return text
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)
    text = re.sub(r'`{1,3}([^`]+)`{1,3}', r'\1', text)
    text = re.sub(r'(?m)^#{1,6}\s*', '', text)
    return text.strip()


TELEGRAM_MAX_LEN = 4096

async def _send_chunked(reply_target, text: str, **kwargs):
    """Kirim text ke Telegram - kalo lebih panjang dari batas satu pesan,
    pecah jadi beberapa pesan BERURUTAN (nyambung ke chat berikutnya) alih2
    kepotong/gagal kirim. Motongnya diusahain di batas baris/spasi biar ga
    motong di tengah kata."""
    limit = TELEGRAM_MAX_LEN - 100
    if len(text) <= limit:
        return await reply_target(text, **kwargs)

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind('\n', 0, limit)
        if cut == -1:
            cut = remaining.rfind(' ', 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()

    last = None
    for chunk in chunks:
        last = await reply_target(chunk, **kwargs)
    return last


async def _call_gemini_json(system_instruction: str, user_text: str, schema: dict, gemini_keys, model_name, temperature: float = 0.9):
    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "maxOutputTokens": 400,
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        }
    }
    async with aiohttp.ClientSession() as session:
        for key in gemini_keys:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
            try:
                async with session.post(url, json=payload, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw = data["candidates"][0]["content"]["parts"][0]["text"]
                        return json.loads(raw)
                    elif resp.status in (429, 500, 503):
                        continue
                    else:
                        logger.error(f"Gemini verify HTTP {resp.status}: {await resp.text()}")
                        return None
            except Exception as e:
                logger.warning(f"Gemini verify call gagal ({key[:10]}...): {e}")
                continue
    return None


async def generate_question(language: str, gemini_keys, model_name):
    schema = {
        "type": "OBJECT",
        "properties": {
            "question": {"type": "STRING"},
            "answer_context": {"type": "STRING"},
        },
        "required": ["question", "answer_context"],
    }

    topic = random.choice(TOPIC_HINTS)
    prompt = f"Target language for the question: {language}\nSuggested theme for inspiration (you may deviate): {topic}"
    if _recent_questions:
        avoid_list = "\n".join(f"- {q}" for q in _recent_questions[-8:])
        prompt += f"\n\nDo NOT repeat or closely resemble any of these recently-used questions - write something genuinely different:\n{avoid_list}"

    result = await _call_gemini_json(QUESTION_SYSTEM_PROMPT, prompt, schema, gemini_keys, model_name, temperature=1.3)
    if result and result.get("question"):
        question = _strip_markdown_noise(result["question"])
        _recent_questions.append(question)
        del _recent_questions[:-_RECENT_CAP]  # keep only the last _RECENT_CAP entries
        _save_recent_questions(_recent_questions)
        return question, result.get("answer_context", "")
    # Fallback kalo Gemini gagal/timeout - tetep ada pertanyaan, bukan nge-block orang gara2 API down
    return "2 + 2 = ?", "The answer must be 4 (in digits or words, any language)."


async def judge_answer(question: str, answer_context: str, user_answer: str, gemini_keys, model_name) -> bool:
    schema = {"type": "OBJECT", "properties": {"correct": {"type": "BOOLEAN"}}, "required": ["correct"]}
    prompt = f"Question asked: {question}\nWhat a correct answer requires: {answer_context}\nUser's reply: {user_answer}"
    result = await _call_gemini_json(JUDGE_SYSTEM_PROMPT, prompt, schema, gemini_keys, model_name, temperature=0.2)
    if result is None:
        return False  # API down -> jangan asal loloskan, biar user coba lagi
    return bool(result.get("correct", False))


def _pending_key(group_chat_id, user_id) -> str:
    return f"{group_chat_id}_{user_id}"


def _remaining_seconds(entry) -> int:
    elapsed = time.time() - entry.get("joined_at", time.time())
    return max(0, int(TIMEOUT_SECONDS - elapsed))


def _format_remaining(entry) -> str:
    remaining = _remaining_seconds(entry)
    minutes, seconds = divmod(remaining, 60)
    return f"{minutes}:{seconds:02d}"


def _find_active_entry(pending: dict, user_id: int):
    """Cari entry verifikasi yang lagi 'aktif' (udah mulai chat di DM, bukan
    yang masih nunggu diklik) buat user ini. Return (key, entry) atau (None, None).
    Kalo user kebetulan punya >1 verifikasi jalan bareng (join banyak grup
    sekaligus), ambil yang paling baru di-update."""
    candidates = []
    for key, entry in pending.items():
        if entry.get("user_id") == user_id and entry.get("stage") != "awaiting_start":
            candidates.append((key, entry))
    if not candidates:
        return None, None
    candidates.sort(key=lambda kv: kv[1].get("updated_at", 0), reverse=True)
    return candidates[0]


async def _send_welcome_with_verify_button(app, load_db, chat_id, user, DB_WELCOME, bot_username):
    db = load_db(DB_WELCOME)
    entry = db.get(str(chat_id), {"enabled": True, "type": "text", "text": DEFAULT_WELCOME, "chat_id": None, "msg_id": None})
    if not entry.get("enabled", True):
        text = DEFAULT_WELCOME
        media_ref = None
    else:
        text = entry.get("text") or DEFAULT_WELCOME
        media_ref = dict(entry) if entry.get("type") == "media" else None

    chat = await app.get_entity(chat_id)
    rendered = render_fillings(text, user, getattr(chat, "title", None))
    deep_link = f"https://t.me/{bot_username}?start=verify_{chat_id}_{user.id}"
    verify_btn = [[Button.url("✅ Verify Here", deep_link)]]
    await send_stored_media_or_text(app, chat_id, rendered, media_ref, buttons=verify_btn)


async def _ask_question(app, save_db, DB_VERIFY_PENDING, pending, key, entry, language,
                         GEMINI_KEYS, MODEL_NAME, reply_target):
    question, answer_context = await generate_question(language, GEMINI_KEYS, MODEL_NAME)
    entry["stage"] = "awaiting_answer"
    entry["language"] = language
    entry["question"] = question
    entry["answer_context"] = answer_context
    entry["updated_at"] = time.time()
    pending[key] = entry
    save_db(DB_VERIFY_PENDING, pending)

    text = f"[Attempt {entry['attempts'] + 1}/{MAX_ATTEMPTS}] ⏳ {_format_remaining(entry)} left before you're removed\n\n{question}\n\nJust reply here with your answer."
    try:
        await _send_chunked(reply_target, text)
    except Exception as e:
        logger.error(f"Gagal kirim pertanyaan verifikasi ({key}): {e}")


async def handle_verify_deeplink(event, payload, app, load_db, save_db, DB_VERIFY_PENDING, GEMINI_KEYS, MODEL_NAME):
    """Dipanggil dari handler /start yang UDAH ADA di main.py, buat payload
    'verify_<chatid>_<userid>'. Return True kalo payload ini valid & udah
    ditangani (jadi main.py gak usah lanjut ngirim /start umum lagi)."""
    if not event.is_private:
        return False
    try:
        rest = payload[len("verify_"):]
        chat_id_str, user_id_str = rest.rsplit("_", 1)
        group_chat_id, target_user_id = int(chat_id_str), int(user_id_str)
    except (ValueError, IndexError):
        return False

    if event.sender_id != target_user_id:
        await event.reply("⚠️ This verification link isn't for your account.")
        return True

    pending = load_db(DB_VERIFY_PENDING)
    key = _pending_key(group_chat_id, target_user_id)
    entry = pending.get(key)
    if not entry:
        await event.reply("ℹ️ No pending verification found for that group (it may have already expired or been completed).")
        return True

    entry["user_id"] = target_user_id
    entry["updated_at"] = time.time()

    if entry["stage"] == "awaiting_start":
        entry["stage"] = "awaiting_language"
        pending[key] = entry
        save_db(DB_VERIFY_PENDING, pending)
        buttons = [
            [Button.inline("🇮🇩 Indonesian", data=f"verifylang_id_{group_chat_id}_{target_user_id}"),
             Button.inline("🇬🇧 English", data=f"verifylang_en_{group_chat_id}_{target_user_id}")],
            [Button.inline("🌐 Other language", data=f"verifylang_other_{group_chat_id}_{target_user_id}")],
        ]
        await event.reply(
            f"👋 Let's verify you for **{entry.get('group_title', 'the group')}**.\n"
            f"⏳ You have **{_format_remaining(entry)}** left before you're removed from the group.\n\n"
            "Which language would you like to use for verification?\n"
            "Pick one below, or tap **Other language** and reply here with the language you'd like to use.",
            buttons=buttons, parse_mode="md"
        )
    elif entry["stage"] in ("awaiting_language", "awaiting_language_reply"):
        pending[key] = entry
        save_db(DB_VERIFY_PENDING, pending)
        await event.reply(f"You're already at the language step ({_format_remaining(entry)} left) - pick a button above, or just reply with your language.")
    elif entry["stage"] == "awaiting_answer":
        pending[key] = entry
        save_db(DB_VERIFY_PENDING, pending)
        await _send_chunked(event.reply, f"You already have a question waiting ({_format_remaining(entry)} left):\n\n{entry['question']}\n\nJust reply here with your answer.")
    return True


def register_verify(app, load_db, save_db, is_user_admin, OWNER_ID,
                     GEMINI_KEYS, MODEL_NAME,
                     DB_VERIFY_SETTINGS, DB_VERIFY_PENDING, DB_WELCOME):

    # ---------------- ADMIN TOGGLE (di grup) ----------------

    @app.on(events.NewMessage(pattern=re.compile(r"^[/!]verify(?:@\w+)?(?:\s+(on|off))?$", re.I)))
    async def cmd_verify_toggle(event):
        if not event.is_group:
            return
        arg = event.pattern_match.group(1)
        if not arg:
            db = load_db(DB_VERIFY_SETTINGS)
            enabled = db.get(str(event.chat_id), {}).get("enabled", False)
            return await event.reply(f"ℹ️ AI Verification saat ini: **{'AKTIF' if enabled else 'MATI'}**", parse_mode="md")

        if event.sender_id != OWNER_ID and not await is_user_admin(app, event.chat_id, event.sender_id):
            return await event.reply("⛔ Cuma admin yang bisa ubah setingan ini.")

        db = load_db(DB_VERIFY_SETTINGS)
        db[str(event.chat_id)] = {"enabled": (arg == "on")}
        save_db(DB_VERIFY_SETTINGS, db)
        await event.reply(
            f"✅ AI Verification member baru: **{'DIAKTIFKAN' if arg == 'on' else 'DIMATIKAN'}**.\n"
            + ("Member baru bakal di-mute total sampe lolos verifikasi lewat DM bot." if arg == "on" else ""),
            parse_mode="md"
        )

    # ---------------- NEW MEMBER JOIN ----------------

    @app.on(events.ChatAction)
    async def on_new_member(event):
        if not (event.user_joined or event.user_added):
            return
        chat_id = event.chat_id
        settings = load_db(DB_VERIFY_SETTINGS)
        verify_enabled = settings.get(str(chat_id), {}).get("enabled", False)

        try:
            users = await event.get_users()
        except Exception:
            users = []
        if not users:
            return

        me = await app.get_me()
        bot_username = me.username
        chat = await event.get_chat()
        group_title = getattr(chat, "title", None)

        now = time.time()
        # Bersihkan cache lama (> 60 detik)
        stale_keys = [k for k, ts in _RECENT_WELCOMES.items() if now - ts > 60]
        for k in stale_keys:
            _RECENT_WELCOMES.pop(k, None)

        valid_users = []
        seen_ids = set()
        for u in users:
            if not u or getattr(u, "bot", False) or u.id == me.id:
                continue
            if u.id in seen_ids:
                continue
            seen_ids.add(u.id)

            key = (chat_id, u.id)
            if now - _RECENT_WELCOMES.get(key, 0) < 20:
                logger.info(f"[on_new_member] Mengabaikan event join duplikat untuk user {u.id} di chat {chat_id}")
                continue
            _RECENT_WELCOMES[key] = now
            valid_users.append(u)

        if not valid_users:
            return

        if not verify_enabled:
            # Welcome reguler ketika verifikasi tidak aktif
            w_db = load_db(DB_WELCOME)
            w_entry = w_db.get(str(chat_id), {"enabled": True, "type": "text", "text": DEFAULT_WELCOME, "chat_id": None, "msg_id": None})
            if not w_entry.get("enabled", True):
                return
            text_tpl = w_entry.get("text") or DEFAULT_WELCOME
            media_ref = dict(w_entry) if w_entry.get("type") in ("media", "album") else None
            for user in valid_users:
                try:
                    rendered = render_fillings(text_tpl, user, group_title)
                    await send_stored_media_or_text(app, chat_id, rendered, media_ref)
                except Exception as e:
                    logger.error(f"Gagal kirim regular welcome buat {user.id} di {chat_id}: {e}")
            return

        # AI Verify aktif: mute member & kirim welcome dengan tombol verifikasi DM
        pending = load_db(DB_VERIFY_PENDING)
        for user in valid_users:
            try:
                await app.edit_permissions(chat_id, user.id, send_messages=False)
            except Exception as e:
                logger.warning(f"Gagal mute member baru {user.id} di {chat_id}: {e}")

            pending[_pending_key(chat_id, user.id)] = {
                "stage": "awaiting_start",
                "user_id": user.id,
                "group_chat_id": chat_id,
                "group_title": group_title,
                "language": None,
                "question": None,
                "answer_context": None,
                "attempts": 0,
                "joined_at": time.time(),
                "updated_at": time.time(),
            }
            try:
                await _send_welcome_with_verify_button(app, load_db, chat_id, user, DB_WELCOME, bot_username)
            except Exception as e:
                logger.error(f"Gagal kirim welcome+verify buat {user.id}: {e}")
        save_db(DB_VERIFY_PENDING, pending)

    # ---------------- CALLBACK: pilih bahasa (di DM) ----------------

    @app.on(events.CallbackQuery(pattern=rb"^verifylang_(id|en|other)_(-?\d+)_(\d+)$"))
    async def cb_verify_lang(event):
        choice = event.pattern_match.group(1).decode()
        group_chat_id = int(event.pattern_match.group(2))
        user_id = int(event.pattern_match.group(3))
        if event.sender_id != user_id:
            return await event.answer("This verification isn't for you.", alert=True)

        pending = load_db(DB_VERIFY_PENDING)
        key = _pending_key(group_chat_id, user_id)
        entry = pending.get(key)
        if not entry or entry["stage"] != "awaiting_language":
            return await event.answer("Nothing to verify right now.", alert=True)

        if choice == "other":
            entry["stage"] = "awaiting_language_reply"
            entry["updated_at"] = time.time()
            pending[key] = entry
            save_db(DB_VERIFY_PENDING, pending)
            return await event.edit("Alright! Please reply here with the language you'd like to use.")

        language = "Indonesian" if choice == "id" else "English"
        await event.edit(f"Language set to **{language}**. Generating your question...", parse_mode="md")
        await _ask_question(app, save_db, DB_VERIFY_PENDING, pending, key, entry, language,
                             GEMINI_KEYS, MODEL_NAME, reply_target=event.respond)

    # ---------------- Pesan biasa DI DM: bahasa custom / jawaban ----------------

    @app.on(events.NewMessage())
    async def verify_dm_listener(event):
        if not event.is_private or not event.raw_text:
            return
        if event.raw_text.startswith("/"):
            return  # /start dkk ditangani terpisah, jangan ke-eat di sini

        pending = load_db(DB_VERIFY_PENDING)
        key, entry = _find_active_entry(pending, event.sender_id)
        if not entry:
            return

        if entry["stage"] == "awaiting_language_reply":
            language = event.raw_text.strip()[:50]
            await _ask_question(app, save_db, DB_VERIFY_PENDING, pending, key, entry, language,
                                 GEMINI_KEYS, MODEL_NAME, reply_target=event.reply)
            return

        if entry["stage"] == "awaiting_answer":
            correct = await judge_answer(entry["question"], entry["answer_context"], event.raw_text, GEMINI_KEYS, MODEL_NAME)
            pending = load_db(DB_VERIFY_PENDING)  # re-load, jaga2 kalo keubah pas nunggu Gemini
            entry = pending.get(key)
            if not entry or entry["stage"] != "awaiting_answer":
                return
            group_chat_id = entry["group_chat_id"]

            if correct:
                del pending[key]
                save_db(DB_VERIFY_PENDING, pending)
                unmute_ok = False
                debug_err = None
                try:
                    group_entity = None
                    try:
                        group_entity = await app.get_entity(group_chat_id)
                    except Exception as e:
                        logger.warning(f"get_entity({group_chat_id}) gagal, coba pake ID mentah: {e}")
                    target = group_entity if group_entity is not None else group_chat_id
                    try:
                        await app.edit_permissions(
                            target,
                            event.sender_id,
                            send_messages=True,
                            send_media=True,
                            send_stickers=True,
                            send_gifs=True,
                            send_games=True,
                            send_inline=True,
                            embed_link_previews=True,
                            send_polls=True
                        )
                        unmute_ok = True
                    except Exception as e:
                        logger.error(f"edit_permissions gagal buat {event.sender_id} di {group_chat_id}: {e}", exc_info=True)
                        debug_err = f"{type(e).__name__}: {e}"
                except Exception as e:
                    debug_err = str(e)

                if unmute_ok:
                    return await event.reply(f"✅ Correct! You're verified for **{entry.get('group_title', 'the group')}** - you can now return and chat in the group.", parse_mode="md")
                else:
                    return await event.reply(
                        f"✅ Correct! But I couldn't automatically unmute you in **{entry.get('group_title', 'the group')}**.\n\n"
                        f"`{debug_err}`\n\n"
                        "Please ping a group admin to unmute you manually for now.",
                        parse_mode="md"
                    )

            entry["attempts"] += 1
            if entry["attempts"] >= MAX_ATTEMPTS:
                del pending[key]
                save_db(DB_VERIFY_PENDING, pending)
                try:
                    group_entity = None
                    try:
                        group_entity = await app.get_entity(group_chat_id)
                    except Exception:
                        pass
                    target = group_entity if group_entity is not None else group_chat_id
                    await app.kick_participant(target, event.sender_id)
                    return await event.reply("❌ Incorrect. You've used all your attempts and were removed from the group. Feel free to rejoin and try again.")
                except Exception as e:
                    logger.error(f"Gagal kick {event.sender_id} dari {group_chat_id} abis gagal verifikasi: {e}", exc_info=True)
                    return await event.reply(
                        f"❌ Incorrect, and you've used all your attempts. I tried to remove you but hit an error on my end.\n\n"
                        f"`{type(e).__name__}: {e}`\n\n"
                        "A group admin will need to handle this manually for now."
                    )

            pending[key] = entry
            save_db(DB_VERIFY_PENDING, pending)
            await event.reply(f"❌ Not quite. Let's try another question ({entry['attempts']}/{MAX_ATTEMPTS} failed attempts).")
            await _ask_question(app, save_db, DB_VERIFY_PENDING, pending, key, entry, entry["language"],
                                 GEMINI_KEYS, MODEL_NAME, reply_target=event.respond)

    logger.info("✅ Verify module (AI join gate, DM-based) registered.")


async def verify_timeout_loop(app, load_db, save_db, DB_VERIFY_PENDING):
    import asyncio
    await asyncio.sleep(15)
    logger.info("⚡ Background Task: Verify timeout sweeper aktif.")
    while True:
        try:
            pending = load_db(DB_VERIFY_PENDING)
            now = time.time()
            changed = False
            for key, entry in list(pending.items()):
                remaining = TIMEOUT_SECONDS - (now - entry.get("joined_at", now))
                user_id = entry.get("user_id")
                group_chat_id = entry.get("group_chat_id")

                if remaining <= 0:
                    if group_chat_id is not None and user_id is not None:
                        try:
                            group_entity = None
                            try:
                                group_entity = await app.get_entity(group_chat_id)
                            except Exception:
                                pass
                            target = group_entity if group_entity is not None else group_chat_id
                            await app.kick_participant(target, user_id)
                            logger.info(f"⏰ Kick {user_id} dari {group_chat_id} - telat nyelesain verifikasi.")
                            try:
                                await app.send_message(user_id, f"⏰ Time's up - you didn't finish verifying in time and were removed from **{entry.get('group_title', 'the group')}**. Feel free to rejoin and try again.", parse_mode="md")
                            except Exception:
                                pass  # gapapa kalo gagal DM, yang penting kick-nya jalan
                        except Exception as e:
                            logger.warning(f"Gagal kick telat-verifikasi buat {key}: {e}", exc_info=True)
                    del pending[key]
                    changed = True

                elif remaining <= WARNING_SECONDS and not entry.get("warned"):
                    entry["warned"] = True
                    pending[key] = entry
                    changed = True
                    if user_id is not None:
                        try:
                            await app.send_message(user_id, f"⚠️ Only **{_format_remaining(entry)}** left to finish verifying, or you'll be removed from the group!", parse_mode="md")
                        except Exception:
                            pass

            if changed:
                save_db(DB_VERIFY_PENDING, pending)
        except Exception as e:
            logger.error(f"verify_timeout_loop error: {e}", exc_info=True)
        await asyncio.sleep(SWEEP_INTERVAL)
