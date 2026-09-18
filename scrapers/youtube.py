import os
import re
import json
import asyncio
import logging
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple
import aiohttp
from .aria2_dl import aria2_download

logger = logging.getLogger(__name__)

class YouTubeScraper:
    """
    Scraper YouTube khusus untuk mengekstrak dan mengunduh:
    1. Postingan Komunitas (Community Posts) - baik foto tunggal maupun carousel/multi-image.
    2. Postingan Teks & Poll Komunitas.
    3. Video YouTube / Shorts reguler maupun video lampiran di postingan komunitas via yt-dlp.
    """
    def __init__(self, download_dir: str, cookie_file: Optional[str] = None):
        self.download_dir = download_dir
        self.cookie_file = cookie_file
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir, exist_ok=True)

    @staticmethod
    def extract_post_id(url: str) -> Optional[str]:
        """Ekstrak ID postingan komunitas YouTube (dimulai dengan 'Ug')."""
        # Format 1: youtube.com/post/Ugkx...
        m1 = re.search(r'/post/(Ug[a-zA-Z0-9_-]+)', url)
        if m1:
            return m1.group(1)
        # Format 2: youtube.com/.../community?lb=Ugkx...
        m2 = re.search(r'[?&]lb=(Ug[a-zA-Z0-9_-]+)', url)
        if m2:
            return m2.group(1)
        return None

    @staticmethod
    def is_community_url(url: str) -> bool:
        """Cek apakah URL adalah link postingan komunitas."""
        return bool(re.search(r'(/post/Ug|[?&]lb=Ug|/posts|/community)', url))

    @staticmethod
    def _parse_vote_count(text: Optional[str]) -> int:
        """Konversi teks vote/like YouTube seperti '12K' atau '1.5M' ke integer."""
        if not text:
            return 0
        text = text.strip().replace(',', '')
        try:
            if text.endswith('K') or text.endswith('k'):
                return int(float(text[:-1]) * 1000)
            elif text.endswith('M') or text.endswith('m'):
                return int(float(text[:-1]) * 1000000)
            return int(text)
        except Exception:
            return 0

    async def _fetch_community_post_html(self, post_id: str) -> Optional[str]:
        """Ambil HTML halaman postingan komunitas dari YouTube."""
        url = f"https://www.youtube.com/post/{post_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.text()
        except Exception as e:
            logger.error(f"[YouTube] Gagal fetch HTML untuk post {post_id}: {e}")
        return None

    def _extract_post_renderer(self, html_data: str) -> Optional[dict]:
        """Cari objek backstagePostRenderer dari ytInitialData di HTML."""
        m = re.search(r'var ytInitialData\s*=\s*({.*?});</script>', html_data, re.DOTALL)
        if not m:
            m = re.search(r'>ytInitialData\s*=\s*({.*?});<', html_data, re.DOTALL)
        if not m:
            return None

        try:
            data = json.loads(m.group(1))
            posts = []

            def find_posts(o):
                if isinstance(o, dict):
                    if 'backstagePostRenderer' in o:
                        posts.append(o['backstagePostRenderer'])
                    elif 'sharedPostRenderer' in o:
                        posts.append(o['sharedPostRenderer'])
                    elif 'postRenderer' in o:
                        posts.append(o['postRenderer'])
                    for v in o.values():
                        find_posts(v)
                elif isinstance(o, list):
                    for it in o:
                        find_posts(it)

            find_posts(data)
            if posts:
                return posts[0]
        except Exception as e:
            logger.error(f"[YouTube] Gagal parse ytInitialData: {e}")

        return None

    async def _download_community_post(self, post_id: str) -> dict:
        """Download postingan komunitas YouTube (gambar atau teks)."""
        html_data = await self._fetch_community_post_html(post_id)
        if not html_data:
            return {"success": False, "error": "Gagal mengambil data halaman postingan komunitas YouTube."}

        post = self._extract_post_renderer(html_data)
        if not post:
            return {"success": False, "error": "Gagal menemukan data konten postingan di halaman YouTube."}

        author = "youtube_creator"
        author_runs = post.get('authorText', {}).get('runs', [])
        if author_runs and author_runs[0].get('text'):
            author = author_runs[0]['text']

        content_runs = post.get('contentText', {}).get('runs', [])
        caption = ''.join(r.get('text', '') for r in content_runs).strip()

        vote_text = post.get('voteCount', {}).get('simpleText')
        like_count = self._parse_vote_count(vote_text)
        reply_count = 0

        # Ambil media attachments
        attachment = post.get('backstageAttachment', {})
        image_urls: List[str] = []
        video_id = None

        # 1. Multi-image carousel
        if 'postMultiImageRenderer' in attachment:
            images = attachment['postMultiImageRenderer'].get('images', [])
            for item in images:
                b_img = item.get('backstageImageRenderer', {})
                thumbs = b_img.get('image', {}).get('thumbnails', [])
                if thumbs:
                    best_url = thumbs[-1].get('url', '')
                    if best_url:
                        # Dapatkan resolusi penuh original
                        clean_u = re.sub(r'=s\d+.*$', '=s0', best_url)
                        if clean_u.startswith('//'):
                            clean_u = 'https:' + clean_u
                        image_urls.append(clean_u)

        # 2. Single image
        elif 'backstageImageRenderer' in attachment:
            thumbs = attachment['backstageImageRenderer'].get('image', {}).get('thumbnails', [])
            if thumbs:
                best_url = thumbs[-1].get('url', '')
                if best_url:
                    clean_u = re.sub(r'=s\d+.*$', '=s0', best_url)
                    if clean_u.startswith('//'):
                        clean_u = 'https:' + clean_u
                    image_urls.append(clean_u)

        # 3. Video attachment
        elif 'videoRenderer' in attachment:
            video_id = attachment['videoRenderer'].get('videoId')

        downloaded_files: List[str] = []

        # Download semua gambar
        if image_urls:
            dl_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            for idx, img_url in enumerate(image_urls):
                file_path = f"{self.download_dir}/{post_id}_{idx}.jpg"
                ok = await aria2_download(img_url, file_path, headers=dl_headers)
                if ok and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    downloaded_files.append(file_path)
                else:
                    # Fallback direct aiohttp
                    try:
                        async with aiohttp.ClientSession(headers=dl_headers) as sess:
                            async with sess.get(img_url) as resp:
                                if resp.status == 200:
                                    with open(file_path, "wb") as f:
                                        f.write(await resp.read())
                                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                        downloaded_files.append(file_path)
                    except Exception as dl_err:
                        logger.error(f"[YouTube] Direct aiohttp image dl failed: {dl_err}")

        # Jika postingan ini melampirkan video, download videonya via yt-dlp
        elif video_id:
            vid_url = f"https://www.youtube.com/watch?v=v_temp_{video_id}"
            vid_result = await self._download_video_ytdlp(f"https://www.youtube.com/watch?v={video_id}", prefix=post_id)
            if vid_result.get("success") and vid_result.get("data", {}).get("downloaded_files"):
                downloaded_files.extend(vid_result["data"]["downloaded_files"])

        # Jika postingan murni teks/poll tanpa media, tetap kembalikan data caption
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

    async def _download_video_ytdlp(self, url: str, prefix: str = "yt") -> dict:
        """Download video / shorts YouTube menggunakan yt-dlp."""
        out_template = f"{self.download_dir}/{prefix}_%(id)s.%(ext)s"
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--no-colors",
            "-S", "res:1080,ext:mp4:m4a",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "--write-info-json",
            "-o", out_template,
        ]
        if self.cookie_file and os.path.exists(self.cookie_file):
            cmd.extend(["--cookies", self.cookie_file])
        cmd.append(url)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='ignore')[-300:] if stderr else "Gagal download video via yt-dlp."
                logger.error(f"[YouTube] yt-dlp failed: {err_msg}")
                return {"success": False, "error": err_msg}

            # Cari file video hasil download
            vid_files = []
            author = "youtube_creator"
            caption = ""

            for fname in os.listdir(self.download_dir):
                if fname.startswith(f"{prefix}_") and fname.endswith(".mp4"):
                    full_p = os.path.join(self.download_dir, fname)
                    if os.path.getsize(full_p) > 1024:
                        vid_files.append(full_p)
                elif fname.startswith(f"{prefix}_") and fname.endswith(".info.json"):
                    try:
                        with open(os.path.join(self.download_dir, fname), "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            author = meta.get("uploader") or meta.get("channel") or author
                            caption = meta.get("title") or meta.get("description") or caption
                    except Exception:
                        pass

            if not vid_files:
                return {"success": False, "error": "File video tidak ditemukan setelah proses yt-dlp."}

            return {
                "success": True,
                "data": {
                    "username": author,
                    "caption": caption,
                    "like_count": 0,
                    "reply_count": 0,
                    "downloaded_files": vid_files
                }
            }
        except Exception as e:
            return {"success": False, "error": f"Exception saat menjalankan yt-dlp: {e}"}

    async def download_post(self, url: str) -> dict:
        """
        Download postingan YouTube (Community post gambar/teks, atau Video/Shorts).
        Returns:
            dict: { "success": bool, "data": {...}, "error": str }
        """
        post_id = self.extract_post_id(url)
        if post_id:
            logger.info(f"[YouTube] Mengunduh postingan komunitas {post_id}...")
            return await self._download_community_post(post_id)

        # Jika bukan link post komunitas langsung, cek apakah link video/shorts
        logger.info(f"[YouTube] Mengunduh video/shorts dari {url}...")
        return await self._download_video_ytdlp(url, prefix="yt_vid")
