import os
import re
import json
import logging
import asyncio
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
import aiohttp
from .aria2_dl import aria2_download

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("BlueskyScraper")


class BlueskyScraperException(Exception):
    pass


class PostNotFoundException(BlueskyScraperException):
    pass


class ParsingException(BlueskyScraperException):
    pass


@dataclass
class MediaItem:
    type: str  # "IMAGE" atau "VIDEO"
    url: str
    width: int
    height: int


@dataclass
class BlueskyPostData:
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


class BlueskyScraper:
    """
    Scraper untuk Bluesky (bsky.app).
    Menggunakan API resmi AT Protocol publik (public.api.bsky.app) yang 100% cookieless,
    stabil, dan mendukung gambar resolusi penuh serta video.
    """

    def __init__(self, download_dir: str = "./downloads/bluesky", max_concurrent_downloads: int = 5):
        self.download_dir = download_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
        self.api_base = "https://public.api.bsky.app/xrpc"
        os.makedirs(self.download_dir, exist_ok=True)

    def extract_post_keys(self, url: str) -> tuple[str, str]:
        """
        Ekstrak handle/DID dan rkey dari URL Bluesky.
        Contoh: https://bsky.app/profile/user.bsky.social/post/3l4abc123
        Returns: (handle_or_did, rkey)
        """
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        parts = [p for p in path.split('/') if p]

        if 'profile' in parts and 'post' in parts:
            prof_idx = parts.index('profile')
            post_idx = parts.index('post')
            if prof_idx + 1 < len(parts) and post_idx + 1 < len(parts):
                actor = parts[prof_idx + 1]
                rkey = parts[post_idx + 1].split('?')[0]
                return actor, rkey

        # Cek regex alternatif
        m = re.search(r'bsky\.app/profile/([^/]+)/post/([^/?#]+)', url)
        if m:
            return m.group(1), m.group(2)

        raise BlueskyScraperException(f"Format URL Bluesky tidak valid: {url}")

    async def _resolve_handle_to_did(self, handle: str) -> str:
        """Resolve handle Bluesky (misal user.bsky.social) menjadi DID (did:plc:...)."""
        if handle.startswith("did:"):
            return handle

        url = f"{self.api_base}/com.atproto.identity.resolveHandle?handle={handle}"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        did = data.get("did")
                        if did:
                            return did
                    raise PostNotFoundException(f"Pengguna Bluesky @{handle} tidak ditemukan.")
        except PostNotFoundException:
            raise
        except Exception as e:
            logger.error(f"[Bluesky] Error resolve handle: {e}")
            raise BlueskyScraperException(f"Gagal menghubungkan identitas Bluesky: {e}")

    async def get_post_info(self, url: str) -> BlueskyPostData:
        """Ambil data postingan Bluesky via endpoint getPostThread."""
        actor, rkey = self.extract_post_keys(url)
        did = await self._resolve_handle_to_did(actor)

        uri = f"at://{did}/app.bsky.feed.post/{rkey}"
        api_url = f"{self.api_base}/app.bsky.feed.getPostThread?uri={uri}&depth=0"

        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(api_url) as resp:
                    if resp.status == 404:
                        raise PostNotFoundException("Postingan Bluesky tidak ditemukan atau sudah dihapus.")
                    if resp.status != 200:
                        raise BlueskyScraperException(f"Gagal mengambil postingan Bluesky. HTTP Status: {resp.status}")

                    data = await resp.json()
        except (PostNotFoundException, BlueskyScraperException):
            raise
        except Exception as e:
            raise BlueskyScraperException(f"Network error Bluesky API: {e}")

        thread = data.get("thread", {})
        post = thread.get("post")
        if not post:
            raise PostNotFoundException("Konten postingan tidak ditemukan dalam respon thread.")

        author = post.get("author", {})
        username = author.get("handle") or actor
        user_pic = author.get("avatar")

        record = post.get("record", {})
        caption = record.get("text", "")
        like_count = post.get("likeCount", 0) or 0
        reply_count = post.get("replyCount", 0) or 0

        # Waktu posting
        created_at_str = record.get("createdAt", "")
        posted_at = int(time.time())

        # Ekstraksi media (Images / Video)
        media_items: List[MediaItem] = []
        embed = post.get("embed", {})
        embed_type = embed.get("$type", "")

        # Jika embed terbungkus dalam recordWithMedia
        if "recordWithMedia" in embed_type:
            embed = embed.get("media", {})
            embed_type = embed.get("$type", "")

        # A. Gambar
        if "images" in embed_type:
            images = embed.get("images", [])
            for img in images:
                fullsize = img.get("fullsize")
                aspect = img.get("aspectRatio", {})
                w = aspect.get("width", 0) or 0
                h = aspect.get("height", 0) or 0
                if fullsize:
                    media_items.append(MediaItem(type="IMAGE", url=fullsize, width=w, height=h))

        # B. Video
        elif "video" in embed_type:
            playlist = embed.get("playlist")
            thumbnail = embed.get("thumbnail")
            aspect = embed.get("aspectRatio", {})
            w = aspect.get("width", 0) or 0
            h = aspect.get("height", 0) or 0
            if playlist:
                media_items.append(MediaItem(type="VIDEO", url=playlist, width=w, height=h))
            elif thumbnail:
                media_items.append(MediaItem(type="IMAGE", url=thumbnail, width=w, height=h))

        if not media_items:
            media_type = "TEXT_ONLY"
        elif len(media_items) == 1:
            media_type = "SINGLE_VIDEO" if media_items[0].type == "VIDEO" else "SINGLE_IMAGE"
        else:
            media_type = "CAROUSEL"

        return BlueskyPostData(
            post_id=rkey,
            shortcode=rkey,
            username=username,
            user_pic=user_pic,
            caption=caption,
            posted_at=posted_at,
            like_count=like_count,
            reply_count=reply_count,
            media_type=media_type,
            media_items=media_items
        )

    async def _download_single_file(self, item: MediaItem, dest_path: str) -> bool:
        """Download file media atau stream video m3u8 menggunakan aria2 atau ffmpeg."""
        async with self.semaphore:
            # Jika video berformat HLS (m3u8), gunakan ffmpeg untuk merender ke MP4
            if item.type == "VIDEO" and (".m3u8" in item.url or "playlist" in item.url):
                cmd = [
                    "ffmpeg", "-y",
                    "-i", item.url,
                    "-c", "copy",
                    "-bsf:a", "aac_adtstoasc",
                    dest_path
                ]
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    await proc.communicate()
                    return proc.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0
                except Exception as e:
                    logger.error(f"[Bluesky] FFmpeg HLS download error: {e}")
                    return False
            else:
                return await aria2_download(item.url, dest_path)

    async def download_post(self, url: str) -> Dict[str, Any]:
        """
        Download postingan Bluesky beserta gambar/videonya.
        Returns:
            {"success": True, "data": BlueskyPostData.to_dict()} atau
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
                filename = f"bluesky_{post_data.shortcode}_{index}.{ext}"
                full_path = os.path.join(self.download_dir, filename)

                downloaded_paths.append(full_path)
                tasks.append(self._download_single_file(item, full_path))

            results = await asyncio.gather(*tasks)
            final_downloaded_files = [path for path, success in zip(downloaded_paths, results) if success]
            post_data.downloaded_files = final_downloaded_files

            return {"success": True, "data": post_data.to_dict()}

        except BlueskyScraperException as bse:
            return {"success": False, "error": str(bse), "error_type": bse.__class__.__name__}
        except Exception as e:
            return {"success": False, "error": f"Internal error: {str(e)}", "error_type": "UnhandledException"}
