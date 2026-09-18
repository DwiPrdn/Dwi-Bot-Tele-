import os
import re
import json
import logging
import asyncio
import time
import urllib.parse
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
import aiohttp
from .aria2_dl import aria2_download

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("SoundCloudScraper")


class SoundCloudScraperException(Exception):
    pass


class TrackNotFoundException(SoundCloudScraperException):
    pass


class ParsingException(SoundCloudScraperException):
    pass


@dataclass
class MediaItem:
    type: str  # "AUDIO"
    url: str
    width: int = 0
    height: int = 0


@dataclass
class SoundCloudPostData:
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
    duration: float = 0.0
    downloaded_files: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SoundCloudScraper:
    """
    Scraper untuk SoundCloud (soundcloud.com & link pendek on.soundcloud.com).
    Mengekstrak audio stream lagu/track dan mengonversinya menjadi file MP3 berkualitas tinggi.
    """

    def __init__(self, download_dir: str = "./downloads/soundcloud", max_concurrent_downloads: int = 5):
        self.download_dir = download_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
        self.default_client_id = "Pb72ranhoyt6gw7hM7TkzUItXlMWSNSo"
        self._cached_client_id = self.default_client_id
        os.makedirs(self.download_dir, exist_ok=True)

    async def _resolve_redirect(self, url: str) -> str:
        """Resolve link pendek on.soundcloud.com."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    resolved = str(resp.url)
                    logger.info(f"[SoundCloud] Resolved {url} -> {resolved}")
                    return resolved
        except Exception as e:
            logger.warning(f"[SoundCloud] Gagal resolve redirect: {e}")
            return url

    async def _get_client_id(self) -> str:
        """Ambil atau perbarui client_id publik SoundCloud."""
        if self._cached_client_id:
            return self._cached_client_id

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get("https://soundcloud.com") as resp:
                    html = await resp.text()

                scripts = re.findall(r'src=\"(https://a-v2\.sndcdn\.com/assets/[^\"]+\.js)\"', html)
                for s_url in reversed(scripts):
                    async with session.get(s_url) as s_resp:
                        js = await s_resp.text()
                        m = re.findall(r'client_id:\"([a-zA-Z0-9]{32})\"', js) or re.findall(r'client_id=([a-zA-Z0-9]{32})', js)
                        if m:
                            self._cached_client_id = m[0]
                            return self._cached_client_id
        except Exception as e:
            logger.warning(f"[SoundCloud] Gagal refresh client_id dinamis: {e}")

        return self.default_client_id

    async def get_post_info(self, url: str) -> SoundCloudPostData:
        """Mengambil data lagu/track dari URL SoundCloud."""
        resolved_url = await self._resolve_redirect(url)

        # 1. Ambil metadata dan Track ID via oEmbed
        oembed_url = f"https://soundcloud.com/oembed?format=json&url={urllib.parse.quote(resolved_url)}"
        headers = {"User-Agent": "Mozilla/5.0"}

        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(oembed_url) as resp:
                    if resp.status == 404:
                        raise TrackNotFoundException("Lagu SoundCloud tidak ditemukan atau disetel privat.")
                    if resp.status != 200:
                        raise SoundCloudScraperException(f"Gagal mengakses oEmbed SoundCloud. HTTP Status: {resp.status}")

                    oembed_data = await resp.json()
        except (TrackNotFoundException, SoundCloudScraperException):
            raise
        except Exception as e:
            raise SoundCloudScraperException(f"Network error oEmbed SoundCloud: {e}")

        html_embed = oembed_data.get("html", "")
        m_tid = re.search(r'tracks(?:%2F|/)(\d+)', html_embed)
        if not m_tid:
            raise ParsingException("Gagal mengekstrak Track ID dari embed SoundCloud.")

        track_id = m_tid.group(1)
        client_id = await self._get_client_id()

        # 2. Ambil detail track & stream transcodings via v2 API
        track_api_url = f"https://api-v2.soundcloud.com/tracks/{track_id}?client_id={client_id}"
        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(track_api_url) as resp:
                    if resp.status != 200:
                        raise SoundCloudScraperException(f"Gagal mengambil data track API SoundCloud: HTTP {resp.status}")
                    track_data = await resp.json()
        except Exception as e:
            raise SoundCloudScraperException(f"Gagal query API track SoundCloud: {e}")

        title = track_data.get("title") or oembed_data.get("title") or "SoundCloud Track"
        user_info = track_data.get("user") or {}
        artist = user_info.get("username") or oembed_data.get("author_name") or "SoundCloud Artist"
        artwork = track_data.get("artwork_url") or oembed_data.get("thumbnail_url")
        duration_s = (track_data.get("duration", 0) or 0) / 1000.0
        like_count = track_data.get("likes_count", 0) or 0
        comment_count = track_data.get("comment_count", 0) or 0

        # Cari stream URL terbaik (prioritas progressive MP3, lalu HLS AAC)
        transcodings = track_data.get("media", {}).get("transcodings", [])
        if not transcodings:
            raise ParsingException("Tidak ditemukan stream audio yang tersedia untuk lagu ini.")

        chosen_stream_info = None
        # Cari progressive mp3 terlebih dahulu
        for t in transcodings:
            if t.get("format", {}).get("protocol") == "progressive":
                chosen_stream_info = t
                break

        # Fallback ke HLS
        if not chosen_stream_info:
            for t in transcodings:
                if t.get("format", {}).get("protocol") == "hls":
                    chosen_stream_info = t
                    break

        if not chosen_stream_info:
            chosen_stream_info = transcodings[0]

        # Resolve direct stream URL dari transcoding
        info_call_url = f"{chosen_stream_info.get('url')}?client_id={client_id}"
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(info_call_url) as resp:
                    if resp.status == 200:
                        s_data = await resp.json()
                        stream_direct_url = s_data.get("url")
                    else:
                        raise ParsingException(f"Gagal resolve stream URL: HTTP {resp.status}")
        except Exception as e:
            raise SoundCloudScraperException(f"Gagal menghubungi stream resolver SoundCloud: {e}")

        if not stream_direct_url:
            raise ParsingException("Stream URL audio tidak ditemukan.")

        caption = f"🎵 {title}\n👤 {artist}"

        return SoundCloudPostData(
            post_id=track_id,
            shortcode=track_id,
            username=artist,
            user_pic=artwork,
            caption=caption,
            posted_at=int(time.time()),
            like_count=like_count,
            reply_count=comment_count,
            media_type="AUDIO",
            media_items=[MediaItem(type="AUDIO", url=stream_direct_url)],
            duration=duration_s
        )

    async def _download_audio(self, stream_url: str, dest_path: str, title: str, artist: str) -> bool:
        """Download dan encode audio ke MP3 menggunakan ffmpeg (atau aria2 jika mp3 langsung)."""
        async with self.semaphore:
            # Gunakan FFmpeg untuk mengunduh dan mengonversi stream (termasuk HLS) ke MP3 berkualitas 192k
            cmd = [
                "ffmpeg", "-y",
                "-i", stream_url,
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                "-metadata", f"title={title}",
                "-metadata", f"artist={artist}",
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
                logger.error(f"[SoundCloud] FFmpeg error: {e}")
                return False

    async def download_post(self, url: str) -> Dict[str, Any]:
        """
        Download lagu dari SoundCloud dan simpan dalam format MP3.
        Returns:
            {"success": True, "data": SoundCloudPostData.to_dict()} atau
            {"success": False, "error": str, "error_type": str}
        """
        try:
            post_data = await self.get_post_info(url)

            filename = f"soundcloud_{post_data.shortcode}.mp3"
            full_path = os.path.join(self.download_dir, filename)

            stream_url = post_data.media_items[0].url
            title = post_data.caption.split('\n')[0].replace("🎵", "").strip()

            success = await self._download_audio(stream_url, full_path, title=title, artist=post_data.username)

            if success:
                post_data.downloaded_files = [full_path]
                return {"success": True, "data": post_data.to_dict()}
            else:
                return {"success": False, "error": "Gagal merender file MP3 dari SoundCloud.", "error_type": "DownloadError"}

        except SoundCloudScraperException as sce:
            return {"success": False, "error": str(sce), "error_type": sce.__class__.__name__}
        except Exception as e:
            return {"success": False, "error": f"Internal error: {str(e)}", "error_type": "UnhandledException"}
