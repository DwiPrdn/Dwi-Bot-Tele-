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
logger = logging.getLogger("CapCutScraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
]


class CapCutScraperException(Exception):
    pass


class PostNotFoundException(CapCutScraperException):
    pass


class ParsingException(CapCutScraperException):
    pass


@dataclass
class MediaItem:
    type: str  # "VIDEO"
    url: str
    width: int
    height: int


@dataclass
class CapCutPostData:
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


class CapCutScraper:
    """
    Scraper untuk CapCut (capcut.com, template-detail, link pendek capcut.com/t/...).
    Mengekstrak video preview template tanpa watermark dalam resolusi penuh (MP4).
    """

    def __init__(self, download_dir: str = "./downloads/capcut", max_concurrent_downloads: int = 5):
        self.download_dir = download_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
        os.makedirs(self.download_dir, exist_ok=True)

    async def _resolve_redirect(self, url: str) -> str:
        """Resolve link pendek capcut.com/t/... atau share link."""
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    resolved = str(resp.url)
                    logger.info(f"[CapCut] Resolved {url} -> {resolved}")
                    return resolved
        except Exception as e:
            logger.warning(f"[CapCut] Gagal resolve redirect: {e}")
            return url

    def extract_template_id(self, url: str) -> str:
        """Ekstrak template ID dari URL CapCut."""
        m = re.search(r'template-detail/(\d+)', url)
        if m:
            return m.group(1)
        m_t = re.search(r'/t/([A-Za-z0-9_-]+)', url)
        if m_t:
            return m_t.group(1)
        parsed = urlparse(url)
        parts = [p for p in parsed.path.strip('/').split('/') if p]
        if parts:
            for p in reversed(parts):
                if p.isdigit():
                    return p
            return parts[-1]
        return str(int(time.time()))

    async def _fetch_html(self, url: str) -> str:
        """Mengambil konten HTML dari URL CapCut."""
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as resp:
                    if resp.status == 404:
                        raise PostNotFoundException("Template CapCut tidak ditemukan atau sudah dihapus.")
                    if resp.status != 200:
                        raise CapCutScraperException(f"Gagal mengambil halaman CapCut. HTTP Status: {resp.status}")
                    return await resp.text()
        except (PostNotFoundException, CapCutScraperException):
            raise
        except Exception as e:
            raise CapCutScraperException(f"Network error CapCut: {str(e)}")

    def _extract_template_data(self, html_content: str, template_id: str) -> CapCutPostData:
        """Ekstrak video URL MP4, judul, deskripsi, dan kreator template dari HTML."""
        soup = BeautifulSoup(html_content, "html.parser")

        video_url = None

        for prop in ["og:video:url", "og:video:secure_url", "og:video", "twitter:player:stream"]:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content") and tag.get("content").startswith("http"):
                video_url = tag.get("content")
                break

        if not video_url:
            for v in soup.find_all("video"):
                src = v.get("src")
                if src and src.startswith("http"):
                    video_url = src
                    break

        if not video_url:
            mp4_matches = re.findall(r'https:[^\"\'\s\<\>]+\.mp4[^\"\'\s\<\>]*', html_content)
            for m in mp4_matches:
                clean_m = m.replace('\\/', '/').replace('&amp;', '&')

                video_url = clean_m
                break

        if not video_url:
            raise ParsingException("Gagal menemukan link video MP4 pada template CapCut ini.")

        og_title = soup.find("meta", property="og:title")
        og_desc = soup.find("meta", property="og:description")
        meta_desc = soup.find("meta", attrs={"name": "description"})

        title_val = (og_title.get("content") if og_title else "") or ""
        caption_val = (
            (og_desc.get("content") if og_desc else "")
            or (meta_desc.get("content") if meta_desc else "")
            or title_val
        ).strip()

        caption_clean = re.sub(r'^CapCut template:\s*', '', caption_val).strip()
        if not caption_clean:
            caption_clean = "CapCut Template"

        username = "CapCut Creator"
        m_author = re.search(r'by\s+([A-Za-z0-9_\.\s]+)\s+on\s+CapCut', caption_val, re.IGNORECASE)
        if m_author:
            username = m_author.group(1).strip() or username

        return CapCutPostData(
            post_id=template_id,
            shortcode=template_id,
            username=username,
            user_pic=None,
            caption=caption_clean,
            posted_at=int(time.time()),
            like_count=0,
            reply_count=0,
            media_type="SINGLE_VIDEO",
            media_items=[MediaItem(type="VIDEO", url=video_url, width=1080, height=1920)]
        )

    async def _download_single_file(self, url: str, dest_path: str) -> bool:
        """Unduh video CapCut via aria2c."""
        async with self.semaphore:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            return await aria2_download(url, dest_path, headers=headers)

    async def get_post_info(self, url: str) -> CapCutPostData:
        """Mengambil info template CapCut."""
        resolved_url = await self._resolve_redirect(url)
        template_id = self.extract_template_id(resolved_url)
        html_content = await self._fetch_html(resolved_url)
        return self._extract_template_data(html_content, template_id)

    async def download_post(self, url: str) -> Dict[str, Any]:
        """
        Download video preview template dari CapCut.
        Returns:
            {"success": True, "data": CapCutPostData.to_dict()} atau
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
                filename = f"capcut_{post_data.shortcode}_{index}.mp4"
                full_path = os.path.join(self.download_dir, filename)

                downloaded_paths.append(full_path)
                tasks.append(self._download_single_file(item.url, full_path))

            results = await asyncio.gather(*tasks)
            final_downloaded_files = [path for path, success in zip(downloaded_paths, results) if success]
            post_data.downloaded_files = final_downloaded_files

            return {"success": True, "data": post_data.to_dict()}

        except CapCutScraperException as cse:
            return {"success": False, "error": str(cse), "error_type": cse.__class__.__name__}
        except Exception as e:
            return {"success": False, "error": f"Internal error: {str(e)}", "error_type": "UnhandledException"}
