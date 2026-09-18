import os
import re
import asyncio
import logging
import urllib.parse
import aiohttp
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from .aria2_dl import aria2_download

logger = logging.getLogger(__name__)

class RedditScraper:
    """
    Scraper Reddit handal anti-403 yang dirancang khusus untuk datacenter / cloud VPS.
    Menggunakan:
    1. Post RSS feed dengan bot User-Agent (tidak diblokir Reddit, 100% lolos anti-bot)
    2. Direct CDN HLS video stream via ffmpeg (audio + video muxed otomatis dalam hitungan detik)
    3. Direct i.redd.it image & gallery extraction
    4. Fallback ke RapidSave API untuk metadata/video alternatif
    """
    def __init__(self, download_dir: str):
        self.download_dir = download_dir
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir, exist_ok=True)

    @staticmethod
    async def search_video_posts(tag: str, limit: int = 30) -> List[Dict[str, str]]:
        """
        Mencari postingan video Reddit (v.redd.it) yang sesuai dengan tag/keyword.
        Mendukung custom keyword maupun direct subreddit (misal 'r/MemeVideos').
        """
        headers = {
            'User-Agent': 'Twitterbot/1.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        tag_clean = tag.strip().lower()
        posts = []
        seen_urls = set()

        if tag_clean.startswith('r/'):
            sub = tag_clean[2:]
            urls = [f'https://www.reddit.com/r/{sub}/hot.rss?limit={limit}']
        else:
            q_hot = urllib.parse.quote(f'{tag_clean} url:v.redd.it')
            urls = [
                f'https://www.reddit.com/search.rss?q={q_hot}&sort=hot',
                f'https://www.reddit.com/search.rss?q={q_hot}&sort=relevance'
            ]

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            for u in urls:
                try:
                    async with session.get(u) as resp:
                        if resp.status == 200:
                            xml_data = await resp.read()
                            root = ET.fromstring(xml_data)
                            ns = {'atom': 'http://www.w3.org/2005/Atom'}
                            for entry in root.findall('atom:entry', ns):
                                link_el = entry.find('atom:link', ns)
                                title_el = entry.find('atom:title', ns)
                                if link_el is not None:
                                    href = link_el.attrib.get('href', '')
                                    if 'comments/' in href and href not in seen_urls:
                                        seen_urls.add(href)
                                        title_text = title_el.text if title_el is not None and title_el.text else 'Reddit Video'
                                        posts.append({
                                            'title': title_text,
                                            'url': href
                                        })
                except Exception as e:
                    logger.warning(f"[Reddit Search] Error fetching {u}: {e}")
                if len(posts) >= limit:
                    break

        return posts

    async def _resolve_url(self, url: str) -> str:
        """Resolve shortlink redd.it atau reddit.com/r/.../s/... ke URL canonical."""
        # Gunakan bot UA (Twitterbot) karena Reddit memblokir IP Datacenter/VPS (403) jika menggunakan browser UA
        headers = {
            "User-Agent": "Twitterbot/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        current_url = url
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                for _ in range(5):
                    if "comments/" in current_url:
                        break
                    async with session.get(current_url, allow_redirects=False) as resp:
                        if resp.status in (301, 302, 303, 307, 308) and "Location" in resp.headers:
                            loc = resp.headers["Location"]
                            if loc.startswith("/"):
                                loc = f"https://www.reddit.com{loc}"
                            current_url = loc
                        else:
                            break
                return current_url
        except Exception as e:
            logger.warning(f"[Reddit] Failed resolving URL {url}: {e}")
            return current_url

    async def download_post(self, url: str) -> dict:
        """
        Download postingan Reddit (gambar, gallery, atau video ber-audio).
        Returns:
            dict: { "success": bool, "data": {...}, "error": str }
        """
        canonical_url = await self._resolve_url(url)
        clean_url = canonical_url.split('?')[0].rstrip('/')

        # Ekstrak post ID dari URL
        post_id_match = re.search(r'comments/([a-z0-9]+)', clean_url, re.IGNORECASE)
        post_id = post_id_match.group(1) if post_id_match else "reddit_post"

        title = "Reddit Post"
        author = "reddit_user"
        content_html = ""
        upvotes = 0
        num_comments = 0

        # 1. Coba ambil metadata & content lewat RSS feed
        rss_url = f"{clean_url}/.rss" if "comments/" in clean_url else f"https://www.reddit.com/comments/{post_id}/.rss"
        rss_headers = {
            "User-Agent": "Twitterbot/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        rss_success = False
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(headers=rss_headers, timeout=timeout) as session:
                async with session.get(rss_url) as resp:
                    if resp.status == 200:
                        xml_bytes = await resp.read()
                        root = ET.fromstring(xml_bytes)
                        ns = {'atom': 'http://www.w3.org/2005/Atom'}
                        entry = root.find('atom:entry', ns)
                        entries = root.findall('atom:entry', ns)
                        if entries:
                            num_comments = max(0, len(entries) - 1)
                        if entry is not None:
                            title_elem = entry.find('atom:title', ns)
                            if title_elem is not None and title_elem.text:
                                title = title_elem.text
                            author_elem = entry.find('atom:author/atom:name', ns)
                            if author_elem is not None and author_elem.text:
                                author = author_elem.text.replace("/u/", "").replace("u/", "")
                            content_elem = entry.find('atom:content', ns)
                            if content_elem is not None and content_elem.text:
                                content_html = content_elem.text
                            rss_success = True
        except Exception as e:
            logger.warning(f"[Reddit] RSS fetch failed for {rss_url}: {e}")

        # Media links
        media_files_downloaded = []

        # Cek apakah ada video (v.redd.it)
        video_id_match = re.search(r'v\.redd\.it/([a-zA-Z0-9]+)', content_html or canonical_url)
        
        # 2. Jika ada video v.redd.it
        if video_id_match:
            vid_id = video_id_match.group(1)
            hls_url = f"https://v.redd.it/{vid_id}/HLSPlaylist.m3u8"
            video_output = f"{self.download_dir}/{post_id}_vid.mp4"

            logger.info(f"[Reddit] Downloading video from {hls_url} using ffmpeg...")
            cmd = [
                "ffmpeg", "-y",
                "-headers", "User-Agent: Mozilla/5.0\r\n",
                "-i", hls_url,
                "-c", "copy",
                video_output
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode == 0 and os.path.exists(video_output) and os.path.getsize(video_output) > 10000:
                    media_files_downloaded.append(video_output)
                else:
                    logger.warning(f"[Reddit] Direct HLS ffmpeg failed (code {proc.returncode}). Stderr: {stderr.decode()[:300]}")
            except Exception as ffmpeg_err:
                logger.error(f"[Reddit] ffmpeg subprocess error: {ffmpeg_err}")

        # 3. Jika video belum berhasil, coba RapidSave API sebagai fallback
        if not media_files_downloaded and video_id_match:
            logger.info(f"[Reddit] Trying RapidSave fallback for {clean_url}...")
            try:
                rapidsave_url = f"https://rapidsave.com/info?url={clean_url}"
                rs_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                async with aiohttp.ClientSession(headers=rs_headers, timeout=aiohttp.ClientTimeout(total=10)) as rs_session:
                    async with rs_session.get(rapidsave_url) as rs_resp:
                        if rs_resp.status == 200:
                            rs_html = await rs_resp.text()
                            # Ambil download URL dari RapidSave
                            v_match = re.search(r'video_url=(https?://[^\s&"\']+)', rs_html)
                            a_match = re.search(r'audio_url=(https?://[^\s&"\']+)', rs_html)
                            if v_match:
                                v_url = v_match.group(1)
                                a_url = a_match.group(1) if a_match else None
                                v_temp = f"{self.download_dir}/{post_id}_temp_v.mp4"
                                a_temp = f"{self.download_dir}/{post_id}_temp_a.mp4"
                                out_final = f"{self.download_dir}/{post_id}_vid.mp4"

                                v_ok = await aria2_download(v_url, v_temp)
                                if v_ok and os.path.exists(v_temp):
                                    if a_url:
                                        a_ok = await aria2_download(a_url, a_temp)
                                        if a_ok and os.path.exists(a_temp):
                                            # Mux video dan audio
                                            mux_proc = await asyncio.create_subprocess_exec(
                                                "ffmpeg", "-y", "-i", v_temp, "-i", a_temp, "-c", "copy", out_final,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                                            )
                                            await mux_proc.communicate()
                                            if os.path.exists(out_final) and os.path.getsize(out_final) > 0:
                                                media_files_downloaded.append(out_final)
                                                if os.path.exists(v_temp): os.remove(v_temp)
                                                if os.path.exists(a_temp): os.remove(a_temp)
                                    if not media_files_downloaded and os.path.exists(v_temp):
                                        os.rename(v_temp, out_final)
                                        media_files_downloaded.append(out_final)
            except Exception as rs_err:
                logger.error(f"[Reddit] RapidSave fallback error: {rs_err}")

        # 4. Jika bukan video atau tidak ada video, cari gambar (i.redd.it / preview.redd.it)
        if not media_files_downloaded:
            # Temukan semua gambar di content HTML
            raw_img_urls = re.findall(r'https?://(?:i|preview)\.redd\.it/[^\s"\'<>]+', content_html)
            
            # Normalisasi ke i.redd.it asli (tanpa query params thumbnail)
            unique_images = []
            seen_filenames = set()

            for img_url in raw_img_urls:
                # Bersihkan HTML entities
                clean_img = img_url.replace('&amp;', '&')
                # Ambil filename/ID gambar
                fn_match = re.search(r'redd\.it/([a-zA-Z0-9_-]+\.(?:jpe?g|png|gif|webp))', clean_img, re.IGNORECASE)
                if fn_match:
                    filename = fn_match.group(1)
                    if filename not in seen_filenames:
                        seen_filenames.add(filename)
                        unique_images.append(f"https://i.redd.it/{filename}")
                else:
                    # Gambar tanpa ekstensi langsung
                    clean_direct = clean_img.split('?')[0]
                    if clean_direct not in seen_filenames and clean_direct != "https://i.redd.it":
                        seen_filenames.add(clean_direct)
                        unique_images.append(clean_direct)

            # Jika masih kosong, coba regex pada canonical_url
            if not unique_images:
                if re.search(r'\.(jpe?g|png|gif|webp)(\?|$)', canonical_url, re.IGNORECASE):
                    unique_images.append(canonical_url)

            # Unduh setiap gambar yang ditemukan
            dl_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "*/*",
                "Sec-Fetch-Mode": "no-cors"
            }
            for idx, img_url in enumerate(unique_images):
                ext = "jpg"
                ext_match = re.search(r'\.([a-zA-Z0-9]+)(?:\?|$)', img_url)
                if ext_match and ext_match.group(1).lower() in ["jpg", "jpeg", "png", "gif", "webp"]:
                    ext = ext_match.group(1).lower()

                file_path = f"{self.download_dir}/{post_id}_{idx}.{ext}"
                ok = await aria2_download(img_url, file_path, headers=dl_headers)
                if ok and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    media_files_downloaded.append(file_path)
                else:
                    # Fallback direct aiohttp
                    try:
                        async with aiohttp.ClientSession(headers=dl_headers) as dl_sess:
                            async with dl_sess.get(img_url) as r:
                                if r.status == 200:
                                    with open(file_path, "wb") as f:
                                        f.write(await r.read())
                                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                                        media_files_downloaded.append(file_path)
                    except Exception as dl_e:
                        logger.error(f"[Reddit] Direct aiohttp image download failed: {dl_e}")

        if not media_files_downloaded:
            return {
                "success": False,
                "error": "Tidak ditemukan media (gambar/video) yang dapat diunduh pada postingan Reddit ini."
            }

        return {
            "success": True,
            "data": {
                "username": author,
                "caption": title,
                "like_count": upvotes,
                "reply_count": num_comments,
                "downloaded_files": media_files_downloaded
            }
        }
