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
from bs4 import BeautifulSoup
from .aria2_dl import aria2_download

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("SpotifyScraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
]


class SpotifyScraperException(Exception):
    pass


class TrackNotFoundException(SpotifyScraperException):
    pass


class ParsingException(SpotifyScraperException):
    pass


@dataclass
class MediaItem:
    type: str  # "AUDIO"
    url: str
    width: int = 0
    height: int = 0


@dataclass
class SpotifyPostData:
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
    title: str = ""
    artist: str = ""
    cover_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SpotifyScraper:
    """
    Scraper untuk platform Spotify (open.spotify.com, spotify.link).
    Mengambil metadata resmi dari Spotify (judul, artis, album, cover HD, durasi),
    lalu mengunduh audio berkualitas tinggi dan menyematkan metadata serta album art via FFmpeg.
    """

    def __init__(
        self,
        download_dir: str = "./downloads/spotify",
        cookie_file: Optional[str] = None
    ):
        self.download_dir = download_dir
        self.cookie_file = cookie_file
        os.makedirs(self.download_dir, exist_ok=True)

    def extract_track_id(self, url: str) -> str:
        """Mengekstrak Spotify Track ID dari URL."""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        parts = path.split('/')
        if 'track' in parts:
            idx = parts.index('track')
            if idx + 1 < len(parts):
                return parts[idx + 1].split('?')[0].split('&')[0]
        if parts:
            return parts[-1].split('?')[0].split('&')[0]
        raise SpotifyScraperException(f"Gagal mengekstrak ID lagu dari URL: {url}")

    async def _resolve_redirects(self, url: str) -> str:
        """Mengikuti redirect URL pendek (spotify.link / spoti.fi)."""
        if any(d in url for d in ["spotify.link", "spoti.fi"]):
            try:
                headers = {"User-Agent": USER_AGENTS[0]}
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        return str(resp.url)
            except Exception as e:
                logger.warning(f"Gagal resolve redirect Spotify: {e}")
        return url

    async def get_post_info(self, url: str) -> SpotifyPostData:
        """
        Mengekstrak metadata lagu dari Spotify embed HTML / oEmbed.
        """
        resolved_url = await self._resolve_redirects(url)
        track_id = self.extract_track_id(resolved_url)

        embed_url = f"https://open.spotify.com/embed/track/{track_id}"
        headers = {
            "User-Agent": USER_AGENTS[0],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }

        title = ""
        artists_str = ""
        duration_sec = 0.0
        cover_url = ""
        preview_url = ""
        release_date = ""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(embed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        soup = BeautifulSoup(html, "html.parser")
                        next_script = soup.find("script", id="__NEXT_DATA__")
                        if next_script and next_script.string:
                            try:
                                next_data = json.loads(next_script.string)
                                entity = next_data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
                                if entity:
                                    title = entity.get("name") or entity.get("title") or ""
                                    artists = entity.get("artists", [])
                                    if isinstance(artists, list) and artists:
                                        artists_str = ", ".join(a.get("name", "") for a in artists if a.get("name"))
                                    elif isinstance(artists, str):
                                        artists_str = artists
                                    
                                    dur_ms = entity.get("duration", 0)
                                    if dur_ms:
                                        duration_sec = round(float(dur_ms) / 1000.0, 1)

                                    images = entity.get("visualIdentity", {}).get("image", [])
                                    if images and isinstance(images, list):
                                        cover_url = images[-1].get("url") or images[0].get("url") or ""

                                    audio_preview = entity.get("audioPreview", {})
                                    if isinstance(audio_preview, dict):
                                        preview_url = audio_preview.get("url") or ""

                                    rel_date = entity.get("releaseDate", {})
                                    if isinstance(rel_date, dict):
                                        release_date = rel_date.get("isoString", "")[:10]
                            except Exception as json_err:
                                logger.warning(f"Error parsing __NEXT_DATA__ Spotify: {json_err}")
        except Exception as e:
            logger.warning(f"Error fetching Spotify embed: {e}")

        # Fallback ke oEmbed jika judul masih kosong
        if not title:
            try:
                oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(oembed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            oembed_data = await resp.json()
                            title = oembed_data.get("title", "")
                            cover_url = cover_url or oembed_data.get("thumbnail_url", "")
            except Exception as oe_err:
                logger.warning(f"Error fetching Spotify oEmbed: {oe_err}")

        if not title:
            raise TrackNotFoundException(f"Tidak dapat menemukan informasi lagu untuk Spotify Track ID {track_id}")

        if not artists_str:
            artists_str = "Spotify Artist"

        caption_clean = f"🎵 {title}\n👤 {artists_str}"
        if release_date:
            caption_clean += f"\n📅 {release_date}"

        media_items = []
        if preview_url:
            media_items.append(MediaItem(type="AUDIO", url=preview_url))
        elif cover_url:
            media_items.append(MediaItem(type="IMAGE", url=cover_url))

        return SpotifyPostData(
            post_id=track_id,
            shortcode=track_id,
            username=artists_str,
            user_pic=cover_url,
            caption=caption_clean,
            posted_at=int(time.time()),
            like_count=0,
            reply_count=0,
            media_type="AUDIO",
            media_items=media_items,
            duration=duration_sec,
            title=title,
            artist=artists_str,
            cover_url=cover_url
        )

    async def _download_audio_stream(
        self,
        query: str,
        dest_path: str,
        cover_path: Optional[str] = None,
        title: str = "",
        artist: str = ""
    ) -> bool:
        """
        Mencari dan mengunduh audio:
        1. Coba pencarian YouTube via yt-dlp dengan cookies/ejs.
        2. Fallback ke SoundCloud search (cookieless).
        Lalu encode ke MP3 192k dengan menyematkan ID3 metadata dan album art.
        """
        temp_audio = f"{dest_path}.raw.webm"
        if os.path.exists(temp_audio):
            try: os.remove(temp_audio)
            except: pass

        download_success = False

        # --- Tier 1: YouTube Search via yt-dlp ---
        yt_args = [
            "yt-dlp",
            f"ytsearch1:{query}",
            "--no-playlist",
            "-f", "bestaudio[ext=m4a]/bestaudio/best",
            "-o", temp_audio,
            "--remote-components", "ejs:github",
            "--no-warnings"
        ]
        if self.cookie_file and os.path.exists(self.cookie_file):
            yt_args.extend(["--cookies", self.cookie_file])

        try:
            proc = await asyncio.create_subprocess_exec(
                *yt_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0 and os.path.exists(temp_audio) and os.path.getsize(temp_audio) > 10000:
                download_success = True
        except Exception as e:
            logger.warning(f"Spotify YouTube search download failed: {e}")

        # --- Tier 2: Fallback SoundCloud Search via yt-dlp ---
        if not download_success:
            logger.info(f"[Spotify] Falling back to SoundCloud search for: {query}")
            sc_args = [
                "yt-dlp",
                f"scsearch1:{query}",
                "--no-playlist",
                "-f", "bestaudio[format_id!*=preview]/bestaudio/best",
                "-o", temp_audio,
                "--no-warnings"
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *sc_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()
                if proc.returncode == 0 and os.path.exists(temp_audio) and os.path.getsize(temp_audio) > 10000:
                    download_success = True
            except Exception as e:
                logger.warning(f"Spotify SoundCloud search download failed: {e}")

        if not download_success or not os.path.exists(temp_audio):
            return False

        # --- Tier 3: Encode to MP3 with Metadata and Cover Art ---
        cmd = ["ffmpeg", "-y", "-i", temp_audio]
        if cover_path and os.path.exists(cover_path) and os.path.getsize(cover_path) > 0:
            cmd.extend(["-i", cover_path, "-map", "0:a", "-map", "1:0", "-c:v", "mjpeg"])
            cmd.extend(["-id3v2_version", "3", "-metadata:s:v", 'title="Album cover"', "-metadata:s:v", 'comment="Cover (front)"'])
        else:
            cmd.extend(["-map", "0:a"])

        cmd.extend([
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-metadata", f"title={title}",
            "-metadata", f"artist={artist}",
            dest_path
        ])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()
            if os.path.exists(temp_audio):
                try: os.remove(temp_audio)
                except: pass
            return proc.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 10000
        except Exception as e:
            logger.error(f"[Spotify] FFmpeg error: {e}")
            if os.path.exists(temp_audio):
                try: os.remove(temp_audio)
                except: pass
            return False

    async def download_post(self, url: str) -> Dict[str, Any]:
        """
        Download lagu dari Spotify dan simpan sebagai MP3 berkualitas tinggi.
        """
        try:
            post_data = await self.get_post_info(url)
            filename = f"spotify_{post_data.shortcode}.mp3"
            full_path = os.path.join(self.download_dir, filename)

            cover_path = None
            if post_data.cover_url:
                cover_path = os.path.join(self.download_dir, f"spotify_{post_data.shortcode}_cover.jpg")
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(post_data.cover_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status == 200:
                                content = await resp.read()
                                with open(cover_path, "wb") as f:
                                    f.write(content)
                except Exception as e:
                    logger.warning(f"Gagal download cover Spotify: {e}")
                    cover_path = None

            search_query = f"{post_data.artist} - {post_data.title}"
            success = await self._download_audio_stream(
                query=search_query,
                dest_path=full_path,
                cover_path=cover_path,
                title=post_data.title,
                artist=post_data.artist
            )

            if success:
                post_data.downloaded_files = [full_path]
                if cover_path and os.path.exists(cover_path):
                    post_data.user_pic = cover_path
                return {"success": True, "data": post_data.to_dict()}
            else:
                if cover_path and os.path.exists(cover_path):
                    try: os.remove(cover_path)
                    except: pass
                return {
                    "success": False,
                    "error": f"Gagal mengunduh lagu '{post_data.title}' oleh '{post_data.artist}'.",
                    "error_type": "DownloadError"
                }

        except SpotifyScraperException as se:
            return {"success": False, "error": str(se), "error_type": se.__class__.__name__}
        except Exception as e:
            return {"success": False, "error": f"Internal error: {str(e)}", "error_type": "UnhandledException"}

    def _score_track_match(self, query: str, title: str, artist: str) -> float:
        """Menghitung relevansi judul dan artis terhadap query pencarian pengguna."""
        q = query.lower().strip()
        t = title.lower().strip()
        a = artist.lower().strip()
        words = [w for w in re.findall(r'\w+', q) if len(w) > 1]

        score = 0.0
        # Exact match on title (misal query "akad" -> title "Akad")
        if t == q:
            score += 3000.0
        elif t.startswith(q + ' ') or t.endswith(' ' + q) or f' {q} ' in f' {t} ':
            score += 1500.0
        elif q in t:
            score += 800.0

        # Exact match / partial match pada artist
        if a == q:
            score += 1200.0
        elif q in a:
            score += 500.0

        # Match gabungan artist + title (misal "payung teduh akad")
        combined = f"{a} {t}"
        if words and all(w in combined for w in words):
            score += 1000.0

        # Match per-kata
        for w in words:
            if w in t:
                score += 250.0
            if w in a:
                score += 150.0

        # Penalti jika sama sekali tidak mengandung kata dari query
        if words and not any(w in t or w in a for w in words):
            score = -1000.0

        return score

    async def search_and_download(self, query: str) -> Dict[str, Any]:
        """
        Mencari lagu berdasarkan query judul/kata kunci dan mengunduhnya sebagai MP3.
        Menggunakan Deezer API dengan relevansi scoring, fallback iTunes API & YouTube search.
        """
        try:
            clean_q = urllib.parse.quote(query.strip())
            title = ""
            artist = ""
            cover_url = ""
            duration = 0.0

            # 1. Cari via Deezer API dengan ranking relevansi
            try:
                meta_url = f"https://api.deezer.com/search?q={clean_q}&limit=25"
                async with aiohttp.ClientSession() as session:
                    async with session.get(meta_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            d = await resp.json()
                            candidates = []
                            for item in d.get("data", []):
                                t = item.get("title") or item.get("title_short") or ""
                                art = item.get("artist", {}).get("name") or ""
                                s = self._score_track_match(query, t, art)
                                if s > 0:
                                    candidates.append((s, item.get("rank", 0), t, art, item))
                            if candidates:
                                candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
                                top = candidates[0]
                                title = top[2]
                                artist = top[3]
                                top_item = top[4]
                                cover_url = top_item.get("album", {}).get("cover_xl") or top_item.get("album", {}).get("cover_big") or ""
                                duration = float(top_item.get("duration", 0))
            except Exception as e:
                logger.warning(f"[Spotify] Deezer search error: {e}")

            # 2. Fallback ke iTunes Search API jika Deezer tidak menemukan hasil relevan
            if not title:
                try:
                    itunes_url = f"https://itunes.apple.com/search?term={clean_q}&entity=song&limit=15"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(itunes_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status == 200:
                                idat = await resp.json()
                                i_candidates = []
                                for item in idat.get("results", []):
                                    t = item.get("trackName") or ""
                                    art = item.get("artistName") or ""
                                    s = self._score_track_match(query, t, art)
                                    if s > 0:
                                        i_candidates.append((s, t, art, item))
                                if i_candidates:
                                    i_candidates.sort(key=lambda x: x[0], reverse=True)
                                    top = i_candidates[0]
                                    title = top[1]
                                    artist = top[2]
                                    raw_cover = top[3].get("artworkUrl100") or ""
                                    cover_url = raw_cover.replace("100x100bb.jpg", "1000x1000bb.jpg")
                                    dur_ms = top[3].get("trackTimeMillis", 0)
                                    duration = round(dur_ms / 1000.0, 1)
                except Exception as e:
                    logger.warning(f"[Spotify] iTunes search fallback error: {e}")

            # 3. Fallback ke YouTube search metadata jika kedua API di atas tidak ada
            if not title:
                try:
                    yt_meta_args = [
                        "yt-dlp", f"ytsearch1:{query}", "--dump-json", "--no-playlist",
                        "--remote-components", "ejs:github"
                    ]
                    if self.cookie_file and os.path.exists(self.cookie_file):
                        yt_meta_args.extend(["--cookies", self.cookie_file])
                    proc = await asyncio.create_subprocess_exec(*yt_meta_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
                    if stdout:
                        info = json.loads(stdout.decode('utf-8', errors='ignore').strip())
                        full_t = info.get("title", "")
                        duration = float(info.get("duration", 0))
                        cover_url = info.get("thumbnail", "")
                        if " - " in full_t:
                            parts = full_t.split(" - ", 1)
                            artist = parts[0].strip()
                            title = re.sub(r'\(.*?\)|\[.*?\]', '', parts[1]).strip()
                        else:
                            title = re.sub(r'\(.*?\)|\[.*?\]', '', full_t).strip()
                            artist = info.get("uploader") or info.get("channel") or "Artist"
                except Exception as e:
                    logger.warning(f"[Spotify] YouTube meta fallback error: {e}")

            if not title:
                title = query.strip().title()
                artist = "Spotify Artist"

            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', f"{artist}_{title}")[:40]
            filename = f"spotify_search_{safe_name}_{int(time.time())}.mp3"
            full_path = os.path.join(self.download_dir, filename)

            cover_path = None
            if cover_url:
                cover_path = os.path.join(self.download_dir, f"cover_{safe_name}.jpg")
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(cover_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status == 200:
                                with open(cover_path, "wb") as f:
                                    f.write(await resp.read())
                except Exception:
                    cover_path = None

            search_query = f"{artist} - {title}" if artist != "Spotify Artist" else query
            success = await self._download_audio_stream(
                query=search_query,
                dest_path=full_path,
                cover_path=cover_path,
                title=title,
                artist=artist
            )

            if success and os.path.exists(full_path) and os.path.getsize(full_path) > 10000:
                return {
                    "success": True,
                    "data": {
                        "title": title,
                        "artist": artist,
                        "duration": duration,
                        "thumb": cover_path if (cover_path and os.path.exists(cover_path)) else None,
                        "downloaded_files": [full_path]
                    }
                }
            else:
                if cover_path and os.path.exists(cover_path):
                    try: os.remove(cover_path)
                    except: pass
                return {
                    "success": False,
                    "error": f"Lagu '{query}' tidak ditemukan atau gagal diunduh via Spotify."
                }
        except Exception as e:
            return {"success": False, "error": f"Error Spotify search: {str(e)}"}

