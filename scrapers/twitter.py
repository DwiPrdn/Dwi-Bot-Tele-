import os
import re
import math
import asyncio
import logging
import aiohttp
from typing import Dict, Any, List, Optional, Tuple
from .aria2_dl import aria2_download

logger = logging.getLogger(__name__)

class TwitterScraper:
    """
    Scraper Twitter / X handal menggunakan:
    1. Primary: Official Twitter Syndication CDN API (cepat, resmi, tanpa rate-limit)
    2. Fallback 1: VxTwitter API
    3. Fallback 2: FixTweet / FxTwitter API
    Mendukung multi-foto, video MP4 kualitas tertinggi, dan GIF animasi.
    """
    def __init__(self, download_dir: str, cookie_file: Optional[str] = None):
        self.download_dir = download_dir
        self.cookie_file = cookie_file
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir, exist_ok=True)

    @staticmethod
    def extract_tweet_id(url: str) -> Optional[str]:
        """Ekstrak ID tweet dari berbagai format URL twitter/x."""
        match = re.search(r'status/(\d+)', url)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _compute_syndication_token(tweet_id: str) -> str:
        """Hitung token matematis untuk Twitter syndication CDN API."""
        try:
            val = (float(tweet_id) / 1e15) * math.pi
            chars = '0123456789abcdefghijklmnopqrstuvwxyz'
            int_part = int(val)
            frac_part = val - int_part
            if int_part == 0:
                s = '0'
            else:
                digits = []
                n = int_part
                while n > 0:
                    digits.append(chars[n % 36])
                    n //= 36
                s = ''.join(reversed(digits))
            s += '.'
            for _ in range(16):
                frac_part *= 36
                d = int(frac_part)
                s += chars[d]
                frac_part -= d
            token = re.sub(r'[0.]+', '', s)
            return token or "1"
        except Exception:
            return "1"

    async def _fetch_syndication(self, tweet_id: str) -> Optional[dict]:
        """Fetch tweet data from official Twitter syndication CDN."""
        token = self._compute_syndication_token(tweet_id)
        url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token={token}&lang=en"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://platform.twitter.com"
        }
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if data and (data.get("text") is not None or data.get("mediaDetails")):
                            return data
        except Exception as e:
            logger.warning(f"[Twitter] Syndication API failed for {tweet_id}: {e}")
        return None

    async def _fetch_vxtwitter(self, tweet_id: str) -> Optional[dict]:
        """Fetch tweet data from VxTwitter API."""
        url = f"https://api.vxtwitter.com/Twitter/status/{tweet_id}"
        headers = {
            "User-Agent": "curl/8.5.0",
            "Accept": "application/json"
        }
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if data and data.get("text") is not None:
                            return data
        except Exception as e:
            logger.warning(f"[Twitter] VxTwitter API failed for {tweet_id}: {e}")
        return None

    async def _fetch_fxtwitter(self, tweet_id: str) -> Optional[dict]:
        """Fetch tweet data from FxTwitter API."""
        url = f"https://api.fxtwitter.com/Twitter/status/{tweet_id}"
        headers = {
            "User-Agent": "TelegramBot (like TwitterBot)",
            "Accept": "application/json"
        }
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if data.get("code") == 200 and data.get("tweet"):
                            return data.get("tweet")
        except Exception as e:
            logger.warning(f"[Twitter] FxTwitter API failed for {tweet_id}: {e}")
        return None

    async def download_post(self, url: str) -> dict:
        """
        Download media dari link X/Twitter.
        Returns:
            dict: { "success": bool, "data": {...}, "error": str }
        """
        tweet_id = self.extract_tweet_id(url)
        if not tweet_id:
            return {"success": False, "error": "ID tweet tidak valid atau tidak ditemukan dalam URL."}

        author = "twitter_user"
        caption = ""
        like_count = 0
        reply_count = 0
        media_items: List[Tuple[str, str]] = [] # list of (url, ext)

        # 1. Coba Twitter Syndication CDN API
        data_syn = await self._fetch_syndication(tweet_id)
        if data_syn:
            author = data_syn.get("user", {}).get("screen_name") or data_syn.get("user", {}).get("name") or "twitter_user"
            caption = data_syn.get("text") or ""
            like_count = data_syn.get("favorite_count") or 0

            # Media details
            media_details = data_syn.get("mediaDetails") or []
            for media in media_details:
                m_type = media.get("type")
                if m_type == "photo":
                    img_url = media.get("media_url_https")
                    if img_url:
                        # Dapatkan resolusi penuh
                        if "?" in img_url:
                            img_url = img_url.split("?")[0] + "?name=orig"
                        else:
                            img_url = img_url + "?name=orig"
                        media_items.append((img_url, "jpg"))
                elif m_type in ("video", "animated_gif"):
                    variants = media.get("video_info", {}).get("variants", [])
                    mp4_variants = [v for v in variants if v.get("content_type") == "video/mp4"]
                    if mp4_variants:
                        # Urutkan berdasarkan bitrate tertinggi
                        mp4_variants.sort(key=lambda x: x.get("bitrate", 0), reverse=True)
                        best_vid = mp4_variants[0].get("url")
                        if best_vid:
                            media_items.append((best_vid, "mp4"))

            # Fallback jika mediaDetails kosong tapi ada photos / video
            if not media_items:
                photos = data_syn.get("photos") or []
                for p in photos:
                    p_url = p.get("url")
                    if p_url:
                        media_items.append((p_url, "jpg"))
                vid = data_syn.get("video")
                if vid:
                    variants = vid.get("variants") or []
                    mp4_variants = [v for v in variants if v.get("content_type") == "video/mp4"]
                    if mp4_variants:
                        mp4_variants.sort(key=lambda x: x.get("bitrate", 0), reverse=True)
                        media_items.append((mp4_variants[0].get("url"), "mp4"))

        # 2. Jika syndication tidak punya media atau gagal, coba VxTwitter
        if not media_items:
            logger.info(f"[Twitter] Media not found via syndication, trying VxTwitter for {tweet_id}...")
            data_vx = await self._fetch_vxtwitter(tweet_id)
            if data_vx:
                author = data_vx.get("user_screen_name") or author
                caption = data_vx.get("text") or caption
                like_count = data_vx.get("likes") or like_count
                reply_count = data_vx.get("replies") or reply_count

                media_ext = data_vx.get("media_extended") or []
                for m in media_ext:
                    m_type = m.get("type")
                    m_url = m.get("url")
                    if m_url:
                        ext = "mp4" if m_type in ("video", "gif") else "jpg"
                        media_items.append((m_url, ext))

                if not media_items and data_vx.get("mediaURLs"):
                    for m_url in data_vx["mediaURLs"]:
                        ext = "mp4" if ".mp4" in m_url.lower() else "jpg"
                        media_items.append((m_url, ext))

        # 3. Jika masih belum ada, coba FxTwitter
        if not media_items:
            logger.info(f"[Twitter] Media not found via VxTwitter, trying FxTwitter for {tweet_id}...")
            data_fx = await self._fetch_fxtwitter(tweet_id)
            if data_fx:
                author = data_fx.get("author", {}).get("screen_name") or author
                caption = data_fx.get("text") or caption
                like_count = data_fx.get("likes") or like_count
                reply_count = data_fx.get("replies") or reply_count

                fx_media = data_fx.get("media", {})
                all_media = fx_media.get("all") or (fx_media.get("photos", []) + fx_media.get("videos", []))
                for m in all_media:
                    m_url = m.get("url")
                    m_type = m.get("type")
                    if m_url:
                        ext = "mp4" if m_type in ("video", "gif") else "jpg"
                        media_items.append((m_url, ext))

        if not media_items:
            return {
                "success": False,
                "error": "Tidak ditemukan foto atau video di postingan Twitter/X ini (hanya teks atau link luar)."
            }

        # Download media files
        downloaded_files = []
        dl_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://x.com/"
        }

        for idx, (m_url, ext) in enumerate(media_items):
            file_path = f"{self.download_dir}/{tweet_id}_{idx}.{ext}"
            ok = await aria2_download(m_url, file_path, headers=dl_headers)
            if ok and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                downloaded_files.append(file_path)
            else:
                logger.warning(f"[Twitter] Aria2 download failed for {m_url}, trying direct aiohttp...")
                try:
                    async with aiohttp.ClientSession(headers=dl_headers) as dl_session:
                        async with dl_session.get(m_url) as r:
                            if r.status == 200:
                                with open(file_path, "wb") as f:
                                    f.write(await r.read())
                                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                    downloaded_files.append(file_path)
                except Exception as dl_err:
                    logger.error(f"[Twitter] Direct aiohttp download failed: {dl_err}")

        if not downloaded_files:
            return {
                "success": False,
                "error": "Gagal mengunduh semua media dari postingan Twitter/X ini."
            }

        return {
            "success": True,
            "data": {
                "username": author,
                "caption": caption,
                "like_count": like_count,
                "reply_count": reply_count,
                "downloaded_files": downloaded_files
            }
        }
