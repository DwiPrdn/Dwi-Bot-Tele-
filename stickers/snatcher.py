import os
import re
import json
import time
import shutil
import asyncio
import logging
import aiohttp
from typing import Optional, List, Tuple, Dict, Any

logger = logging.getLogger("StickerSnatcher")

# In-memory storage untuk pemilihan multimedia dari tautan sosial media
# session_id -> { "user_id": int, "user_name": str, "files": [str], "emoji": str, "created_at": float }
SNATCH_SESSIONS: Dict[str, Dict[str, Any]] = {}


class StickerSnatcher:
    """
    Service pembuat dan pengelola sticker pack Telegram (Static & Video WebM).
    Mendukung penambahan media langsung (foto, video, GIF, sticker) maupun
    ekstraksi multimedia dari tautan media sosial.
    """
    def __init__(self, bot_token: str, bot_username: str, temp_dir: str = "downloads/stickers"):
        self.bot_token = bot_token
        self.bot_username = (bot_username or "").lstrip("@")
        self.temp_dir = temp_dir
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        os.makedirs(self.temp_dir, exist_ok=True)

    async def upload_sticker_file(self, user_id: int, file_path: str, sticker_format: str) -> Optional[str]:
        """
        Upload file stiker ke Telegram Bot API (uploadStickerFile).
        Returns:
            file_id (str) jika berhasil, None jika gagal.
        """
        url = f"{self.api_url}/uploadStickerFile"
        data = aiohttp.FormData()
        data.add_field('user_id', str(user_id))
        data.add_field('sticker_format', sticker_format)

        content_type = 'image/png' if sticker_format == 'static' else 'video/webm'
        filename = f"sticker.{'png' if sticker_format == 'static' else 'webm'}"

        try:
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
            data.add_field('sticker', file_bytes, filename=filename, content_type=content_type)

            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=data) as resp:
                    res = await resp.json()
                    if res.get('ok'):
                        return res['result']['file_id']
                    else:
                        logger.error(f"[StickerSnatcher] uploadStickerFile failed: {res}")
                        return None
        except Exception as e:
            logger.error(f"[StickerSnatcher] Exception in uploadStickerFile: {e}", exc_info=True)
            return None

    async def get_sticker_set(self, name: str) -> Tuple[Optional[dict], bool]:
        """
        Ambil info sticker set berdasarkan nama pack.
        Returns:
            (sticker_set: Optional[dict], not_found: bool)
            - Jika pack ditemukan: (dict, False)
            - Jika pack belum pernah dibuat: (None, True)
            - Jika terjadi error API/koneksi: (None, False)
        """
        url = f"{self.api_url}/getStickerSet"
        for attempt in range(2):
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, params={'name': name}) as resp:
                        res = await resp.json()
                        if res.get('ok'):
                            return res['result'], False
                        desc = str(res.get('description', '')).upper()
                        if 'STICKERSET_INVALID' in desc:
                            return None, True
                        logger.warning(f"[StickerSnatcher] getStickerSet API response: {res}")
                        return None, False
            except Exception as e:
                logger.error(f"[StickerSnatcher] getStickerSet attempt {attempt+1} error: {e}")
                if attempt == 0:
                    await asyncio.sleep(1)
        return None, False

    async def create_new_sticker_set(
        self, user_id: int, name: str, title: str, sticker_file_id: str, emoji: str, sticker_format: str
    ) -> bool:
        """Buat pack stiker baru via createNewStickerSet."""
        url = f"{self.api_url}/createNewStickerSet"
        payload = {
            'user_id': user_id,
            'name': name,
            'title': title,
            'sticker_format': sticker_format,
            'stickers': json.dumps([{
                'sticker': sticker_file_id,
                'emoji_list': [emoji],
                'format': sticker_format
            }])
        }
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=payload) as resp:
                    res = await resp.json()
                    if res.get('ok'):
                        return True
                    logger.error(f"[StickerSnatcher] createNewStickerSet error: {res}")
                    return False
        except Exception as e:
            logger.error(f"[StickerSnatcher] Exception createNewStickerSet: {e}")
            return False

    async def add_sticker_to_set(
        self, user_id: int, name: str, sticker_file_id: str, emoji: str, sticker_format: str
    ) -> bool:
        """Tambahkan stiker ke pack yang sudah ada via addStickerToSet."""
        url = f"{self.api_url}/addStickerToSet"
        payload = {
            'user_id': user_id,
            'name': name,
            'sticker': json.dumps({
                'sticker': sticker_file_id,
                'emoji_list': [emoji],
                'format': sticker_format
            })
        }
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=payload) as resp:
                    res = await resp.json()
                    if res.get('ok'):
                        return True
                    logger.error(f"[StickerSnatcher] addStickerToSet error: {res}")
                    return False
        except Exception as e:
            logger.error(f"[StickerSnatcher] Exception addStickerToSet: {e}")
            return False

    def generate_pack_title(self, clean_name: str, pack_num: int) -> str:
        """
        Menyusun nama/judul pack stiker yang rapi dengan menyertakan username bot
        sebagai kredit resmi (maksimal 64 karakter sesuai aturan Telegram Bot API).
        Mendukung aksara Unicode penuh (Jawa, Arab, Kanji, Cyrillic, Latin).
        Contoh: "ꦫꦥ ꦮꦺꦴꦤ꧀ꦒ꧀ ꦗꦮꦶ's Stickers #1 by @Plendes_bot"
        """
        type_str = "Stickers"
        credit = f"by @{self.bot_username}" if self.bot_username else ""
        suffix = f"#{pack_num} {credit}".strip()

        overhead = len(f"'s {type_str} {suffix}")
        max_name_len = max(5, 64 - overhead)
        if len(clean_name) > max_name_len:
            clean_name = clean_name[:max_name_len].strip()

        title = f"{clean_name}'s {type_str} {suffix}"
        return title[:64].strip()

    async def set_sticker_set_title(self, name: str, title: str) -> bool:
        """Mengubah judul sticker set via setStickerSetTitle."""
        url = f"{self.api_url}/setStickerSetTitle"
        payload = {'name': name, 'title': title}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, data=payload) as resp:
                    res = await resp.json()
                    return res.get('ok', False)
        except Exception as e:
            logger.error(f"[StickerSnatcher] setStickerSetTitle error: {e}")
            return False

    async def convert_to_sticker(
        self, input_path: str, user_id: int, start_offset: float = 0.0
    ) -> Tuple[Optional[str], str]:
        """
        Konversi media apa pun (foto/gambar/video/GIF/live stiker) ke format WebM VP9 Telegram
        agar semua media tersimpan dalam 1 pack stiker gabungan (seperti bot @fStikBot).
        - Resolusi: Sisi terpanjang tepat 512px, sisi lain genap <= 512px.
        - Format warna: yuva420p (alpha/transparansi didukung penuh, mencegah glitch/layar merah).
        - Durasi: Tepat batas maksimum resmi stiker Telegram, yaitu 3.0 detik (3000 ms).
        - Ukuran: <= 256KB (batas resmi Telegram Bot API).
        - Frame rate: <= 30 FPS.
        Returns:
            (output_path, error_msg)
        """
        if not os.path.exists(input_path):
            return None, "File input tidak ditemukan."

        w, h = 512, 512
        is_video = False
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "json", input_path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            info = json.loads(stdout.decode())
            streams = info.get("streams", [])
            if streams:
                w = int(streams[0].get("width") or 512)
                h = int(streams[0].get("height") or 512)
        except Exception:
            pass

        ext = input_path.lower().split('.')[-1]
        temp_anim_input = None

        if ext in ['mp4', 'mov', 'webm', 'mkv', 'gif', 'avi', 'flv', 'wmv']:
            is_video = True
        elif ext in ['webp', 'png']:

            try:
                from PIL import Image
                with Image.open(input_path) as im:
                    if getattr(im, 'is_animated', False) and getattr(im, 'n_frames', 1) > 1:
                        is_video = True

                        temp_anim_input = os.path.join(self.temp_dir, f"temp_anim_{user_id}_{int(time.time()*1000)}.gif")
                        frames = []
                        durations = []
                        for i in range(im.n_frames):
                            im.seek(i)
                            frames.append(im.convert('RGBA'))
                            durations.append(im.info.get('duration', 100))
                        frames[0].save(temp_anim_input, save_all=True, append_images=frames[1:], duration=durations, loop=0)
            except Exception as e:
                logger.warning(f"[StickerSnatcher] PIL check animated error: {e}")

        if not is_video:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", input_path,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()
                dur_str = stdout.decode().strip()
                if dur_str and dur_str != "N/A":
                    try:
                        if float(dur_str) > 0.1:
                            is_video = True
                    except ValueError:
                        pass
            except Exception:
                pass

        if w >= h:
            tw = 512
            th = int(round(512 * h / max(1, w)))
            if th % 2 != 0:
                th += 1
            th = min(512, max(2, th))
        else:
            th = 512
            tw = int(round(512 * w / max(1, h)))
            if tw % 2 != 0:
                tw += 1
            tw = min(512, max(2, tw))

        out_name = f"snatch_{user_id}_{int(time.time() * 1000)}"
        output_file = os.path.join(self.temp_dir, f"{out_name}.webm")

        actual_input = temp_anim_input if (temp_anim_input and os.path.exists(temp_anim_input)) else input_path

        MAX_STICKER_DURATION = "3.0"

        if not is_video:

            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", actual_input,
                "-c:v", "libvpx-vp9",
                "-pix_fmt", "yuva420p",
                "-vf", f"scale={tw}:{th},fps=30",
                "-t", MAX_STICKER_DURATION,
                "-b:v", "150k",
                "-an",
                output_file
            ]
        else:

            cmd = ["ffmpeg", "-y"]
            if start_offset > 0:
                cmd.extend(["-ss", str(start_offset)])
            cmd.extend([
                "-i", actual_input,
                "-t", MAX_STICKER_DURATION,
                "-c:v", "libvpx-vp9",
                "-pix_fmt", "yuva420p",
                "-vf", f"scale={tw}:{th},fps=30",
                "-b:v", "180k",
                "-maxrate", "240k",
                "-bufsize", "450k",
                "-an",
                output_file
            ])

        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, stderr = await proc.communicate()
            if proc.returncode == 0 and os.path.exists(output_file) and os.path.getsize(output_file) > 0:

                if os.path.getsize(output_file) > 256 * 1024:
                    for target_br in ["120k", "90k", "60k", "40k"]:
                        lower_out = os.path.join(self.temp_dir, f"{out_name}_low.webm")
                        cmd_low = [
                            "ffmpeg", "-y", "-i", output_file,
                            "-c:v", "libvpx-vp9",
                            "-pix_fmt", "yuva420p",
                            "-b:v", target_br,
                            "-maxrate", target_br,
                            "-bufsize", "200k",
                            "-an", lower_out
                        ]
                        proc_low = await asyncio.create_subprocess_exec(*cmd_low, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                        await proc_low.communicate()
                        if os.path.exists(lower_out) and os.path.getsize(lower_out) <= 256 * 1024:
                            os.replace(lower_out, output_file)
                            break

                return output_file, ""
            return None, f"Gagal konversi ke WebM VP9: {stderr.decode()[:150]}"
        except Exception as e:
            return None, f"Error konversi stiker: {e}"
        finally:
            if temp_anim_input and os.path.exists(temp_anim_input):
                try:
                    os.remove(temp_anim_input)
                except Exception:
                    pass

    async def snatch_to_pack(
        self, user_id: int, user_first_name: str, input_media_path: str, emoji: str = "✨", start_offset: float = 0.0
    ) -> Tuple[bool, str, str, str]:
        """
        Mengonversi media (foto/video/live stiker) dan memasukkannya ke sticker pack tunggal pengguna.
        Durasi stiker disesuaikan dengan maksimum yang ditetapkan Telegram (3.0 detik).
        Returns:
            (success: bool, pack_name_or_error: str, pack_url: str, pack_title: str)
        """
        # 1. Konversi media ke WebM VP9 (maksimum 3.0 detik resmi Telegram)
        converted_file, err = await self.convert_to_sticker(input_media_path, user_id, start_offset=start_offset)
        if not converted_file:
            return False, err, "", ""

        sticker_format = "video"
        # Bersihkan karakter kontrol dan newline, tapi pertahankan huruf Unicode (Jawa, Arab, Kanji, dsb)
        clean_name = re.sub(r'[\r\n\t]+', ' ', user_first_name or '').strip()
        clean_name = "".join(ch for ch in clean_name if ch.isprintable()).strip()
        if not clean_name:
            clean_name = "User"

        try:
            # 2. Upload file stiker ke Telegram
            file_id = await self.upload_sticker_file(user_id, converted_file, sticker_format)
            if not file_id:
                return False, "Gagal mengunggah file stiker ke server Telegram.", "", ""

            # 3. Cari pack pengguna yang belum penuh (< 120 stiker)
            pack_num = 1
            chosen_pack_name = ""
            chosen_pack_title = ""
            pack_url = ""

            while pack_num <= 50:
                pack_name = f"pack_{user_id}_p{pack_num}_by_{self.bot_username}"
                expected_title = self.generate_pack_title(clean_name, pack_num)
                sticker_set, not_found = await self.get_sticker_set(pack_name)

                if not_found:

                    ok = await self.create_new_sticker_set(user_id, pack_name, expected_title, file_id, emoji, sticker_format)
                    if ok:
                        chosen_pack_name = pack_name
                        chosen_pack_title = expected_title
                        pack_url = f"https://t.me/addstickers/{pack_name}"
                        break
                    else:
                        return False, "Gagal membuat sticker pack baru.", "", ""
                elif sticker_set is None:

                    return False, "Gagal menghubungi Telegram untuk memeriksa status sticker pack.", "", ""
                else:

                    curr_title = sticker_set.get('title', '')
                    if curr_title != expected_title:
                        await self.set_sticker_set_title(pack_name, expected_title)
                        chosen_pack_title = expected_title
                    else:
                        chosen_pack_title = curr_title or expected_title

                    stickers = sticker_set.get('stickers', [])
                    if len(stickers) < 120:
                        ok = await self.add_sticker_to_set(user_id, pack_name, file_id, emoji, sticker_format)
                        if ok:
                            chosen_pack_name = pack_name
                            pack_url = f"https://t.me/addstickers/{pack_name}"
                            break
                        else:
                            return False, "Gagal menambahkan stiker ke pack yang ada.", "", ""
                    else:
                        pack_num += 1

            if not chosen_pack_name:
                return False, "Semua sticker pack kamu sudah penuh (maks 50 pack).", "", ""

            return True, chosen_pack_name, pack_url, chosen_pack_title

        finally:

            if converted_file and os.path.exists(converted_file):
                try:
                    os.remove(converted_file)
                except Exception:
                    pass
