import os
import re
import json
import asyncio
import logging
import aiohttp
from typing import Dict, Any, List, Optional
from .aria2_dl import aria2_download

logger = logging.getLogger(__name__)

class TikTokScraper:
    """
    Scraper TikTok handal dengan arsitektur multi-engine:
    1. Primary: TikWM API (sangat cepat, mendukung video tanpa watermark dan photo slideshow/carousel).
    2. Fallback: yt-dlp (ekstraksi metadata lengkap termasuk description/caption dan download langsung).
    """
    def __init__(self, download_dir: str, cookie_file: Optional[str] = None):
        self.download_dir = download_dir
        self.cookie_file = cookie_file
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir, exist_ok=True)

    async def _resolve_redirect(self, url: str) -> str:
        """Follow redirects untuk link pendek vt.tiktok.com / vm.tiktok.com"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    resolved = str(resp.url)
                    logger.info(f"[TikTok] Resolved {url} -> {resolved}")
                    return resolved
        except Exception as e:
            logger.warning(f"[TikTok] Failed resolving redirect for {url}: {e}")
            return url

    async def _fetch_description_via_ytdlp(self, url: str) -> str:
        """Helper cepat untuk mengambil description/caption via yt-dlp jika API utama kosong"""
        try:
            cmd = ["yt-dlp", "--dump-json", "--no-warnings", url]
            if self.cookie_file and os.path.exists(self.cookie_file):
                cmd.extend(["--cookies", self.cookie_file])
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                meta = json.loads(stdout.decode('utf-8', errors='ignore'))
                return (meta.get("description") or meta.get("title") or "").strip()
        except Exception as e:
            logger.warning(f"[TikTok] Helper yt-dlp dump-json failed: {e}")
        return ""

    async def _download_via_ytdlp(self, url: str) -> dict:
        """Fallback engine menggunakan yt-dlp jika TikWM gagal atau API down"""
        logger.info(f"[TikTok] Trying fallback download via yt-dlp for {url}")
        try:
            out_template = os.path.join(self.download_dir, "tt_%(id)s.%(ext)s")
            cmd = [
                "yt-dlp",
                "-o", out_template,
                "--no-warnings",
                "--print-json",
                "--max-filesize", "100M",
                url
            ]
            if self.cookie_file and os.path.exists(self.cookie_file):
                cmd.extend(["--cookies", self.cookie_file])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='ignore')[:300] if stderr else "yt-dlp error"
                logger.error(f"[TikTok] yt-dlp download failed: {err_msg}")
                return {"success": False, "error": f"yt-dlp download failed: {err_msg}"}

            meta = {}
            if stdout:
                try:
                    meta = json.loads(stdout.decode('utf-8', errors='ignore'))
                except Exception:
                    pass

            post_id = str(meta.get("id") or "tiktok")
            author = meta.get("uploader") or meta.get("uploader_id") or "tiktok_user"
            caption = (meta.get("description") or meta.get("title") or "").strip()
            like_count = meta.get("like_count") or 0
            comment_count = meta.get("comment_count") or 0

            downloaded_files = []
            for fname in os.listdir(self.download_dir):
                if fname.startswith(f"tt_{post_id}") and not fname.endswith(".part") and not fname.endswith(".ytdl"):
                    full_p = os.path.join(self.download_dir, fname)
                    if os.path.getsize(full_p) > 0:
                        downloaded_files.append(full_p)

            if not downloaded_files:
                return {"success": False, "error": "File hasil download yt-dlp tidak ditemukan."}

            return {
                "success": True,
                "data": {
                    "username": author,
                    "caption": caption,
                    "like_count": like_count,
                    "reply_count": comment_count,
                    "downloaded_files": downloaded_files
                }
            }
        except Exception as e:
            logger.error(f"[TikTok] yt-dlp exception: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def download_post(self, url: str) -> dict:
        """
        Download video atau gambar carousel dari postingan TikTok dengan multi-engine.
        Returns:
            dict: { "success": bool, "data": {...}, "error": str }
        """
        resolved_url = await self._resolve_redirect(url)
        clean_url = resolved_url.split('?')[0] if '?' in resolved_url else resolved_url

        # --- Tier 1: TikWM API ---
        payload = None
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*"
        }

        # Coba request dengan parameter yang benar (query params dict & POST)
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            # 1. GET dengan query param url
            for target_url in [clean_url, resolved_url]:
                try:
                    async with session.get("https://www.tikwm.com/api/", params={"url": target_url, "hd": "1"}) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            if data.get("code") == 0 and data.get("data"):
                                payload = data["data"]
                                break
                except Exception as e:
                    logger.warning(f"[TikTok] TikWM GET failed for {target_url}: {e}")

            # 2. Jika belum dapat, coba POST
            if not payload:
                try:
                    async with session.post("https://www.tikwm.com/api/", data={"url": clean_url, "hd": 1}) as resp:
                        if resp.status == 200:
                            data = await resp.json(content_type=None)
                            if data.get("code") == 0 and data.get("data"):
                                payload = data["data"]
                except Exception as e:
                    logger.warning(f"[TikTok] TikWM POST failed: {e}")

        # Jika TikWM berhasil mendapatkan metadata
        if payload:
            post_id = str(payload.get("id") or payload.get("video_id") or "tiktok")
            author_data = payload.get("author", {})
            author = author_data.get("unique_id") or author_data.get("nickname") or "tiktok_user"

            # Ambil caption selengkap mungkin dari content_desc atau title
            title = (payload.get("title") or "").strip()
            content_desc = payload.get("content_desc")
            if isinstance(content_desc, list) and content_desc:
                desc_str = " ".join(str(x).strip() for x in content_desc if str(x).strip())
            else:
                desc_str = str(content_desc or "").strip()

            caption = desc_str if len(desc_str) > len(title) else title
            if not caption:
                caption = (payload.get("desc") or payload.get("text") or "").strip()

            # Kumpulkan media URLs (foto slideshow atau video)
            media_list = []
            images = payload.get("images")
            if images and isinstance(images, list) and len(images) > 0:
                for idx, img_url in enumerate(images):
                    if isinstance(img_url, str) and img_url.startswith("http"):
                        media_list.append((img_url, "jpg"))
            else:
                video_url = payload.get("hdplay") or payload.get("play") or payload.get("wmplay")
                if video_url:
                    if video_url.startswith("//"):
                        video_url = "https:" + video_url
                    media_list.append((video_url, "mp4"))

            if media_list:
                downloaded_files = []
                dl_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://www.tiktok.com/"
                }

                for idx, (m_url, ext) in enumerate(media_list):
                    file_path = f"{self.download_dir}/{post_id}_{idx}.{ext}"
                    ok = await aria2_download(m_url, file_path, headers=dl_headers)
                    if ok and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                        downloaded_files.append(file_path)
                    else:
                        logger.warning(f"[TikTok] Aria2 download failed for {m_url}, trying direct aiohttp...")
                        try:
                            async with aiohttp.ClientSession(headers=dl_headers) as dl_session:
                                async with dl_session.get(m_url) as r:
                                    if r.status == 200:
                                        with open(file_path, "wb") as f:
                                            f.write(await r.read())
                                        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                            downloaded_files.append(file_path)
                        except Exception as dl_err:
                            logger.error(f"[TikTok] Direct aiohttp download failed: {dl_err}")

                if downloaded_files:
                    # Jika caption masih kosong, coba ambil cepat via yt-dlp
                    if not caption:
                        caption = await self._fetch_description_via_ytdlp(clean_url)

                    like_count = payload.get("digg_count") or 0
                    comment_count = payload.get("comment_count") or 0

                    return {
                        "success": True,
                        "data": {
                            "username": author,
                            "caption": caption,
                            "like_count": like_count,
                            "reply_count": comment_count,
                            "downloaded_files": downloaded_files
                        }
                    }

        # --- Tier 2: Fallback ke yt-dlp jika TikWM gagal atau API bermasalah ---
        logger.warning(f"[TikTok] TikWM failed for {url}. Falling back to yt-dlp...")
        yt_res = await self._download_via_ytdlp(clean_url)
        if yt_res.get("success"):
            return yt_res

        return {
            "success": False,
            "error": "Gagal mengekstrak data dari TikTok (postingan privat, dihapus, atau server dibatasi)."
        }
