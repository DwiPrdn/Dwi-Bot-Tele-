import os
import re
import json
import logging
import asyncio
import random
import time
import html as html_lib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import urlparse, unquote
import aiohttp
from bs4 import BeautifulSoup
from .aria2_dl import aria2_download

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("FacebookScraper")

MOBILE_USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36",
]

DESKTOP_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
]


class FacebookScraperException(Exception):
    pass


class PostNotFoundException(FacebookScraperException):
    pass


class ParsingException(FacebookScraperException):
    pass


@dataclass
class MediaItem:
    type: str  # "VIDEO" or "IMAGE"
    url: str
    width: int = 0
    height: int = 0


@dataclass
class FacebookPostData:
    post_id: str
    shortcode: str
    username: str
    user_pic: Optional[str]
    caption: str
    posted_at: int
    like_count: int
    reply_count: int
    media_type: str
    media_items: List[MediaItem]
    downloaded_files: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FacebookScraper:
    """
    Pure native Python scraper untuk video, reels, dan foto Facebook.
    Tanpa library eksternal tambahan (hanya aiohttp, BeautifulSoup, aria2_dl).
    Mendukung video & postingan foto/gambar.
    Mencegah bug 'scraping media acak dari sidebar/feed' dengan:
    1. Validasi ketat target ID & deteksi redirect login/feed.
    2. Ekstraksi spesifik OpenGraph video/image head metadata dari m.facebook.com.
    3. Filter ketat terhadap asset gambar UI statis (logo, emoji, avatar, icon).
    """

    def __init__(self, download_dir: str = "./downloads/facebook", max_concurrent_downloads: int = 5):
        self.download_dir = download_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
        os.makedirs(self.download_dir, exist_ok=True)

    def extract_id(self, url: str) -> Optional[str]:
        """Ekstrak ID video, reel, post, atau photo dari format URL Facebook."""
        decoded_url = unquote(url)

        # 1. Format path numerik umum (/videos/123, /reel/123, /posts/123, /photos/123)
        m = re.search(r'/(?:videos|reel|posts|photo|photos)/(\d+)', decoded_url)
        if m:
            return m.group(1)

        # 2. Format query parameter (?v=123, ?fbid=123, ?story_fbid=123)
        m_v = re.search(r'[?&](?:v|fbid|story_fbid)=(\d+)', decoded_url)
        if m_v:
            return m_v.group(1)

        # 3. Format share links (/share/r/123, /share/v/123, /share/p/123, fb.watch/123)
        m_s = re.search(r'/(?:share/(?:r|v|p)|fb\.watch)/([a-zA-Z0-9_-]+)', decoded_url)
        if m_s:
            cand = m_s.group(1)
            if cand not in ('watch', 'reel', 'videos', 'posts', 'photos', 'login', 'share'):
                return cand

        # 4. Fallback path inspection
        parsed = urlparse(decoded_url)
        parts = [p for p in parsed.path.strip('/').split('/') if p]
        if parts:
            for p in reversed(parts):
                if p.isdigit():
                    return p
            cand = parts[-1].split('?')[0]
            if cand not in ('watch', 'reel', 'videos', 'posts', 'photos', 'login', 'share', 'home', 'feed'):
                return cand

        return None

    def _to_mobile_url(self, url: str) -> str:
        """Konversi URL Facebook ke versi mobile (m.facebook.com) yang bersih dari script bloat."""
        clean = url.replace("https://www.facebook.com", "https://m.facebook.com")
        clean = clean.replace("http://www.facebook.com", "https://m.facebook.com")
        clean = clean.replace("https://web.facebook.com", "https://m.facebook.com")
        clean = clean.replace("http://web.facebook.com", "https://m.facebook.com")
        clean = clean.replace("https://facebook.com", "https://m.facebook.com")
        clean = clean.replace("http://facebook.com", "https://m.facebook.com")
        return clean

    async def _resolve_and_fetch_html(self, url: str) -> Tuple[str, str]:
        """
        Resolve link pendek fb.watch / share link dan ambil konten HTML.
        Mencoba mobile endpoint terlebih dahulu, fallback ke desktop jika diperlukan.
        Returns: (final_resolved_url, html_content)
        """
        mobile_url = self._to_mobile_url(url)
        headers_mobile = {
            "User-Agent": random.choice(MOBILE_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1"
        }

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(headers=headers_mobile, timeout=timeout) as session:
                async with session.get(mobile_url, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    logger.info(f"[Facebook] Resolved {url} -> {final_url} (HTTP {resp.status})")
                    if resp.status == 200:
                        html_text = await resp.text()
                        return final_url, html_text
                    elif resp.status == 404:
                        raise PostNotFoundException("Postingan/video Facebook tidak ditemukan atau telah dihapus.")
        except PostNotFoundException:
            raise
        except Exception as e:
            logger.warning(f"[Facebook] Mobile fetch gagal ({e}), mencoba desktop endpoint...")

        # Fallback desktop fetch
        headers_desktop = {
            "User-Agent": random.choice(DESKTOP_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1"
        }
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(headers=headers_desktop, timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    final_url = str(resp.url)
                    if resp.status == 404:
                        raise PostNotFoundException("Postingan/video Facebook tidak ditemukan atau disetel privat.")
                    if resp.status not in (200, 301, 302):
                        raise FacebookScraperException(f"Gagal mengakses Facebook. HTTP Status: {resp.status}")
                    html_text = await resp.text()
                    return final_url, html_text
        except (PostNotFoundException, FacebookScraperException):
            raise
        except Exception as e:
            raise FacebookScraperException(f"Koneksi ke Facebook bermasalah: {str(e)}")

    def _clean_author(self, raw_author: str, raw_title: str) -> str:
        """Membersihkan nama pembuat/halaman Facebook agar tidak tertukar dengan view count / reaction count."""
        view_reaction_pattern = r'\b\d+(\.\d+)?[KM]?\s*(views|reactions|shares|likes|comments|tayangan|suka)\b'
        if re.search(view_reaction_pattern, raw_author, re.IGNORECASE):
            raw_author = ""

        if not raw_author and raw_title:
            clean_t = re.sub(r'\s*\|\s*Facebook$', '', raw_title, flags=re.IGNORECASE).strip()
            parts = [p.strip() for p in clean_t.split('|') if p.strip()]
            for p in reversed(parts):
                if not re.search(view_reaction_pattern, p, re.IGNORECASE) and 1 < len(p) < 60:
                    raw_author = p
                    break

        return raw_author or "Facebook Creator"

    def _clean_media_url(self, raw_url: str) -> str:
        """Membersihkan URL media dari entity escape dan backslash."""
        u = raw_url.replace('\\/', '/').replace('&amp;', '&').strip()
        try:
            u = u.encode('utf-8').decode('unicode-escape', errors='ignore')
        except Exception:
            pass
        return u.replace('\\/', '/').replace('&amp;', '&')

    def _is_static_asset(self, url: str) -> bool:
        """Mendeteksi apakah URL gambar adalah aset statis/logo/icon Facebook bukan konten postingan."""
        u_lower = url.lower()
        bad_keywords = [
            "static.xx.fbcdn.net", "rsrc.php", "logos", "app_icon",
            "emoji.php", "blank.gif", "external.xx.fbcdn.net",
            "p50x50", "p100x100", "s50x50", "s100x100", "favicon"
        ]
        return any(b in u_lower for b in bad_keywords)

    def _extract_media(self, html_content: str, target_id: Optional[str]) -> Tuple[List[MediaItem], str]:
        """
        Ekstraksi media native (Video & Foto) dengan verifikasi ketat.
        Menghindari konten liar dari feed rekomendasi umum atau halaman login.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Validasi Halaman: Jangan scrape jika dilempar ke feed rekomendasi / login umum!
        og_url = soup.find("meta", property="og:url")
        og_title = soup.find("meta", property="og:title")
        title_text = (og_title.get("content") if og_title else "").strip()
        url_text = (og_url.get("content") if og_url else "").strip()

        # Deteksi generic watch redirect tanpa video ID spesifik
        if (
            url_text.rstrip('/') in ("https://www.facebook.com/watch", "https://m.facebook.com/watch")
            or "Discover popular videos" in title_text
            or "Log in to Facebook" in title_text
            or "Log into Facebook" in title_text
            or "Facebook - log in or sign up" in title_text
        ):
            raise PostNotFoundException(
                "Postingan/video Facebook tidak dapat diakses publik atau disetel privat (Meta mengalihkan ke halaman login/feed)."
            )

        media_items: List[MediaItem] = []

        # 2. Cek OpenGraph Video spesifik (Paling akurat & 100% bebas media acak!)
        og_video = (
            soup.find("meta", property="og:video")
            or soup.find("meta", property="og:video:url")
            or soup.find("meta", property="og:video:secure_url")
            or soup.find("meta", attrs={"name": "twitter:player:stream"})
            or soup.find("meta", attrs={"name": "twitter:player"})
        )
        if og_video and og_video.get("content"):
            vid_url = self._clean_media_url(og_video["content"])
            if (".mp4" in vid_url or "fbcdn.net" in vid_url) and not vid_url.endswith(".html"):
                w = 0
                h = 0
                meta_w = soup.find("meta", property="og:video:width")
                meta_h = soup.find("meta", property="og:video:height")
                if meta_w and meta_w.get("content", "").isdigit(): w = int(meta_w["content"])
                if meta_h and meta_h.get("content", "").isdigit(): h = int(meta_h["content"])
                media_items.append(MediaItem(type="VIDEO", url=vid_url, width=w, height=h))
                return media_items, "SINGLE_VIDEO"

        # 3. Cek Script JSON yang secara spesifik memuat target_id (hanya jika target_id valid)
        if target_id and len(target_id) >= 4 and target_id in html_content:
            for script in soup.find_all("script"):
                s_txt = script.get_text()
                if target_id in s_txt:
                    patterns = [
                        r'\"browser_native_hd_url\":\s*\"(https:[^\"]+)\"',
                        r'\"playable_url_quality_hd\":\s*\"(https:[^\"]+)\"',
                        r'\"hd_src\":\s*\"(https:[^\"]+)\"',
                        r'\"browser_native_sd_url\":\s*\"(https:[^\"]+)\"',
                        r'\"playable_url\":\s*\"(https:[^\"]+)\"',
                        r'\"sd_src\":\s*\"(https:[^\"]+)\"',
                    ]
                    for pat in patterns:
                        m = re.search(pat, s_txt)
                        if m:
                            clean_u = self._clean_media_url(m.group(1))
                            media_items.append(MediaItem(type="VIDEO", url=clean_u))
                            return media_items, "SINGLE_VIDEO"

        # 4. Deteksi Postingan FOTO / GAMBAR
        # Cek og:image spesifik dari head
        og_image = (
            soup.find("meta", property="og:image")
            or soup.find("meta", property="og:image:url")
            or soup.find("meta", attrs={"name": "twitter:image"})
        )
        if og_image and og_image.get("content"):
            img_url = self._clean_media_url(og_image["content"])
            if not self._is_static_asset(img_url):
                # Cari kemungkinan multi-photo jika postingan adalah album foto
                found_images = [img_url]
                if target_id:
                    # Cari foto-foto terkait dalam blok target
                    photo_matches = re.findall(r'\"image\":\s*\{\"uri\":\s*\"(https:[^\"]+fbcdn\.net[^\"]+)\"', html_content)
                    for pm in photo_matches:
                        clean_pm = self._clean_media_url(pm)
                        if clean_pm not in found_images and not self._is_static_asset(clean_pm):
                            found_images.append(clean_pm)

                for u in found_images[:10]:
                    media_items.append(MediaItem(type="IMAGE", url=u))

                mtype = "SINGLE_IMAGE" if len(media_items) == 1 else "MULTI_IMAGE"
                return media_items, mtype

        return [], "NONE"

    async def _download_single_file(self, url: str, dest_path: str) -> bool:
        """Unduh file media via aria2c."""
        async with self.semaphore:
            headers = {"User-Agent": random.choice(DESKTOP_USER_AGENTS)}
            return await aria2_download(url, dest_path, headers=headers)

    async def download_post(self, url: str) -> Dict[str, Any]:
        """
        Download postingan Facebook (Video, Reels, atau Foto) secara native dan akurat.
        Returns:
            {"success": True, "data": FacebookPostData.to_dict()} atau
            {"success": False, "error": str, "error_type": str}
        """
        try:
            target_id = self.extract_id(url)
            resolved_url, html_content = await self._resolve_and_fetch_html(url)
            resolved_id = self.extract_id(resolved_url) or target_id

            media_items, media_type = self._extract_media(html_content, resolved_id)

            if not media_items:
                return {
                    "success": False,
                    "error": "Tidak dapat menemukan video atau foto yang valid pada postingan Facebook ini (mungkin disetel privat atau telah dihapus).",
                    "error_type": "PostNotFoundException"
                }

            soup = BeautifulSoup(html_content, "html.parser")
            og_title = soup.find("meta", property="og:title")
            og_desc = soup.find("meta", property="og:description")
            meta_desc = soup.find("meta", attrs={"name": "description"})

            caption = (
                (og_desc.get("content") if og_desc else "")
                or (meta_desc.get("content") if meta_desc else "")
                or (og_title.get("content") if og_title else "")
            ).strip()
            caption = re.sub(r'\s*\|\s*Facebook$', '', caption, flags=re.IGNORECASE).strip()

            title_text = (og_title.get("content") if og_title else "").strip()
            username = self._clean_author("", title_text)

            post_data = FacebookPostData(
                post_id=resolved_id or str(int(time.time())),
                shortcode=resolved_id or str(int(time.time())),
                username=username,
                user_pic=None,
                caption=caption,
                posted_at=int(time.time()),
                like_count=0,
                reply_count=0,
                media_type=media_type,
                media_items=media_items,
                downloaded_files=[]
            )

            # Download media items via aria2c
            downloaded_paths = []
            tasks = []
            for index, item in enumerate(media_items):
                ext = "mp4" if item.type == "VIDEO" else "jpg"
                filename = f"facebook_{post_data.shortcode}_{index}.{ext}"
                full_path = os.path.join(self.download_dir, filename)
                downloaded_paths.append(full_path)
                tasks.append(self._download_single_file(item.url, full_path))

            results = await asyncio.gather(*tasks)
            final_files = [p for p, ok in zip(downloaded_paths, results) if ok and os.path.exists(p) and os.path.getsize(p) > 512]
            post_data.downloaded_files = final_files

            if not final_files:
                return {
                    "success": False,
                    "error": "Gagal mengunduh file media Facebook dari server CDN.",
                    "error_type": "DownloadException"
                }

            return {"success": True, "data": post_data.to_dict()}

        except FacebookScraperException as fse:
            return {"success": False, "error": str(fse), "error_type": fse.__class__.__name__}
        except Exception as e:
            return {"success": False, "error": f"Internal error: {str(e)}", "error_type": "UnhandledException"}
