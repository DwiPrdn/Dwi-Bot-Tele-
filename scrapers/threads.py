import os
import re
import json
import logging
import asyncio
import random
import time
import html as html_lib
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
import aiohttp
from bs4 import BeautifulSoup
from .aria2_dl import aria2_download

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ThreadsScraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]


class ThreadsScraperException(Exception):
    pass


class PostNotFoundException(ThreadsScraperException):
    pass


class ParsingException(ThreadsScraperException):
    pass


@dataclass
class MediaItem:
    type: str
    url: str
    width: int
    height: int


@dataclass
class ThreadsPostData:
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


class ThreadsScraper:
    """
    Scraper untuk platform Threads (threads.net).
    Mendukung mode Cookieless (tanpa login) sebagai metode utama yang andal,
    dengan fallback otomatis ke cookie jika tersedia dan diperlukan.
    """

    def __init__(
        self,
        download_dir: str = "./downloads/threads",
        max_concurrent_downloads: int = 5,
        cookie_file: str = "cookies.json"
    ):
        self.download_dir = download_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
        self.cookie_file = cookie_file

        self.cookies: Dict[str, str] = {}
        if os.path.exists(cookie_file):
            try:
                with open(cookie_file, 'r', encoding='utf-8') as f:
                    self.cookies = json.load(f)
                logger.info(f"Loaded {len(self.cookies)} cookies dari {cookie_file} (sebagai fallback).")
            except Exception as e:
                logger.warning(f"Gagal meload cookies fallback: {e}")
        else:
            logger.info("Scraper aktif dalam mode cookieless murni (tanpa login/cookies).")

        os.makedirs(self.download_dir, exist_ok=True)

    def extract_shortcode(self, url: str) -> str:
        """Mengekstrak shortcode postingan dari URL Threads."""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        parts = [p for p in path.split('/') if p]

        if 'post' in parts:
            idx = parts.index('post')
            if idx + 1 < len(parts):
                return parts[idx + 1].split('?')[0].split('&')[0]

        if 't' in parts:
            idx = parts.index('t')
            if idx + 1 < len(parts):
                return parts[idx + 1].split('?')[0].split('&')[0]

        if parts:
            return parts[-1].split('?')[0].split('&')[0]

        raise ThreadsScraperException(f"Gagal mengekstrak shortcode dari URL: {url}")

    def clean_original_url(self, url: str) -> str:
        """Standarisasi URL ke domain threads.net tanpa parameter tracking."""
        parsed = urlparse(url)
        domain = parsed.netloc.replace("threads.com", "threads.net")
        if not domain.endswith("threads.net"):
            domain = "www.threads.net"
        scheme = parsed.scheme or "https"
        return f"{scheme}://{domain}{parsed.path}"

    def _get_default_headers(self) -> Dict[str, str]:
        """Headers HTTP modern meniru browser resmi."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1"
        }

    async def _fetch_html(self, url: str, use_cookies: bool = False) -> tuple[str, str]:
        """
        Mengambil konten HTML dari URL Threads.
        Secara default dilakukan tanpa cookies (cookieless).
        """
        cookies_to_use = self.cookies if (use_cookies and self.cookies) else None
        async with aiohttp.ClientSession(cookies=cookies_to_use) as session:
            try:
                headers = self._get_default_headers()
                async with session.get(url, headers=headers, timeout=15, allow_redirects=True) as response:
                    final_url = str(response.url)
                    if response.status == 404:
                        raise PostNotFoundException("Postingan tidak ditemukan atau akun privat.")
                    if response.status not in (200, 301, 302):
                        raise ThreadsScraperException(f"Gagal mengambil halaman. HTTP Status: {response.status}")

                    html = await response.text()

                    # Deteksi jika diredirect ke login/challenge
                    if use_cookies and (
                        "__coig_challenge_redirected" in final_url
                        or "login" in final_url
                        or "auth_platform" in final_url
                    ):
                        raise ThreadsScraperException("Akun cookies terkunci atau dialihkan ke login checkpoint.")

                    return html, final_url
            except (PostNotFoundException, ThreadsScraperException):
                raise
            except Exception as e:
                raise ThreadsScraperException(f"Network error: {str(e)}")

    def _find_target_post(self, data: Any, shortcode: str) -> Optional[Dict[str, Any]]:
        """Mencari objek postingan Threads dengan mencocokkan shortcode secara rekursif."""
        if isinstance(data, dict):
            # Target post langsung
            if data.get("code") == shortcode:
                if (
                    "image_versions2" in data
                    or "video_versions" in data
                    or "carousel_media" in data
                    or "user" in data
                ):
                    return data

            # Terbungkus dalam sub-key 'post'
            if "post" in data and isinstance(data["post"], dict):
                if data["post"].get("code") == shortcode:
                    return data["post"]

            # Terbungkus dalam 'thread_items'
            if "thread_items" in data and isinstance(data["thread_items"], list):
                for ti in data["thread_items"]:
                    if isinstance(ti, dict) and "post" in ti and isinstance(ti["post"], dict):
                        if ti["post"].get("code") == shortcode:
                            return ti["post"]
                    res = self._find_target_post(ti, shortcode)
                    if res:
                        return res

            for key, value in data.items():
                res = self._find_target_post(value, shortcode)
                if res:
                    return res

        elif isinstance(data, list):
            for item in data:
                res = self._find_target_post(item, shortcode)
                if res:
                    return res

        return None

    def _parse_media_object(self, media_dict: Dict[str, Any]) -> Optional[MediaItem]:
        """Mengekstrak resolusi video atau gambar tertinggi dari sub-objek media."""
        try:
            video_versions = media_dict.get("video_versions") or []
            if video_versions and isinstance(video_versions, list):
                best_video = max(
                    video_versions,
                    key=lambda v: (v.get("width", 0) or 0) * (v.get("height", 0) or 0)
                )
                v_url = best_video.get("url")
                if v_url:
                    return MediaItem(
                        type="VIDEO",
                        url=html_lib.unescape(v_url),
                        width=best_video.get("width", 0) or 0,
                        height=best_video.get("height", 0) or 0
                    )

            image_candidates = (media_dict.get("image_versions2") or {}).get("candidates") or []
            if image_candidates and isinstance(image_candidates, list):
                best_image = max(
                    image_candidates,
                    key=lambda img: (img.get("width", 0) or 0) * (img.get("height", 0) or 0)
                )
                img_url = best_image.get("url")
                if img_url:
                    return MediaItem(
                        type="IMAGE",
                        url=html_lib.unescape(img_url),
                        width=best_image.get("width", 0) or 0,
                        height=best_image.get("height", 0) or 0
                    )
        except Exception as e:
            logger.warning(f"Gagal parsing sub-object media: {e}")
        return None

    def _parse_threads_json(self, target_post: Dict[str, Any], shortcode: str) -> ThreadsPostData:
        """Mengonversi dictionary data postingan mentah menjadi objek ThreadsPostData."""
        user_info = target_post.get("user") or {}
        username = user_info.get("username") or user_info.get("full_name") or "threads_user"
        user_pic = user_info.get("profile_pic_url")

        caption_obj = target_post.get("caption")
        if isinstance(caption_obj, dict):
            caption_text = caption_obj.get("text") or ""
        elif isinstance(caption_obj, str):
            caption_text = caption_obj
        else:
            caption_text = ""

        like_count = target_post.get("like_count", 0) or 0
        text_post_info = target_post.get("text_post_app_info") or {}
        reply_count = text_post_info.get("direct_reply_count", 0) or 0
        posted_at = target_post.get("taken_at", 0) or int(time.time())

        media_items: List[MediaItem] = []
        carousel_media = target_post.get("carousel_media")

        if carousel_media and isinstance(carousel_media, list) and len(carousel_media) > 0:
            media_type = "CAROUSEL"
            for sub_media in carousel_media:
                parsed_item = self._parse_media_object(sub_media)
                if parsed_item:
                    media_items.append(parsed_item)
        else:
            parsed_item = self._parse_media_object(target_post)
            if parsed_item:
                media_items.append(parsed_item)
                media_type = "SINGLE_VIDEO" if parsed_item.type == "VIDEO" else "SINGLE_IMAGE"
            else:
                media_type = "TEXT_ONLY"

        return ThreadsPostData(
            post_id=str(target_post.get("id") or target_post.get("pk") or shortcode),
            shortcode=shortcode,
            username=username,
            user_pic=user_pic,
            caption=caption_text,
            posted_at=posted_at,
            like_count=like_count,
            reply_count=reply_count,
            media_type=media_type,
            media_items=media_items
        )

    def _parse_opengraph(self, soup: BeautifulSoup, shortcode: str) -> Optional[ThreadsPostData]:
        """Fallback ekstraksi metadata via OpenGraph tags."""
        og_title = soup.find("meta", property="og:title")
        og_desc = soup.find("meta", property="og:description")
        og_image = soup.find("meta", property="og:image")
        og_video = soup.find("meta", property="og:video")

        title_val = og_title.get("content", "") if og_title else ""
        desc_val = og_desc.get("content", "") if og_desc else ""
        image_url = og_image.get("content", "") if og_image else ""
        video_url = og_video.get("content", "") if og_video else ""

        if not (image_url or video_url or desc_val):
            return None

        username = "threads_user"
        if title_val and " on Threads" in title_val:
            username = title_val.split(" on Threads")[0].strip().lstrip("@")
        elif title_val:
            username = title_val.split()[0].strip().lstrip("@")

        media_items = []
        media_type = "TEXT_ONLY"
        if video_url:
            media_items.append(MediaItem(type="VIDEO", url=video_url, width=0, height=0))
            media_type = "SINGLE_VIDEO"
        elif image_url and not any(ic in image_url for ic in ["static.cdninstagram.com", "threads.net/static"]):
            media_items.append(MediaItem(type="IMAGE", url=image_url, width=0, height=0))
            media_type = "SINGLE_IMAGE"

        return ThreadsPostData(
            post_id=shortcode,
            shortcode=shortcode,
            username=username,
            user_pic=None,
            caption=desc_val,
            posted_at=int(time.time()),
            like_count=0,
            reply_count=0,
            media_type=media_type,
            media_items=media_items
        )

    def _extract_post_from_html(self, html_content: str, shortcode: str) -> Optional[ThreadsPostData]:
        """Mengekstrak data postingan lengkap dari konten HTML Threads."""
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Telusuri semua tag <script> yang mengandung shortcode
        for script in soup.find_all("script"):
            txt = script.get_text().strip()
            if not txt or shortcode not in txt:
                continue

            if (txt.startswith('{') and txt.endswith('}')) or (txt.startswith('[') and txt.endswith(']')):
                try:
                    data = json.loads(txt)
                    post = self._find_target_post(data, shortcode)
                    if post and ("user" in post or "video_versions" in post or "image_versions2" in post or "caption" in post):
                        return self._parse_threads_json(post, shortcode)
                except Exception:
                    pass

            # Cari blok JSON di dalam script jika ada wrapper JS
            matches = re.finditer(r'(\{.*?\"code\":\s*\"' + re.escape(shortcode) + r'\".*?\})', txt)
            for m in matches:
                try:
                    data = json.loads(m.group(1))
                    post = self._find_target_post(data, shortcode)
                    if post:
                        return self._parse_threads_json(post, shortcode)
                except Exception:
                    pass

        # 2. Fallback: Cari di raw HTML jika script tag berada di luar DOM / streaming BigPipe
        if shortcode in html_content:
            for m in re.finditer(r'(\{\"require\":\[\[\"ScheduledServerJS\".*?\]\]\})', html_content):
                block = m.group(1)
                if shortcode in block:
                    try:
                        data = json.loads(block)
                        post = self._find_target_post(data, shortcode)
                        if post:
                            return self._parse_threads_json(post, shortcode)
                    except Exception:
                        pass

        # 3. Fallback: OpenGraph tags
        og_data = self._parse_opengraph(soup, shortcode)
        if og_data:
            return og_data

        return None

    def _extract_json_from_html(self, html_content: str) -> Dict[str, Any]:
        """Helper untuk kompatibilitas fungsi lama."""
        soup = BeautifulSoup(html_content, "html.parser")
        combined_json = {}
        for script in soup.find_all("script"):
            txt = script.get_text().strip()
            if not txt:
                continue
            if (txt.startswith('{') and txt.endswith('}')) or (txt.startswith('[') and txt.endswith(']')):
                try:
                    data = json.loads(txt)
                    if isinstance(data, dict):
                        combined_json.update(data)
                except Exception:
                    pass
        if combined_json:
            return combined_json
        raise ParsingException("Gagal ekstrak JSON dari HTML.")

    async def _download_single_file(self, url: str, dest_path: str) -> bool:
        """Mengunduh file media tunggal via aria2c (tanpa cookie akun ke CDN)."""
        async with self.semaphore:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            success = await aria2_download(url, dest_path, headers=headers)
            if success:
                logger.info(f"Berhasil unduh: {dest_path}")
            else:
                logger.error(f"Gagal unduh media: {url}")
            return success

    async def get_post_info(self, url: str) -> ThreadsPostData:
        """
        Mengambil informasi postingan Threads.
        Mencoba mode Cookieless terlebih dahulu. Jika gagal dan cookie tersedia,
        mencoba fallback menggunakan cookies.
        """
        clean_url_str = self.clean_original_url(url)
        shortcode = self.extract_shortcode(clean_url_str)
        last_error = None

        # 1. Coba mode Cookieless (Guest / Tanpa Login)
        try:
            html_content, final_url = await self._fetch_html(clean_url_str, use_cookies=False)
            resolved_shortcode = self.extract_shortcode(final_url) or shortcode
            post_data = self._extract_post_from_html(html_content, resolved_shortcode)
            if post_data:
                logger.info(f"[ThreadsScraper] Berhasil scrape cookieless untuk post: {resolved_shortcode}")
                return post_data
        except Exception as e:
            logger.warning(f"[ThreadsScraper] Mode cookieless gagal ({e}), mengecek opsi fallback...")
            last_error = e

        # 2. Fallback: Coba menggunakan cookies jika file cookies tersedia
        if self.cookies:
            try:
                logger.info("[ThreadsScraper] Mencoba fallback dengan cookies...")
                html_content, final_url = await self._fetch_html(clean_url_str, use_cookies=True)
                resolved_shortcode = self.extract_shortcode(final_url) or shortcode
                post_data = self._extract_post_from_html(html_content, resolved_shortcode)
                if post_data:
                    logger.info(f"[ThreadsScraper] Berhasil scrape dengan cookies fallback: {resolved_shortcode}")
                    return post_data
            except Exception as e:
                logger.error(f"[ThreadsScraper] Fallback dengan cookies juga gagal: {e}")
                last_error = e

        if isinstance(last_error, ThreadsScraperException):
            raise last_error
        raise ParsingException(f"Gagal mengambil data postingan Threads ({shortcode}). Pastikan URL publik dan valid.")

    async def download_post(self, url: str) -> Dict[str, Any]:
        """
        Mengunduh postingan Threads beserta seluruh media (foto/video/carousel).
        Returns:
            {"success": True, "data": ThreadsPostData.to_dict()} atau
            {"success": False, "error": str, "error_type": str}
        """
        try:
            post_data = await self.get_post_info(url)

            if not post_data.media_items:
                post_data.downloaded_files = []
                return {"success": True, "data": post_data.to_dict()}

            downloaded_paths = []
            tasks = []
            for index, item in enumerate(post_data.media_items):
                ext = "mp4" if item.type == "VIDEO" else "jpg"
                filename = f"threads_{post_data.shortcode}_{index}.{ext}"
                full_path = os.path.join(self.download_dir, filename)

                downloaded_paths.append(full_path)
                tasks.append(self._download_single_file(item.url, full_path))

            results = await asyncio.gather(*tasks)
            final_downloaded_files = [path for path, success in zip(downloaded_paths, results) if success]
            post_data.downloaded_files = final_downloaded_files

            return {"success": True, "data": post_data.to_dict()}

        except ThreadsScraperException as tse:
            return {"success": False, "error": str(tse), "error_type": tse.__class__.__name__}
        except Exception as e:
            return {"success": False, "error": f"Internal error: {str(e)}", "error_type": "UnhandledException"}