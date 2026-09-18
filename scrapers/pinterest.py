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
logger = logging.getLogger("PinterestScraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
]

# Aset statis CSS yang tidak boleh terunduh sebagai media pin
KNOWN_CSS_ASSETS = {
    "d53b014d86a6b6761bf649a0ed813c2b",  # Instagram gradient background url
}


class PinterestScraperException(Exception):
    pass


class PostNotFoundException(PinterestScraperException):
    pass


class ParsingException(PinterestScraperException):
    pass


@dataclass
class MediaItem:
    type: str  # "IMAGE" atau "VIDEO"
    url: str
    width: int = 0
    height: int = 0


@dataclass
class PinterestPostData:
    post_id: str
    shortcode: str
    username: str
    user_pic: Optional[str]
    caption: str
    posted_at: int
    like_count: int
    reply_count: int
    media_type: str  # "SINGLE_IMAGE", "CAROUSEL", "SINGLE_VIDEO"
    media_items: List[MediaItem]
    downloaded_files: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def extract_image_hash(url: str) -> str:
    """Ekstrak hash atau nama file dasar dari URL gambar."""
    path = urlparse(url).path
    filename = os.path.basename(path)
    base, _ = os.path.splitext(filename)
    return base or url


def upgrade_pinimg_url(url: str) -> str:
    """
    Naikkan resolusi URL gambar i.pinimg.com ke originals jika memungkinkan,
    serta abaikan avatar atau aset CSS.
    """
    if not url or not isinstance(url, str):
        return ""
    clean_url = url.replace(r"\/", "/").replace("\\/", "/").strip()
    img_hash = extract_image_hash(clean_url)
    if img_hash in KNOWN_CSS_ASSETS:
        return ""
    if "/avatars/" in clean_url or clean_url.endswith(".svg"):
        return ""
    if "i.pinimg.com" in clean_url:
        return re.sub(r'/(?:[0-9]+x[0-9]*|[0-9]+x)/', '/originals/', clean_url)
    return clean_url


def extract_video_url_from_dict(vdata: Any) -> str:
    """Ekstrak URL video MP4 atau HLS terbaik dari dictionary metadata Pinterest."""
    if not isinstance(vdata, dict):
        return ""

    candidate_lists = []
    keys_to_check = [
        "videoList1080P", "videoList720P", "videoListEXP3", "videoListEXP4",
        "videoListEXP5", "videoListEXP6", "videoListEXP7", "videoList",
        "v_hlsv4_video_list", "videoListMobile"
    ]

    # Cek apakah vdata memiliki key bersarang seperti videoDataV2
    nested = vdata.get("videoDataV2") or vdata.get("video") or vdata.get("videos")
    search_dicts = [vdata]
    if isinstance(nested, dict):
        search_dicts.append(nested)

    for sd in search_dicts:
        for k in keys_to_check:
            if k in sd and isinstance(sd[k], dict):
                candidate_lists.append(sd[k])
        if "videoList" in sd and isinstance(sd["videoList"], dict) and sd["videoList"] not in candidate_lists:
            candidate_lists.append(sd["videoList"])

    # 1. Cari MP4 berkualitas tinggi dulu (1080p, 720p, 480p)
    for cl in candidate_lists:
        for q in ["v1080P", "vExp720P", "v720P", "v480P"]:
            if q in cl and isinstance(cl[q], dict) and cl[q].get("url"):
                u = str(cl[q]["url"])
                if ".mp4" in u:
                    return u.replace(r"\/", "/").replace("\\/", "/")

    # 2. Cari MP4 apa saja dalam candidates
    for cl in candidate_lists:
        for vobj in cl.values():
            if isinstance(vobj, dict) and vobj.get("url"):
                u = str(vobj["url"])
                if ".mp4" in u:
                    return u.replace(r"\/", "/").replace("\\/", "/")

    # 3. Cek videoUrls list jika ada
    for sd in search_dicts:
        if "videoUrls" in sd and isinstance(sd["videoUrls"], list):
            for u in sd["videoUrls"]:
                if isinstance(u, str) and ".mp4" in u:
                    return u.replace(r"\/", "/").replace("\\/", "/")

    # 4. Jika hanya ada m3u8 (HLS), simpan sebagai opsi cadangan
    for cl in candidate_lists:
        for q in ["vHLSV4", "vHLSV3MOBILE", "vHLS"]:
            if q in cl and isinstance(cl[q], dict) and cl[q].get("url"):
                return str(cl[q]["url"]).replace(r"\/", "/").replace("\\/", "/")
        for vobj in cl.values():
            if isinstance(vobj, dict) and vobj.get("url"):
                return str(vobj["url"]).replace(r"\/", "/").replace("\\/", "/")

    return ""


class PinterestScraper:
    """
    Scraper untuk Pinterest (pinterest.com & link pendek pin.it).
    Mengekstrak gambar resolusi asli (originals / 736x), multi-image/carousel, dan video pins secara cookieless.
    """

    def __init__(self, download_dir: str = "./downloads/pinterest", max_concurrent_downloads: int = 5):
        self.download_dir = download_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
        os.makedirs(self.download_dir, exist_ok=True)

    async def _resolve_url(self, url: str) -> str:
        """Resolve redirect untuk link pin.it atau link pendek."""
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    resolved = str(resp.url)
                    logger.info(f"[Pinterest] Resolved {url} -> {resolved}")
                    return resolved
        except Exception as e:
            logger.warning(f"[Pinterest] Gagal resolve redirect: {e}")
            return url

    def extract_pin_id(self, url: str) -> str:
        """Mengekstrak ID pin dari URL Pinterest."""
        m = re.search(r'/pin/(\d+)', url)
        if m:
            return m.group(1)
        parsed = urlparse(url)
        parts = [p for p in parsed.path.strip('/').split('/') if p]
        if parts:
            for p in reversed(parts):
                if p.isdigit():
                    return p
            return parts[-1]
        raise PinterestScraperException(f"Gagal mengekstrak Pin ID dari URL: {url}")

    async def _fetch_html(self, url: str) -> str:
        """Fetch HTML halaman Pinterest."""
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
                        raise PostNotFoundException("Pin Pinterest tidak ditemukan.")
                    if resp.status != 200:
                        raise PinterestScraperException(f"Gagal mengambil halaman. HTTP Status: {resp.status}")
                    return await resp.text()
        except (PostNotFoundException, PinterestScraperException):
            raise
        except Exception as e:
            raise PinterestScraperException(f"Network error: {str(e)}")

    def _extract_relay_data(self, html_content: str) -> Optional[Dict[str, Any]]:
        """Ekstrak query GraphQL Relay (v3GetPinQueryv2 / v3GetPinQuery) dari HTML."""
        matches = re.findall(r'window\.__PWS_RELAY_REGISTER_COMPLETED_REQUEST__\([^,]+,\s*(\{.*?\})\);', html_content)
        for m in matches:
            try:
                parsed = json.loads(m)
                data_wrap = parsed.get("data", {})
                pin_data = (
                    data_wrap.get("v3GetPinQueryv2", {}).get("data")
                    or data_wrap.get("v3GetPinQuery", {}).get("data")
                    or data_wrap.get("pin")
                )
                if pin_data and isinstance(pin_data, dict):
                    return pin_data
            except Exception:
                continue
        return None

    def _extract_post_from_html(self, html_content: str, pin_id: str, resolved_url: str) -> PinterestPostData:
        """Ekstrak gambar/video dan metadata dari HTML halaman Pinterest."""
        soup = BeautifulSoup(html_content, "html.parser")
        relay_data = self._extract_relay_data(html_content) or {}

        # 1. Ekstrak Username Pinner / Creator
        username = ""
        if relay_data:
            native_creator = relay_data.get("nativeCreator") or {}
            origin_pinner = relay_data.get("originPinner") or {}
            pinner = relay_data.get("pinner") or {}
            username = (
                native_creator.get("username")
                or origin_pinner.get("username")
                or pinner.get("username")
            )
        if not username:
            pinner_meta = soup.find("meta", property="pinterestapp:pinner")
            if pinner_meta and pinner_meta.get("content"):
                parts = [p for p in pinner_meta["content"].strip("/").split("/") if p]
                if parts:
                    username = parts[-1]
        if not username:
            pinboard_meta = soup.find("meta", property="pinterestapp:pinboard")
            if pinboard_meta and pinboard_meta.get("content"):
                parts = [p for p in pinboard_meta["content"].strip("/").split("/") if p]
                if len(parts) >= 2:
                    username = parts[-2]
        if not username:
            author_meta = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", property="article:author")
            if author_meta and author_meta.get("content"):
                username = author_meta["content"].strip()
        username = (username or "Pinterest").lstrip("@").strip()

        # 2. Judul dan Deskripsi
        og_title = soup.find("meta", property="og:title")
        og_desc = soup.find("meta", property="og:description")
        meta_desc = soup.find("meta", attrs={"name": "description"})

        title_val = (
            (relay_data.get("title") if relay_data else "")
            or (relay_data.get("gridTitle") if relay_data else "")
            or (og_title.get("content") if og_title else "")
            or (relay_data.get("seoTitle") if relay_data else "")
            or ""
        ).strip()
        title_val = re.sub(r'\s*\|\s*Pinterest$', '', title_val).strip()

        desc_val = (
            (relay_data.get("description") if relay_data else "")
            or (relay_data.get("unauthOnPageDescription") if relay_data else "")
            or (relay_data.get("gridDescription") if relay_data else "")
            or (og_desc.get("content") if og_desc else "")
            or (meta_desc.get("content") if meta_desc else "")
            or (relay_data.get("seoDescription") if relay_data else "")
            or ""
        ).strip()
        desc_val = re.sub(r'\s*\|\s*Pinterest$', '', desc_val).strip()

        if title_val and desc_val:
            if title_val.lower() == desc_val.lower():
                caption_val = title_val
            elif title_val.lower() in desc_val.lower():
                caption_val = desc_val
            elif desc_val.lower() in title_val.lower():
                caption_val = title_val
            else:
                caption_val = f"{title_val}\n\n{desc_val}"
        else:
            caption_val = title_val or desc_val
        caption_val = html_lib.unescape(caption_val).strip()

        # 3. Deteksi & Ekstraksi Media (StoryPinData > CarouselData > Video > Single Image)
        # A. Cek StoryPinData (Idea Pins / Stories baik single maupun multi-page)
        story = relay_data.get("storyPinData")
        if story and isinstance(story, dict):
            pages = story.get("pages") or []
            story_items: List[MediaItem] = []
            for p in pages:
                for b in p.get("blocks") or []:
                    # Cek jika block berisi video
                    b_vid_data = b.get("videoDataV2") or b.get("video") or b.get("videos")
                    if b_vid_data or b.get("__typename") == "StoryPinVideoBlock":
                        v_url = extract_video_url_from_dict(b_vid_data or b)
                        if v_url:
                            story_items.append(MediaItem(type="VIDEO", url=v_url, width=0, height=0))
                            break
                    # Cek jika block berisi gambar
                    found_img = False
                    for k in ["images_orig", "images_750x", "images_736x", "images_474x", "image"]:
                        val = b.get(k)
                        if isinstance(val, dict) and val.get("url"):
                            u = upgrade_pinimg_url(val["url"])
                            if u:
                                story_items.append(MediaItem(type="IMAGE", url=u, width=0, height=0))
                                found_img = True
                                break
                    if found_img:
                        break

            # Deduplikasi
            seen = set()
            deduped_story = []
            for item in story_items:
                h = extract_image_hash(item.url)
                if h and h not in seen:
                    seen.add(h)
                    deduped_story.append(item)

            if deduped_story:
                media_type = "CAROUSEL" if len(deduped_story) > 1 else f"SINGLE_{deduped_story[0].type}"
                return PinterestPostData(
                    post_id=pin_id,
                    shortcode=pin_id,
                    username=username,
                    user_pic=None,
                    caption=caption_val,
                    posted_at=int(time.time()),
                    like_count=0,
                    reply_count=0,
                    media_type=media_type,
                    media_items=deduped_story
                )

        # B. Cek CarouselData (Multi-slide carousel)
        carousel = relay_data.get("carouselData")
        if carousel:
            slots = []
            if isinstance(carousel, dict):
                slots = carousel.get("carousel_slots") or carousel.get("slots") or carousel.get("items") or []
            elif isinstance(carousel, list):
                slots = carousel

            carousel_items: List[MediaItem] = []
            for s in slots:
                if isinstance(s, dict):
                    v_url = extract_video_url_from_dict(s.get("videos") or s.get("video") or s)
                    if v_url:
                        carousel_items.append(MediaItem(type="VIDEO", url=v_url, width=0, height=0))
                        continue
                    imgs = s.get("images") or {}
                    orig = imgs.get("orig") or imgs.get("736x") or imgs.get("750x") or {}
                    if isinstance(orig, dict) and orig.get("url"):
                        u = upgrade_pinimg_url(orig["url"])
                        if u:
                            carousel_items.append(MediaItem(type="IMAGE", url=u, width=0, height=0))

            seen = set()
            deduped_carousel = []
            for item in carousel_items:
                h = extract_image_hash(item.url)
                if h and h not in seen:
                    seen.add(h)
                    deduped_carousel.append(item)

            if deduped_carousel:
                media_type = "CAROUSEL" if len(deduped_carousel) > 1 else f"SINGLE_{deduped_carousel[0].type}"
                return PinterestPostData(
                    post_id=pin_id,
                    shortcode=pin_id,
                    username=username,
                    user_pic=None,
                    caption=caption_val,
                    posted_at=int(time.time()),
                    like_count=0,
                    reply_count=0,
                    media_type=media_type,
                    media_items=deduped_carousel
                )

        # C. Cek Video Pins (Relay metadata & HTML regex)
        video_url = extract_video_url_from_dict(relay_data.get("videos"))

        # Cek HTML regex untuk video pins (v1.pinimg.com / v.pinimg.com)
        if not video_url:
            v_matches = re.findall(r'https://v1?\.pinimg\.com/videos/[^\s\"\'\<\>]+\.mp4', html_content)
            if v_matches:
                sorted_v = sorted(v_matches, key=lambda x: (1 if '720' in x else (2 if '1080' in x else 0)), reverse=True)
                video_url = sorted_v[0].replace(r"\/", "/").replace("\\/", "")

        # Cek penanda video di meta tag jika belum ketemu direct URL
        if not video_url:
            og_video = soup.find("meta", property="og:video") or soup.find("meta", property="og:video:secure_url")
            if og_video and og_video.get("content"):
                video_url = og_video["content"]
            elif "[video]" in title_val.lower() or "[видео]" in title_val.lower():
                video_url = resolved_url

        if video_url:
            return PinterestPostData(
                post_id=pin_id,
                shortcode=pin_id,
                username=username,
                user_pic=None,
                caption=caption_val,
                posted_at=int(time.time()),
                like_count=0,
                reply_count=0,
                media_type="SINGLE_VIDEO",
                media_items=[MediaItem(type="VIDEO", url=video_url, width=0, height=0)]
            )

        # D. Single Image (Relay / Preload / og:image / HTML)
        media_items: List[MediaItem] = []

        # 1. Dari Relay Data
        imgs = (
            relay_data.get("images_orig")
            or relay_data.get("images_736x")
            or relay_data.get("imageLargeUrl")
        )
        if isinstance(imgs, dict) and imgs.get("url"):
            u = upgrade_pinimg_url(imgs["url"])
            if u:
                media_items.append(MediaItem(type="IMAGE", url=u, width=0, height=0))
        elif isinstance(imgs, str):
            u = upgrade_pinimg_url(imgs)
            if u:
                media_items.append(MediaItem(type="IMAGE", url=u, width=0, height=0))

        # 2. Dari HTML preload link <link id="pin-image-preload" href="...">
        if not media_items:
            preload = soup.find("link", id="pin-image-preload")
            if preload and preload.get("href"):
                u = upgrade_pinimg_url(preload["href"])
                if u:
                    media_items.append(MediaItem(type="IMAGE", url=u, width=0, height=0))

        # 3. Dari meta tag og:image
        if not media_items:
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                u = upgrade_pinimg_url(og_img["content"])
                if u:
                    media_items.append(MediaItem(type="IMAGE", url=u, width=0, height=0))

        # 4. Fallback: Parse <img> tags setelah membuang <style> dan <script>
        if not media_items:
            soup_clean = BeautifulSoup(html_content, "html.parser")
            for tag in soup_clean(["style", "script", "noscript"]):
                tag.decompose()
            seen = set()
            for img in soup_clean.find_all("img"):
                src = img.get("src")
                if src and "i.pinimg.com" in src:
                    u = upgrade_pinimg_url(src)
                    h = extract_image_hash(u)
                    if u and h and h not in seen:
                        seen.add(h)
                        media_items.append(MediaItem(type="IMAGE", url=u, width=0, height=0))

        if not media_items:
            raise ParsingException("Tidak dapat menemukan media gambar atau video pada Pin ini.")

        return PinterestPostData(
            post_id=pin_id,
            shortcode=pin_id,
            username=username,
            user_pic=None,
            caption=caption_val,
            posted_at=int(time.time()),
            like_count=0,
            reply_count=0,
            media_type="CAROUSEL" if len(media_items) > 1 else f"SINGLE_{media_items[0].type}",
            media_items=media_items
        )

    async def _extract_post_from_ytdlp(self, url: str, pin_id: str) -> Optional[PinterestPostData]:
        """Fallback mengekstrak info Pin video menggunakan yt-dlp jika parsing HTML gagal."""
        cmd = ["yt-dlp", "--dump-json", "--no-warnings", "--no-playlist", url]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0 and stdout:
                data = json.loads(stdout.decode("utf-8"))
                uploader = (data.get("uploader") or "Pinterest").lstrip("@")
                title = data.get("title") or ""
                desc = data.get("description") or ""
                if title and desc:
                    caption = title if title.lower() in desc.lower() else f"{title}\n\n{desc}"
                else:
                    caption = title or desc
                video_url = data.get("url") or url
                return PinterestPostData(
                    post_id=pin_id,
                    shortcode=pin_id,
                    username=uploader,
                    user_pic=None,
                    caption=caption.strip(),
                    posted_at=int(time.time()),
                    like_count=data.get("like_count") or 0,
                    reply_count=data.get("comment_count") or 0,
                    media_type="SINGLE_VIDEO",
                    media_items=[MediaItem(type="VIDEO", url=video_url, width=data.get("width") or 0, height=data.get("height") or 0)]
                )
        except Exception as e:
            logger.warning(f"[Pinterest] yt-dlp dump-json fallback error: {e}")
        return None

    async def _download_single_file(self, url: str, dest_path: str) -> bool:
        """Unduh file media gambar tunggal via aria2c dengan fallback otomatis ke 736x."""
        async with self.semaphore:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            success = await aria2_download(url, dest_path, headers=headers)
            if not success or not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
                if "/originals/" in url:
                    fallback_url = url.replace("/originals/", "/736x/")
                    logger.info(f"[Pinterest] Originals gagal, mencoba fallback 736x: {fallback_url}")
                    if os.path.exists(dest_path):
                        try:
                            os.remove(dest_path)
                        except Exception:
                            pass
                    success = await aria2_download(fallback_url, dest_path, headers=headers)
            return success and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0

    async def _download_video_ytdlp(self, url: str, dest_path: str) -> bool:
        """Download video Pinterest menggunakan yt-dlp sebagai fallback."""
        cmd = [
            "yt-dlp",
            "-f", "b[ext=mp4]/best",
            "-o", dest_path,
            "--no-warnings",
            "--no-playlist",
            url
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            # Pastikan nama file cocok
            if not os.path.exists(dest_path):
                base_no_ext = os.path.splitext(dest_path)[0]
                for possible in [f"{base_no_ext}.mp4", f"{base_no_ext}.mkv", f"{base_no_ext}.webm"]:
                    if os.path.exists(possible) and os.path.getsize(possible) > 0:
                        os.rename(possible, dest_path)
                        break

            if proc.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                logger.info(f"[Pinterest] yt-dlp berhasil download video ke {dest_path}")
                return True
            else:
                logger.warning(f"[Pinterest] yt-dlp error: {stderr.decode(errors='ignore')[:200]}")
                return False
        except Exception as e:
            logger.error(f"[Pinterest] Exception saat yt-dlp download: {e}")
            return False

    async def _download_video(self, item_url: str, post_url: str, dest_path: str) -> bool:
        """Unduh video Pinterest via aria2c jika direct MP4 atau fallback ke yt-dlp."""
        async with self.semaphore:
            if item_url and item_url.startswith("http") and ".mp4" in item_url:
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                ok = await aria2_download(item_url, dest_path, headers=headers)
                if ok and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                    return True
                logger.warning(f"[Pinterest] Direct video download gagal, fallback ke yt-dlp...")

            # Fallback ke yt-dlp dengan URL postingan
            target_url = post_url if post_url and ("pin/" in post_url or "pin.it" in post_url) else item_url
            return await self._download_video_ytdlp(target_url, dest_path)

    async def get_post_info(self, url: str) -> PinterestPostData:
        """Mengambil data Pin dari URL Pinterest."""
        resolved_url = await self._resolve_url(url)
        pin_id = self.extract_pin_id(resolved_url)
        canonical_url = f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else resolved_url

        try:
            html_content = await self._fetch_html(canonical_url)
            return self._extract_post_from_html(html_content, pin_id, canonical_url)
        except Exception as html_err:
            logger.warning(f"[Pinterest] HTML extraction error ({html_err}), mencoba yt-dlp fallback...")
            ytdlp_data = await self._extract_post_from_ytdlp(canonical_url, pin_id)
            if ytdlp_data:
                return ytdlp_data
            raise html_err

    async def download_post(self, url: str) -> Dict[str, Any]:
        """
        Download postingan/Pin Pinterest.
        Returns:
            {"success": True, "data": PinterestPostData.to_dict()} atau
            {"success": False, "error": str, "error_type": str}
        """
        try:
            resolved_url = await self._resolve_url(url)
            pin_id = self.extract_pin_id(resolved_url)
            canonical_url = f"https://www.pinterest.com/pin/{pin_id}/" if pin_id else resolved_url

            post_data = await self.get_post_info(canonical_url)

            downloaded_paths = []
            tasks = []
            for index, item in enumerate(post_data.media_items):
                ext = "mp4" if item.type == "VIDEO" else "jpg"
                u_lower = item.url.lower().split("?")[0]
                if u_lower.endswith(".png"):
                    ext = "png"
                elif u_lower.endswith(".gif"):
                    ext = "gif"

                filename = f"pinterest_{post_data.shortcode}_{index}.{ext}"
                full_path = os.path.join(self.download_dir, filename)
                downloaded_paths.append(full_path)

                if item.type == "VIDEO":
                    tasks.append(self._download_video(item.url, canonical_url, full_path))
                else:
                    tasks.append(self._download_single_file(item.url, full_path))

            results = await asyncio.gather(*tasks)
            final_downloaded_files = [path for path, success in zip(downloaded_paths, results) if success]

            # Jika unduhan kosong dan tipe media adalah video, coba yt-dlp sekali lagi
            if not final_downloaded_files and post_data.media_type in ["SINGLE_VIDEO", "VIDEO"]:
                fallback_path = os.path.join(self.download_dir, f"pinterest_{post_data.shortcode}_0.mp4")
                if await self._download_video_ytdlp(canonical_url, fallback_path):
                    final_downloaded_files.append(fallback_path)

            post_data.downloaded_files = final_downloaded_files
            return {"success": True, "data": post_data.to_dict()}

        except PinterestScraperException as pse:
            return {"success": False, "error": str(pse), "error_type": pse.__class__.__name__}
        except Exception as e:
            logger.error(f"[Pinterest] download_post error: {e}", exc_info=True)
            return {"success": False, "error": f"Internal error: {str(e)}", "error_type": "UnhandledException"}
