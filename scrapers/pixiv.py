import os
import re
import json
import logging
import asyncio
import zipfile
import shutil
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from urllib.parse import urlparse, parse_qs
import aiohttp
from bs4 import BeautifulSoup
from .aria2_dl import aria2_download

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("PixivScraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
]


class PixivScraperException(Exception):
    pass


class PostNotFoundException(PixivScraperException):
    pass


class ParsingException(PixivScraperException):
    pass


@dataclass
class MediaItem:
    type: str  # "IMAGE" atau "VIDEO"
    url: str
    width: int = 0
    height: int = 0


@dataclass
class PixivPostData:
    post_id: str
    shortcode: str
    username: str
    user_pic: Optional[str]
    caption: str
    posted_at: int
    like_count: int
    reply_count: int  # Dipetakan ke bookmark_count
    media_type: str
    media_items: List[MediaItem]
    downloaded_files: List[str] = None
    title: str = ""
    author_id: str = ""
    tags: List[str] = None
    is_ugoira: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PixivScraper:
    """
    Scraper untuk platform Pixiv (pixiv.net).
    Mendukung ilustrasi tunggal, manga (multi-page album), dan animasi Ugoira.
    Bekerja secara cookieless untuk karya publik, dengan opsi fallback cookie (PHPSESSID) untuk R-18.
    """

    def __init__(
        self,
        download_dir: str = "./downloads/pixiv",
        cookie_file: Optional[str] = None
    ):
        self.download_dir = download_dir
        self.cookie_file = cookie_file
        self.cookies: Dict[str, str] = {}
        if cookie_file and os.path.exists(cookie_file):
            try:
                if cookie_file.endswith('.json'):
                    with open(cookie_file, 'r', encoding='utf-8') as f:
                        self.cookies = json.load(f)
                else:
                    # Netscape / header format
                    with open(cookie_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            parts = line.strip().split('\t')
                            if len(parts) >= 7:
                                self.cookies[parts[5]] = parts[6]
            except Exception as e:
                logger.warning(f"Gagal memuat cookies Pixiv: {e}")
        os.makedirs(self.download_dir, exist_ok=True)

    def extract_illust_id(self, url: str) -> str:
        """Mengekstrak ID ilustrasi dari berbagai format URL Pixiv."""
        # Format: pixiv.net/(en/)?artworks/(\d+)
        m = re.search(r'artworks/(\d+)', url)
        if m:
            return m.group(1)

        # Format: pixiv.net/i/(\d+)
        m = re.search(r'pixiv\.net/i/(\d+)', url)
        if m:
            return m.group(1)

        # Format query: illust_id=(\d+)
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if 'illust_id' in qs and qs['illust_id']:
            return qs['illust_id'][0]

        # Format path: /member_illust.php / ... / (\d+)
        m = re.search(r'(\d{6,12})', url)
        if m:
            return m.group(1)

        raise PixivScraperException(f"Gagal mengekstrak ID ilustrasi dari URL: {url}")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": USER_AGENTS[0],
            "Referer": "https://www.pixiv.net/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8,id;q=0.7"
        }

    async def get_post_info(self, url: str) -> PixivPostData:
        """
        Mengambil metadata karya Pixiv dari endpoint AJAX resmi.
        """
        illust_id = self.extract_illust_id(url)
        ajax_url = f"https://www.pixiv.net/ajax/illust/{illust_id}"

        headers = self._get_headers()
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            async with session.get(ajax_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    raise PostNotFoundException(f"Pixiv mengembalikan status {resp.status} untuk ID {illust_id}")
                data = await resp.json()

        if data.get("error"):
            msg = data.get("message") or "Unknown error"
            raise PostNotFoundException(f"Gagal mengambil karya Pixiv: {msg}")

        body = data.get("body", {})
        if not body:
            raise ParsingException("Data karya Pixiv kosong.")

        title = body.get("title") or body.get("illustTitle") or f"Pixiv Illust {illust_id}"
        author_name = body.get("userName") or "Pixiv Artist"
        author_id = str(body.get("userId") or "")
        like_count = int(body.get("likeCount") or 0)
        bookmark_count = int(body.get("bookmarkCount") or 0)
        view_count = int(body.get("viewCount") or 0)
        page_count = int(body.get("pageCount") or 1)
        illust_type = int(body.get("illustType") or 0)  # 0: illust, 1: manga, 2: ugoira
        is_ugoira = (illust_type == 2)

        # Bersihkan deskripsi HTML
        raw_desc = body.get("description") or body.get("illustComment") or ""
        clean_desc = BeautifulSoup(raw_desc, "html.parser").get_text("\n").strip()

        tags_data = body.get("tags", {}).get("tags", [])
        tags_list = [t.get("tag") for t in tags_data if isinstance(t, dict) and t.get("tag")]

        media_items = []

        if is_ugoira:
            # Ugoira (animasi)
            media_items.append(MediaItem(type="VIDEO", url=f"https://www.pixiv.net/ajax/illust/{illust_id}/ugoira_meta"))
        elif page_count > 1:
            # Multi-page manga / album
            pages_url = f"https://www.pixiv.net/ajax/illust/{illust_id}/pages"
            async with aiohttp.ClientSession(cookies=self.cookies) as session:
                async with session.get(pages_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as p_resp:
                    if p_resp.status == 200:
                        p_data = await p_resp.json()
                        pages = p_data.get("body", [])
                        for page in pages:
                            orig_url = page.get("urls", {}).get("original")
                            if orig_url:
                                media_items.append(MediaItem(type="IMAGE", url=orig_url, width=page.get("width", 0), height=page.get("height", 0)))
            if not media_items:
                orig_url = body.get("urls", {}).get("original") or body.get("urls", {}).get("regular")
                if orig_url:
                    media_items.append(MediaItem(type="IMAGE", url=orig_url))
        else:
            # Single image
            orig_url = body.get("urls", {}).get("original") or body.get("urls", {}).get("regular")
            if not orig_url:
                raise ParsingException("URL gambar Pixiv tidak ditemukan (mungkin konten R-18 yang membutuhkan login).")
            media_items.append(MediaItem(
                type="IMAGE",
                url=orig_url,
                width=int(body.get("width") or 0),
                height=int(body.get("height") or 0)
            ))

        caption = f"✨ <b>{title}</b>\n👤 <b>{author_name}</b>"
        if clean_desc:
            caption += f"\n\n<blockquote expandable>{clean_desc[:800]}</blockquote>"
        caption += f"\n\n❤️ {like_count} Likes | ⭐ {bookmark_count} Bookmarks | 👁️ {view_count} Views\nDownloaded By @Plendes_bot"

        return PixivPostData(
            post_id=illust_id,
            shortcode=illust_id,
            username=author_name,
            user_pic=None,
            caption=caption,
            posted_at=int(time.time()),
            like_count=like_count,
            reply_count=bookmark_count,
            media_type="VIDEO" if is_ugoira else "IMAGE",
            media_items=media_items,
            title=title,
            author_id=author_id,
            tags=tags_list,
            is_ugoira=is_ugoira
        )

    async def _download_file(self, url: str, dest_path: str) -> bool:
        """Mengunduh gambar dari i.pximg.net dengan header Referer yang diperlukan."""
        headers = self._get_headers()
        try:
            async with aiohttp.ClientSession(cookies=self.cookies) as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        with open(dest_path, "wb") as f:
                            while True:
                                chunk = await resp.content.read(65536)
                                if not chunk:
                                    break
                                f.write(chunk)
                        return os.path.exists(dest_path) and os.path.getsize(dest_path) > 0
                    else:
                        logger.warning(f"Pixiv download returned HTTP {resp.status} for {url}")
                        return False
        except Exception as e:
            logger.error(f"Gagal download file Pixiv {url}: {e}")
            return False

    async def _process_ugoira(self, meta_url: str, illust_id: str) -> Optional[str]:
        """Memproses Ugoira (animasi) menjadi file video MP4 dengan FFmpeg."""
        headers = self._get_headers()
        try:
            async with aiohttp.ClientSession(cookies=self.cookies) as session:
                async with session.get(meta_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return None
                    meta_data = await resp.json()

            ugoira_body = meta_data.get("body", {})
            zip_url = ugoira_body.get("originalSrc") or ugoira_body.get("src")
            frames = ugoira_body.get("frames", [])
            if not zip_url or not frames:
                return None

            tmp_dir = os.path.join(self.download_dir, f"ugoira_{illust_id}_{int(time.time())}")
            os.makedirs(tmp_dir, exist_ok=True)
            zip_file = os.path.join(tmp_dir, "ugoira.zip")

            # Download zip
            dl_ok = await self._download_file(zip_url, zip_file)
            if not dl_ok:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return None

            # Unzip
            with zipfile.ZipFile(zip_file, 'r') as zf:
                zf.extractall(tmp_dir)

            # Hitung rata-rata delay frame untuk framerate
            delays = [f.get("delay", 100) for f in frames if isinstance(f, dict)]
            avg_delay_ms = sum(delays) / len(delays) if delays else 100
            fps = max(1.0, round(1000.0 / avg_delay_ms, 2))

            output_mp4 = os.path.join(self.download_dir, f"pixiv_ugoira_{illust_id}.mp4")

            # Buat file concat list untuk ffmpeg
            concat_txt = os.path.join(tmp_dir, "concat.txt")
            with open(concat_txt, "w") as f:
                for fr in frames:
                    f_file = fr.get("file")
                    dur_s = fr.get("delay", 100) / 1000.0
                    f.write(f"file '{f_file}'\n")
                    f.write(f"duration {dur_s}\n")
                if frames:
                    f.write(f"file '{frames[-1].get('file')}'\n")

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_txt,
                "-pix_fmt", "yuv420p",
                "-c:v", "libx264",
                "-movflags", "+faststart",
                output_mp4
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=tmp_dir,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()
            shutil.rmtree(tmp_dir, ignore_errors=True)

            if proc.returncode == 0 and os.path.exists(output_mp4) and os.path.getsize(output_mp4) > 0:
                return output_mp4
            return None

        except Exception as e:
            logger.error(f"Error memproses Ugoira Pixiv: {e}")
            return None

    async def download_post(self, url: str) -> Dict[str, Any]:
        """
        Download postingan / album Pixiv.
        Returns:
            {"success": True, "data": PixivPostData.to_dict()} atau
            {"success": False, "error": str, "error_type": str}
        """
        try:
            post_data = await self.get_post_info(url)

            if post_data.is_ugoira and post_data.media_items:
                ugoira_file = await self._process_ugoira(post_data.media_items[0].url, post_data.shortcode)
                if ugoira_file:
                    post_data.downloaded_files = [ugoira_file]
                    return {"success": True, "data": post_data.to_dict()}
                else:
                    return {"success": False, "error": "Gagal merender animasi Ugoira Pixiv.", "error_type": "RenderError"}

            downloaded_paths = []
            tasks = []
            for index, item in enumerate(post_data.media_items):
                ext = "jpg"
                u_clean = item.url.split('?')[0].lower()
                if u_clean.endswith('.png'):
                    ext = "png"
                elif u_clean.endswith('.gif'):
                    ext = "gif"

                filename = f"pixiv_{post_data.shortcode}_p{index}.{ext}"
                full_path = os.path.join(self.download_dir, filename)
                downloaded_paths.append(full_path)
                tasks.append(self._download_file(item.url, full_path))

            results = await asyncio.gather(*tasks)
            final_files = [path for path, ok in zip(downloaded_paths, results) if ok]

            if not final_files:
                return {
                    "success": False,
                    "error": "Gagal mengunduh gambar Pixiv. Jika ini karya R-18, pastikan cookie akun terpasang.",
                    "error_type": "DownloadError"
                }

            post_data.downloaded_files = final_files
            return {"success": True, "data": post_data.to_dict()}

        except PixivScraperException as pse:
            return {"success": False, "error": str(pse), "error_type": pse.__class__.__name__}
        except Exception as e:
            return {"success": False, "error": f"Internal error: {str(e)}", "error_type": "UnhandledException"}
