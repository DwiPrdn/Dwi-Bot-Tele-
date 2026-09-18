import os
import re
import json
import logging
import asyncio
import random
import time
import shutil
import base64
import html as html_lib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
import aiohttp
from bs4 import BeautifulSoup
from PIL import Image
from .aria2_dl import aria2_download

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("InstagramScraper")

_SCRAPERS_DIR = os.path.dirname(os.path.abspath(__file__))
_LOGS_DIR = os.path.join(_SCRAPERS_DIR, "logs")


def _save_debug_log(content: str) -> str:
    """
    Menyimpan log debug HTML ke scrapers/logs/debug_ig.html dan scrapers/logs/debug_full.html.
    Mengembalikan path absolut ke debug_ig.html.
    """
    os.makedirs(_LOGS_DIR, exist_ok=True)
    target_ig = os.path.join(_LOGS_DIR, "debug_ig.html")
    target_full = os.path.join(_LOGS_DIR, "debug_full.html")

    for path in (target_ig, target_full):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as err:
            logger.warning(f"Gagal menulis file debug di {path}: {err}")

    return target_ig

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]


class InstagramScraperException(Exception):
    pass


class PostNotFoundException(InstagramScraperException):
    pass


class ParsingException(InstagramScraperException):
    pass


@dataclass
class MediaItem:
    type: str  # "VIDEO" or "IMAGE"
    url: str
    width: int = 0
    height: int = 0


@dataclass
class InstagramPostData:
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


def shortcode_to_media_id(shortcode: str) -> Optional[int]:
    """Konversi base64 shortcode Instagram ke media ID numerik (PK)."""
    if not shortcode:
        return None
    if shortcode.isdigit():
        return int(shortcode)
    # Jika shortcode panjang (private share link dengan tracking suffix > 28 karakter)
    if len(shortcode) > 28:
        shortcode = shortcode[:-28]
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    try:
        for char in shortcode:
            media_id = media_id * 64 + alphabet.index(char)
        return media_id
    except Exception:
        return None


def media_id_to_shortcode(media_id: int) -> str:
    """Konversi media ID numerik (PK) ke shortcode Instagram."""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    shortcode = ''
    while media_id > 0:
        media_id, rem = divmod(media_id, 64)
        shortcode = alphabet[rem] + shortcode
    return shortcode


def parse_cookie_file(cookie_file: str) -> Dict[str, str]:
    """
    Parse file cookies dari berbagai format:
    - Netscape format (tab-delimited lines, format umum cookies.txt)
    - JSON format ({"sessionid": "...", "csrftoken": "..."})
    - Raw header string ("sessionid=...; csrftoken=...")
    """
    cookies: Dict[str, str] = {}
    if not cookie_file or not os.path.exists(cookie_file):
        return cookies

    try:
        with open(cookie_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().strip()

        # 1. Format JSON
        if content.startswith('{') and content.endswith('}'):
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    return {str(k).strip(): str(v).strip() for k, v in data.items()}
            except Exception:
                pass

        # 2. Format Header String (sessionid=xxx; csrftoken=yyy)
        if "sessionid=" in content and "\t" not in content:
            for item in content.split(';'):
                if '=' in item:
                    k, v = item.strip().split('=', 1)
                    cookies[k.strip()] = v.strip()
            return cookies

        # 3. Format Netscape cookies.txt
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('#HttpOnly_'):
                line = line[10:]
            if line.startswith('#') or not line:
                continue
            parts = line.split('\t')
            if len(parts) >= 7:
                cookies[parts[5].strip()] = parts[6].strip()

    except Exception as e:
        logger.warning(f"Gagal membaca file cookies {cookie_file}: {e}")

    return cookies


class InstagramScraper:
    """
    Scraper untuk platform Instagram (instagram.com).
    Mendukung mode Cookieless (tanpa login/cookies) sebagai metode utama yang cepat & mandiri,
    dengan fallback otomatis ke cookies hanya jika diperlukan (misal: konten restricted / login wall).
    Jika terjadi kegagalan, log debug disimpan otomatis ke scrapers/logs/debug_ig.html dan debug_full.html.
    """

    def __init__(
        self,
        download_dir: str = "./downloads/ig",
        max_concurrent_downloads: int = 5,
        cookie_file: Optional[str] = "dbbot/cookies/ig.txt"
    ):
        self.download_dir = download_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
        self.cookie_file_path = cookie_file

        self.cookies: Dict[str, str] = {}
        self.has_session = False
        if cookie_file and os.path.exists(cookie_file):
            self.cookies = parse_cookie_file(cookie_file)
            if self.cookies:
                self.has_session = "sessionid" in self.cookies
                if self.has_session:
                    logger.info(f"Loaded {len(self.cookies)} cookies dari {cookie_file} (termasuk sessionid autentikasi).")
                else:
                    logger.warning(f"Loaded {len(self.cookies)} cookies dari {cookie_file} (Peringatan: 'sessionid' tidak ditemukan, fitur Story memerlukan sessionid).")
            else:
                logger.info("Scraper aktif dalam mode cookieless murni (file cookies kosong/tidak valid).")
        else:
            logger.info("Scraper aktif dalam mode cookieless murni (tanpa login/cookies).")

        os.makedirs(self.download_dir, exist_ok=True)

    def extract_shortcode(self, url: str) -> str:
        """Mengekstrak shortcode postingan atau ID story dari beragam format URL Instagram."""
        parsed = urlparse(url)
        path = parsed.path.strip('/')

        m = re.search(r'(?:(?:p|reel|reels|tv|share/(?:p|reel)))/([a-zA-Z0-9_-]+)', path)
        if m:
            return m.group(1)

        m_stories = re.search(r'stories/[^/?#&]+/(\d+)', path)
        if m_stories:
            return m_stories.group(1)

        # Cek format profil /{username}/p/{shortcode}
        m_user_post = re.search(r'[^/?#&]+/(?:p|reel)/([a-zA-Z0-9_-]+)', path)
        if m_user_post:
            return m_user_post.group(1)

        parts = [p for p in path.split('/') if p]
        if parts:
            cand = parts[-1].split('?')[0].split('&')[0]
            if re.match(r'^[a-zA-Z0-9_-]+$', cand):
                return cand

        raise InstagramScraperException(f"Gagal mengekstrak shortcode dari URL Instagram: {url}")

    def clean_original_url(self, url: str) -> str:
        """Standarisasi URL Instagram ke domain www.instagram.com tanpa parameter tracking."""
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        if not path:
            return url
        shortcode = self.extract_shortcode(url)
        if "stories" in path:
            return f"https://www.instagram.com{parsed.path}"
        if "reel" in path:
            return f"https://www.instagram.com/reel/{shortcode}/"
        return f"https://www.instagram.com/p/{shortcode}/"

    def _get_default_headers(self) -> Dict[str, str]:
        """Headers HTTP modern meniru browser resmi untuk permintaan cookieless."""
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

    async def _fetch_html(self, url: str, use_cookies: bool = False) -> Tuple[str, str]:
        """
        Mengambil konten HTML dari URL Instagram via aiohttp.
        Secara default dilakukan tanpa cookies (cookieless).
        """
        cookies_to_use = self.cookies if (use_cookies and self.cookies) else None
        headers = self._get_default_headers()

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(cookies=cookies_to_use, timeout=timeout) as session:
            try:
                async with session.get(url, headers=headers, allow_redirects=True) as response:
                    final_url = str(response.url)
                    if response.status == 404:
                        raise PostNotFoundException("Postingan Instagram tidak ditemukan atau akun bersifat privat.")

                    html = await response.text()

                    # Deteksi jika diredirect ke checkpoint/scraping warning saat memakai cookies
                    if use_cookies and (
                        "__coig_challenge_redirected" in final_url
                        or "login" in final_url
                        or "scraping_warning" in final_url
                        or "auth_platform" in final_url
                    ):
                        raise InstagramScraperException("Sesi cookies dialihkan ke login checkpoint / scraping warning.")

                    return html, final_url
            except (PostNotFoundException, InstagramScraperException):
                raise
            except Exception as e:
                raise InstagramScraperException(f"Network error saat mengambil HTML: {str(e)}")

    def _find_target_post(self, data: Any, shortcode: str, media_id_str: str = "") -> Optional[Dict[str, Any]]:
        """Mencari objek postingan Instagram target secara rekursif dari struktur JSON/Relay."""
        if isinstance(data, dict):
            # Abaikan item profil timeline agar tidak salah mengambil grid profile creator
            if 'profile_grid_items' in data or 'xdt_api__v1__profile_timeline' in data:
                return None

            # Cocokkan code / shortcode
            c = data.get("code") or data.get("shortcode")
            pk = str(data.get("pk") or data.get("id") or "")
            is_match = (c == shortcode) or (media_id_str and pk == media_id_str)

            has_media = (
                "image_versions2" in data
                or "video_versions" in data
                or "carousel_media" in data
                or "edge_sidecar_to_children" in data
                or "display_url" in data
                or "video_url" in data
            )

            if is_match and has_media:
                return data

            # Terbungkus dalam sub-key xdt_api__v1__media__shortcode__web_info
            if "xdt_api__v1__media__shortcode__web_info" in data:
                info = data["xdt_api__v1__media__shortcode__web_info"]
                if isinstance(info, dict) and info.get("items"):
                    for it in info["items"]:
                        if it.get("code") == shortcode or not it.get("code"):
                            return it
                    return info["items"][0]

            if "xdt_shortcode_media" in data and isinstance(data["xdt_shortcode_media"], dict):
                return data["xdt_shortcode_media"]

            if "shortcode_media" in data and isinstance(data["shortcode_media"], dict):
                return data["shortcode_media"]

            if "post" in data and isinstance(data["post"], dict):
                res = self._find_target_post(data["post"], shortcode, media_id_str)
                if res:
                    return res

            for key, value in data.items():
                if key in ('profile_grid_items', 'xdt_api__v1__profile_timeline'):
                    continue
                res = self._find_target_post(value, shortcode, media_id_str)
                if res:
                    return res

        elif isinstance(data, list):
            for item in data:
                res = self._find_target_post(item, shortcode, media_id_str)
                if res:
                    return res

        return None

    def _parse_media_object(self, media_dict: Dict[str, Any]) -> Optional[MediaItem]:
        """Mengekstrak resolusi video MP4 tertinggi atau gambar resolusi tertinggi dari sub-objek media."""
        try:
            # 1. Cek versi video
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

            if media_dict.get("video_url"):
                return MediaItem(
                    type="VIDEO",
                    url=html_lib.unescape(media_dict["video_url"]),
                    width=media_dict.get("dimensions", {}).get("width", 0) or 0,
                    height=media_dict.get("dimensions", {}).get("height", 0) or 0
                )

            # 2. Cek versi gambar
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

            disp_url = media_dict.get("display_url") or media_dict.get("display_src")
            if disp_url:
                return MediaItem(
                    type="IMAGE",
                    url=html_lib.unescape(disp_url),
                    width=media_dict.get("dimensions", {}).get("width", 0) or 0,
                    height=media_dict.get("dimensions", {}).get("height", 0) or 0
                )

        except Exception as e:
            logger.warning(f"[InstagramScraper] Gagal parsing media item: {e}")

        return None

    def _parse_instagram_json(self, target_post: Dict[str, Any], shortcode: str) -> InstagramPostData:
        """Mengonversi dictionary data postingan mentah menjadi objek InstagramPostData."""
        user_info = target_post.get("user") or target_post.get("owner") or {}
        username = user_info.get("username") or user_info.get("full_name") or "user_ig"
        user_pic = user_info.get("profile_pic_url")

        # Ekstrak teks caption
        caption_text = ""
        caption_obj = target_post.get("caption")
        if isinstance(caption_obj, dict):
            caption_text = caption_obj.get("text") or ""
        elif isinstance(caption_obj, str):
            caption_text = caption_obj
        elif "edge_media_to_caption" in target_post:
            edges = target_post.get("edge_media_to_caption", {}).get("edges", [])
            if edges and isinstance(edges, list) and edges[0].get("node", {}).get("text"):
                caption_text = edges[0]["node"]["text"]

        like_count = (
            target_post.get("like_count")
            or target_post.get("edge_media_preview_like", {}).get("count")
            or 0
        )
        reply_count = (
            target_post.get("comment_count")
            or target_post.get("edge_media_to_comment", {}).get("count")
            or 0
        )
        posted_at = (
            target_post.get("taken_at")
            or target_post.get("taken_at_timestamp")
            or int(time.time())
        )

        media_items: List[MediaItem] = []

        # 1. Format Album / Carousel standar
        carousel_media = target_post.get("carousel_media")
        if carousel_media and isinstance(carousel_media, list) and len(carousel_media) > 0:
            media_type = "CAROUSEL"
            for sub_media in carousel_media:
                parsed_item = self._parse_media_object(sub_media)
                if parsed_item:
                    media_items.append(parsed_item)

        # 2. Format Album GraphQL edge_sidecar_to_children
        elif "edge_sidecar_to_children" in target_post:
            edges = target_post.get("edge_sidecar_to_children", {}).get("edges", [])
            media_type = "CAROUSEL"
            for edge in edges:
                node = edge.get("node", {})
                parsed_item = self._parse_media_object(node)
                if parsed_item:
                    media_items.append(parsed_item)

        # 3. Single Media (Video / Foto)
        else:
            parsed_item = self._parse_media_object(target_post)
            if parsed_item:
                media_items.append(parsed_item)
                media_type = "SINGLE_VIDEO" if parsed_item.type == "VIDEO" else "SINGLE_IMAGE"
            else:
                media_type = "TEXT_ONLY"

        # Dedup media items
        seen_urls = set()
        deduped_items: List[MediaItem] = []
        for it in media_items:
            clean_u = it.url.replace('\\/', '/').strip('"\' ')
            if clean_u and clean_u not in seen_urls:
                seen_urls.add(clean_u)
                it.url = clean_u
                deduped_items.append(it)

        return InstagramPostData(
            post_id=str(target_post.get("pk") or target_post.get("id") or shortcode),
            shortcode=shortcode,
            username=username,
            user_pic=user_pic,
            caption=caption_text,
            posted_at=posted_at,
            like_count=like_count,
            reply_count=reply_count,
            media_type=media_type,
            media_items=deduped_items
        )

    def _parse_opengraph(self, soup: BeautifulSoup, shortcode: str) -> Optional[InstagramPostData]:
        """Fallback ekstraksi metadata via OpenGraph meta tags."""
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

        username = "user_ig"
        if title_val and " on Instagram" in title_val:
            username = title_val.split(" on Instagram")[0].strip().lstrip("@")
        elif title_val:
            username = title_val.split()[0].strip().lstrip("@")

        caption = desc_val
        if ' - ' in caption and ': "' in caption:
            caption = caption.split(': "', 1)[1].rstrip('" ')

        media_items = []
        media_type = "TEXT_ONLY"
        if video_url:
            media_items.append(MediaItem(type="VIDEO", url=video_url, width=0, height=0))
            media_type = "SINGLE_VIDEO"
        elif image_url and not any(ic in image_url for ic in ["static.cdninstagram.com", "instagram.com/static"]):
            media_items.append(MediaItem(type="IMAGE", url=image_url, width=0, height=0))
            media_type = "SINGLE_IMAGE"

        return InstagramPostData(
            post_id=shortcode,
            shortcode=shortcode,
            username=username,
            user_pic=None,
            caption=caption,
            posted_at=int(time.time()),
            like_count=0,
            reply_count=0,
            media_type=media_type,
            media_items=media_items
        )

    def _extract_post_from_html(self, html_content: str, shortcode: str) -> Optional[InstagramPostData]:
        """Mengekstrak data postingan lengkap dari konten HTML Instagram."""
        if not html_content:
            return None

        media_id_str = str(shortcode_to_media_id(shortcode) or "")
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Telusuri semua tag <script> yang mengandung shortcode atau media ID
        for script in soup.find_all("script"):
            txt = script.get_text().strip()
            if not txt:
                continue

            if (shortcode in txt) or (media_id_str and media_id_str in txt):
                if (txt.startswith('{') and txt.endswith('}')) or (txt.startswith('[') and txt.endswith(']')):
                    try:
                        data = json.loads(txt)
                        post = self._find_target_post(data, shortcode, media_id_str)
                        if post:
                            return self._parse_instagram_json(post, shortcode)
                    except Exception:
                        pass

                # Cari blok JSON di dalam wrapper JS
                matches = re.finditer(r'(\{.*?\"(?:code|shortcode)\":\s*\"' + re.escape(shortcode) + r'\".*?\})', txt)
                for m in matches:
                    try:
                        data = json.loads(m.group(1))
                        post = self._find_target_post(data, shortcode, media_id_str)
                        if post:
                            return self._parse_instagram_json(post, shortcode)
                    except Exception:
                        pass

        # 2. Cari di raw HTML jika script tag berada di streaming BigPipe / ScheduledServerJS
        if shortcode in html_content:
            for m in re.finditer(r'(\{\"require\":\[\[\"ScheduledServerJS\".*?\]\]\})', html_content):
                block = m.group(1)
                if shortcode in block:
                    try:
                        data = json.loads(block)
                        post = self._find_target_post(data, shortcode, media_id_str)
                        if post:
                            return self._parse_instagram_json(post, shortcode)
                    except Exception:
                        pass

        # 3. Fallback OpenGraph tags
        og_data = self._parse_opengraph(soup, shortcode)
        if og_data and og_data.media_items:
            return og_data

        return None

    async def _fetch_api_with_cookies(self, media_id: int) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Ambil informasi media lengkap langsung via Web API Instagram dengan cookies fallback.
        Menggunakan endpoint www.instagram.com/api/v1/media/{media_id}/info/.
        Returns: (item_dict, debug_info)
        """
        if not self.cookies:
            return None, "File cookies tidak tersedia atau kosong."

        url = f"https://www.instagram.com/api/v1/media/{media_id}/info/"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "359341",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.instagram.com/",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(cookies=self.cookies, timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    resp_text = await resp.text()
                    if resp.status == 200:
                        try:
                            data = json.loads(resp_text)
                            items = data.get("items")
                            if items and isinstance(items, list) and len(items) > 0:
                                logger.info(f"[InstagramScraper] API fallback berhasil untuk media ID {media_id}.")
                                return items[0], ""
                        except Exception as json_err:
                            return None, f"Gagal parsing response JSON dari API (Status: 200): {json_err}"

                    debug_info = (
                        f"Instagram API Error (HTTP {resp.status}) untuk media ID {media_id}:\n"
                        f"Headers: {dict(resp.headers)}\n"
                        f"Body: {resp_text[:1000]}"
                    )
                    return None, debug_info
        except Exception as e:
            debug_info = f"Network Exception saat request API ({media_id}): {str(e)}"
            return None, debug_info

    async def _fetch_reels_media_with_cookies(self, reel_id: str) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        """
        Ambil items story / highlight via endpoint api/v1/feed/reels_media/?reel_ids={reel_id}.
        reel_id format:
        - highlight: 'highlight:17951234567890123'
        - user: '73332927701'
        Returns: (items_list, debug_info)
        """
        if not self.cookies:
            return None, "File cookies tidak tersedia atau kosong."

        url = f"https://www.instagram.com/api/v1/feed/reels_media/?reel_ids={reel_id}"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "359341",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.instagram.com/",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(cookies=self.cookies, timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    resp_text = await resp.text()
                    if resp.status == 200:
                        try:
                            data = json.loads(resp_text)
                            reels = data.get("reels", {})
                            target = reels.get(reel_id) or reels.get(str(reel_id))
                            if target and target.get("items"):
                                return target["items"], ""
                        except Exception as json_err:
                            return None, f"Gagal parsing response JSON dari reels_media: {json_err}"

                    debug_info = (
                        f"Instagram reels_media Error (HTTP {resp.status}) untuk reel_id {reel_id}:\n"
                        f"Headers: {dict(resp.headers)}\n"
                        f"Body: {resp_text[:1000]}"
                    )
                    return None, debug_info
        except Exception as e:
            debug_info = f"Network Exception saat request reels_media ({reel_id}): {str(e)}"
            return None, debug_info

    async def _resolve_username_to_id(self, username: str) -> Optional[int]:
        """Mendapatkan numeric user ID (PK) dari username melalui web_profile_info."""
        if not self.cookies:
            return None

        url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "359341",
            "Accept": "*/*",
            "Referer": f"https://www.instagram.com/{username}/",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(cookies=self.cookies, timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        uid = data.get("data", {}).get("user", {}).get("id")
                        if uid:
                            return int(uid)
        except Exception:
            pass

        return None


    async def _download_single_file(self, url: str, dest_path: str) -> bool:
        """Mengunduh file media tunggal via aria2c tanpa cookie akun ke CDN."""
        async with self.semaphore:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            success = await aria2_download(url, dest_path, headers=headers)
            if success:
                logger.info(f"[InstagramScraper] Berhasil unduh: {dest_path}")
                # Konversi file .webp ke .jpg demi kompatibilitas penuh Telegram
                if dest_path.lower().endswith('.jpg') and os.path.exists(dest_path):
                    try:
                        with open(dest_path, 'rb') as f:
                            head = f.read(12)
                        if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
                            im = Image.open(dest_path).convert('RGB')
                            im.save(dest_path, 'JPEG', quality=95)
                    except Exception as conv_err:
                        logger.warning(f"[InstagramScraper] Konversi webp->jpg gagal: {conv_err}")
            else:
                logger.error(f"[InstagramScraper] Gagal unduh media: {url}")
            return success

    async def get_post_info(self, url: str) -> InstagramPostData:
        """
        Mengambil informasi postingan Instagram.
        Mencoba mode Cookieless terlebih dahulu (tanpa login/cookies).
        Jika gagal dan cookies tersedia, beralih ke fallback cookies.
        Jika seluruh metode gagal, menyimpan output debug ke scrapers/logs/debug_ig.html & debug_full.html.
        """
        clean_url_str = self.clean_original_url(url)
        shortcode = self.extract_shortcode(clean_url_str)
        media_id = shortcode_to_media_id(shortcode)

        last_error = None
        last_debug_html = ""

        # 1. Coba mode Cookieless (Guest / Tanpa Login)
        try:
            html_content, final_url = await self._fetch_html(clean_url_str, use_cookies=False)
            last_debug_html = html_content
            resolved_shortcode = self.extract_shortcode(final_url) or shortcode
            post_data = self._extract_post_from_html(html_content, resolved_shortcode)
            if post_data and post_data.media_items:
                logger.info(f"[InstagramScraper] Berhasil scrape cookieless untuk post: {resolved_shortcode}")
                return post_data
        except Exception as e:
            logger.warning(f"[InstagramScraper] Mode cookieless gagal ({e}), mengecek opsi fallback...")
            last_error = e

        # 2. Fallback: Coba menggunakan cookies jika file cookies tersedia
        if self.cookies:
            logger.info("[InstagramScraper] Mencoba fallback dengan cookies...")

            # 2a. Mobile/Web API dengan cookies
            if media_id:
                try:
                    api_item, api_debug = await self._fetch_api_with_cookies(media_id)
                    if api_item:
                        post_data = self._parse_instagram_json(api_item, shortcode)
                        if post_data and post_data.media_items:
                            logger.info(f"[InstagramScraper] Berhasil scrape via API dengan cookies fallback: {shortcode}")
                            return post_data
                    if api_debug:
                        last_debug_html = api_debug
                except Exception as api_err:
                    logger.warning(f"[InstagramScraper] API fallback gagal: {api_err}")
                    last_error = api_err


            # 2c. HTML fetch dengan cookies
            try:
                html_content, final_url = await self._fetch_html(clean_url_str, use_cookies=True)
                last_debug_html = html_content
                resolved_shortcode = self.extract_shortcode(final_url) or shortcode
                post_data = self._extract_post_from_html(html_content, resolved_shortcode)
                if post_data and post_data.media_items:
                    logger.info(f"[InstagramScraper] Berhasil scrape HTML dengan cookies fallback: {resolved_shortcode}")
                    return post_data
            except Exception as e:
                logger.debug(f"[InstagramScraper] Fallback HTML cookies gagal: {e}")
                last_error = e

        # 3. Semua metode gagal: Simpan output debug ke scrapers/logs/debug_ig.html & debug_full.html
        debug_output_text = last_debug_html or f"Gagal mengekstrak postingan Instagram: {shortcode}\nURL: {url}\nLast error: {last_error}"
        debug_file = _save_debug_log(debug_output_text)
        logger.info(f"[InstagramScraper] File debug disimpan di '{debug_file}'.")

        if isinstance(last_error, InstagramScraperException):
            raise last_error
        raise ParsingException(f"Gagal mengambil postingan Instagram ({shortcode}). File debug disimpan di '{debug_file}'.")

    async def _process_story_items(self, items: List[Dict[str, Any]], prefix: str, username: str) -> Dict[str, Any]:
        """Memproses daftar raw story items, parsing media, mengunduh file, dan mengembalikan InstagramPostData."""
        all_media_items: List[MediaItem] = []
        user_pic = None
        real_username = username

        for item in items:
            p_data = self._parse_instagram_json(item, str(item.get("pk") or prefix))
            if p_data.username and p_data.username != "user_ig":
                real_username = p_data.username
            if p_data.user_pic and not user_pic:
                user_pic = p_data.user_pic
            all_media_items.extend(p_data.media_items)

        if not all_media_items:
            return {
                "success": False,
                "error": "Tidak ada media gambar/video yang dapat diekstrak dari Story Instagram ini."
            }

        # Dedup media items berdasarkan URL
        seen = set()
        deduped: List[MediaItem] = []
        for m in all_media_items:
            if m.url not in seen:
                seen.add(m.url)
                deduped.append(m)

        downloaded_files = []
        tasks = []
        for idx, m_item in enumerate(deduped):
            ext = "mp4" if m_item.type == "VIDEO" else "jpg"
            fn = f"{prefix}_{idx}.{ext}"
            fp = os.path.join(self.download_dir, fn)
            downloaded_files.append(fp)
            tasks.append(self._download_single_file(m_item.url, fp))

        results = await asyncio.gather(*tasks)
        final_files = [p for p, ok in zip(downloaded_files, results) if ok]

        if not final_files:
            return {
                "success": False,
                "error": "Gagal mengunduh file media Story dari server CDN Instagram."
            }

        post_data = InstagramPostData(
            post_id=prefix,
            shortcode=prefix,
            username=real_username,
            user_pic=user_pic,
            caption=f"Instagram Story dari @{real_username}",
            posted_at=int(time.time()),
            like_count=0,
            reply_count=0,
            media_type="CAROUSEL" if len(final_files) > 1 else ("SINGLE_VIDEO" if final_files[0].endswith('.mp4') else "SINGLE_IMAGE"),
            media_items=deduped,
            downloaded_files=final_files
        )

        return {"success": True, "data": post_data.to_dict()}

    async def download_story(self, url: str) -> Dict[str, Any]:
        """
        Download Instagram Story atau Highlight.
        Mengekstrak via Instagram Mobile/Web API dengan cookies fallback.
        Mendukung:
        - Single story: https://www.instagram.com/stories/{username}/{story_id}/
        - Highlight: https://www.instagram.com/stories/highlights/{highlight_id}/
        - Highlight share link: https://www.instagram.com/s/{base64_highlight}/
        - User active stories: https://www.instagram.com/stories/{username}/
        """
        debug_file = os.path.join(_LOGS_DIR, "debug_ig.html")

        # 1. Deteksi format highlight / single story / user story
        highlight_id = None
        story_id = None
        username = "ig_story_user"

        # Cek share link /s/{code}
        if "/s/" in url:
            m_s = re.search(r'/s/([a-zA-Z0-9_-]+)', url)
            if m_s:
                code = m_s.group(1)
                try:
                    padded = code + '=' * (-len(code) % 4)
                    decoded = base64.b64decode(padded).decode('utf-8', errors='ignore')
                    if "highlight:" in decoded:
                        highlight_id = decoded.split("highlight:")[1].split("?")[0].split("&")[0]
                except Exception:
                    pass

        # Cek highlight standard: stories/highlights/{id}
        if not highlight_id:
            m_hl = re.search(r'stories/highlights/(\d+)', url)
            if m_hl:
                highlight_id = m_hl.group(1)

        # Cek single story item: stories/{username}/{story_id}
        if not highlight_id:
            m_single = re.search(r'stories/(?!highlights/)([^/?#&]+)/(\d+)', url)
            if m_single:
                username = m_single.group(1)
                story_id = m_single.group(2)
            else:
                m_user = re.search(r'stories/(?!highlights/)([^/?#&]+)', url)
                if m_user:
                    username = m_user.group(1)

        # 2. Cek Mode Cookieless vs Cookies Autentikasi
        if not self.has_session:
            # Cookieless Story TIDAK didukung oleh Meta
            debug_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Instagram Story Debug Log - Cookieless Restriction</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 25px; line-height: 1.6; background: #fafafa; color: #262626; }}
    .card {{ background: white; max-width: 750px; margin: auto; padding: 25px; border-radius: 12px; border: 1px solid #dbdbdb; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
    h2 {{ color: #ed4956; margin-top: 0; }}
    .alert-box {{ background: #fff1f0; border: 1px solid #ffa39e; border-radius: 8px; padding: 15px; margin: 15px 0; color: #cf1322; }}
    .info-box {{ background: #f6ffed; border: 1px solid #b7eb8f; border-radius: 8px; padding: 15px; margin: 15px 0; color: #389e0d; }}
    code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace; }}
    ul {{ margin: 8px 0; padding-left: 20px; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>⚠️ Instagram Story Cookieless Restriction</h2>
    <p><b>Target URL:</b> <a href="{url}">{url}</a></p>
    <p><b>Target Terdeteksi:</b> Username=<code>{username}</code>, StoryID=<code>{story_id or 'None'}</code>, HighlightID=<code>{highlight_id or 'None'}</code></p>
    <p><b>Status Cookies:</b> {len(self.cookies)} cookies dimuat (tetapi <code>sessionid</code> tidak ditemukan).</p>
    
    <div class="alert-box">
      <b>Penyebab Kegagalan:</b>
      <ul>
        <li>Konten <b>Instagram Stories & Highlights</b> tidak memiliki antarmuka web publik terbuka.</li>
        <li>Meta secara ketat mengunci endpoint Story di balik session login resmi (<code>sessionid</code>). Setiap permintaan unauthenticated (cookieless) langsung dialihkan oleh Instagram ke <code>/accounts/login/</code>.</li>
        <li>Postingan Feed, Carousel, dan Reels publik tetap dapat diunduh 100% tanpa cookies (cookieless). Namun fitur Story secara teknis memerlukan autentikasi session.</li>
      </ul>
    </div>
    
    <div class="info-box">
      <b>Solusi:</b>
      <p>Sediakan cookies akun Instagram aktif yang mengandung <code>sessionid</code> pada file <code>dbbot/cookies/ig.txt</code>.</p>
    </div>
  </div>
</body>
</html>"""
            _save_debug_log(debug_content)
            logger.info(f"[InstagramScraper] Diagnostic story cookieless disimpan di '{debug_file}'.")

            return {
                "success": False,
                "error": (
                    "Instagram Story tidak bisa diunduh secara cookieless (tanpa login).\n"
                    "Meta mengunci seluruh konten Story 24 jam di balik autentikasi akun (berbeda dengan Post/Reels yang bisa diunduh cookieless).\n"
                    "Silakan sediakan cookies akun IG yang memiliki 'sessionid' di dbbot/cookies/ig.txt untuk mengunduh Story."
                ),
                "error_type": "LoginRequiredException"
            }

        # 3. Mode Cookies Fallback (Memiliki sessionid aktif)
        # 3a. Highlight Story
        if highlight_id:
            logger.info(f"[InstagramScraper] Mengunduh Highlight ID: {highlight_id} via reels_media...")
            items, debug_info = await self._fetch_reels_media_with_cookies(f"highlight:{highlight_id}")
            if items:
                return await self._process_story_items(items, f"highlight_{highlight_id}", username)
            else:
                _save_debug_log(debug_info or f"Gagal mengambil Highlight {highlight_id}")
                return {
                    "success": False,
                    "error": f"Gagal mengambil Highlight Instagram ({highlight_id}). Pastikan highlight masih aktif dan akun tidak privat/diblokir. Detail disimpan di '{debug_file}'."
                }

        # 3b. Single Story dengan numeric story_id
        if story_id and story_id.isdigit():
            media_id = int(story_id)
            logger.info(f"[InstagramScraper] Mengunduh Story ID: {media_id} via media info API...")
            api_item, debug_info = await self._fetch_api_with_cookies(media_id)
            if api_item:
                return await self._process_story_items([api_item], f"story_{story_id}", username)

            _save_debug_log(debug_info or f"Gagal mengambil Story ID {story_id}")
            return {
                "success": False,
                "error": f"Story Instagram tidak ditemukan atau akun bersifat privat (pastikan akun IG pada cookies mengikuti akun target jika privat, atau story sudah kadaluarsa >24 jam). Log disimpan di '{debug_file}'."
            }

        # 3c. User Active Stories (stories/{username}/)
        if username and username != "ig_story_user":
            logger.info(f"[InstagramScraper] Mencoba mengunduh active stories untuk user: {username}...")
            try:
                user_id = await self._resolve_username_to_id(username)
                if user_id:
                    items, debug_info = await self._fetch_reels_media_with_cookies(str(user_id))
                    if items:
                        return await self._process_story_items(items, f"user_stories_{username}", username)
                    elif debug_info:
                        _save_debug_log(debug_info)
            except Exception as u_err:
                logger.debug(f"[InstagramScraper] Gagal resolve user_id {username}: {u_err}")

        # Jika semua penanganan story gagal
        _save_debug_log(f"Gagal mengunduh story Instagram: {url}\nCookies loaded: {len(self.cookies)}, Has session: {self.has_session}")

        return {
            "success": False,
            "error": f"Gagal mengunduh story Instagram (story mungkin sudah kadaluarsa >24 jam, akun privat, atau session cookies perlu di-update). Log disimpan di '{debug_file}'."
        }

    async def download_post(self, url: str) -> Dict[str, Any]:
        """
        Mengunduh postingan Instagram (foto, video, carousel/album, atau reels).
        Returns:
            {"success": True, "data": InstagramPostData.to_dict()} atau
            {"success": False, "error": str, "error_type": str}
        """
        try:
            if "instagram.com/stories" in url:
                return await self.download_story(url)

            post_data = await self.get_post_info(url)

            if not post_data.media_items:
                post_data.downloaded_files = []
                return {"success": True, "data": post_data.to_dict()}

            downloaded_paths = []
            tasks = []
            for index, item in enumerate(post_data.media_items):
                ext = "mp4" if item.type == "VIDEO" else "jpg"
                filename = f"ig_{post_data.shortcode}_{index}.{ext}"
                full_path = os.path.join(self.download_dir, filename)

                downloaded_paths.append(full_path)
                tasks.append(self._download_single_file(item.url, full_path))

            results = await asyncio.gather(*tasks)
            final_downloaded_files = [path for path, success in zip(downloaded_paths, results) if success]
            post_data.downloaded_files = final_downloaded_files

            if not final_downloaded_files:
                return {
                    "success": False,
                    "error": f"Gagal mengunduh file media dari server CDN Instagram untuk postingan {post_data.shortcode}."
                }

            return {"success": True, "data": post_data.to_dict()}

        except InstagramScraperException as ise:
            return {"success": False, "error": str(ise), "error_type": ise.__class__.__name__}
        except Exception as e:
            return {"success": False, "error": f"Internal error: {str(e)}", "error_type": "UnhandledException"}