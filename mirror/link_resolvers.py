"""
link_resolvers.py

Ubah link SHARE PAGE (yang butuh diklik/konfirmasi manual di browser) jadi
link DIRECT DOWNLOAD yang bisa langsung ditarik aria2c / downloader:

- Google Drive: file kecil langsung, file gede (>~100MB) butuh token confirm.
- Mediafire: parsing tombol unduh dengan browser headers, referer & pola regex lengkap.
- Pixeldrain: /u/{id} dipetain ke /api/file/{id}.
- Gofile: /d/{contentId} dipetain via Gofile API untuk mendapatkan direct link.
- Krakenfiles: scrape token & form download untuk mendapatkan direct URL.
- Dropbox: konversi dl=0 ke dl=1.
- Catbox/Litterbox: tautan langsung.
- Mega: deteksi is_mega_url untuk diarahkan ke mega_dl.
- Workupload: API getDownloadServer atau form scraping.
- 1fichier: scraping tombol/form unduh.
- Sfile.mobi: scraping tombol unduh langsung.
- OneDrive: konversi tautan berbagi ke tautan unduh langsung.
- Generic Landing / Mirror: ikuti redirect HTTP (301/302/307/308), deteksi binary Content-Type,
  Content-Disposition, meta refresh, JavaScript redirect, form submit download,
  dan tombol unduh file arsip/media multi-hop.
"""
import re
import asyncio
import logging
from urllib.parse import urljoin, urlparse, urlencode, unquote
from typing import Tuple, Dict, Optional, Any
import aiohttp
from bs4 import BeautifulSoup

from .mega_dl import is_mega_url

logger = logging.getLogger("LinkResolvers")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    "Sec-Ch-Ua": '"Not-A.Brand";v="99", "Chromium";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

BINARY_EXTENSIONS = (
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".zst",
    ".iso", ".img", ".dmg", ".bin",
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm",
    ".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a",
    ".pdf", ".epub", ".mobi", ".docx", ".xlsx",
    ".apk", ".xapk", ".exe", ".msi", ".deb", ".rpm",
    ".torrent"
)

BIN_EXT_PATTERN = re.compile(
    r'\.(?:zip|rar|7z|tar|gz|bz2|xz|zst|iso|img|dmg|bin|mp4|mkv|avi|mov|flv|wmv|webm|mp3|flac|wav|aac|ogg|m4a|pdf|epub|apk|xapk|exe|msi|deb|rpm|torrent)(?:\?|$)',
    re.I
)


async def _fetch_html_fallback_curl(url: str, referer: str = None) -> str:
    """Fallback mengambil respon HTML menggunakan curl untuk melewati proteksi bot / Cloudflare sederhana."""
    cmd = [
        "curl", "-s", "-L",
        "-A", BROWSER_HEADERS["User-Agent"],
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "-H", "Accept-Language: en-US,en;q=0.9",
        "-H", "Sec-Fetch-Dest: document",
        "-H", "Sec-Fetch-Mode: navigate",
        "-H", "Sec-Fetch-Site: none",
        "--max-time", "20",
    ]
    if referer:
        cmd.extend(["-e", referer])
    cmd.append(url)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await proc.communicate()
        return stdout.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.debug(f"Curl fallback error: {e}")
        return ""


async def _resolve_gdrive(session: aiohttp.ClientSession, url: str) -> Tuple[str, Dict[str, str]]:
    """Resolve Google Drive link ke direct download, menangani halaman konfirmasi file besar."""
    req_headers = {"User-Agent": BROWSER_HEADERS["User-Agent"]}
    m = re.search(r'/d/([a-zA-Z0-9_-]+)|[?&]id=([a-zA-Z0-9_-]+)', url)
    if not m:
        return url, req_headers
    file_id = m.group(1) or m.group(2)

    base_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    try:
        async with session.get(base_url, headers=BROWSER_HEADERS, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            cd = resp.headers.get("Content-Disposition", "").lower()
            if "attachment" in cd or ("text/html" not in content_type and "text/plain" not in content_type):
                return str(resp.url), req_headers

            html_text = await resp.text()

            token = None
            for key, morsel in session.cookie_jar.filter_cookies(base_url).items():
                if key.startswith("download_warning"):
                    token = morsel.value
                    break

            try:
                soup = BeautifulSoup(html_text, "html.parser")
                form = soup.find("form", id="download-form") or soup.find("form", action=re.compile(r"drive\.usercontent\.google\.com|download", re.I))
                if form:
                    action = form.get("action", "")
                    inputs = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
                    if action and inputs:
                        if action.startswith("/"):
                            action = urljoin("https://drive.usercontent.google.com", action)
                        return f"{action}?{urlencode(inputs)}", req_headers

                link = soup.find("a", id="uc-download-link")
                if link and link.get("href"):
                    return urljoin(base_url, link["href"]), req_headers
            except Exception:
                pass

            if not token:
                cm = re.search(r'confirm=([0-9A-Za-z_-]+)', html_text)
                if cm:
                    token = cm.group(1)

            if token:
                return f"https://drive.google.com/uc?export=download&confirm={token}&id={file_id}", req_headers
    except Exception as e:
        logger.warning(f"[GDrive resolver] Gagal resolve, pake URL asli: {e}")

    return base_url, req_headers

async def _resolve_mediafire(session: aiohttp.ClientSession, url: str) -> Tuple[str, Dict[str, str]]:
    """Resolve Mediafire share/landing link ke direct CDN link."""

    m_short = re.search(r'mediafire\.com/\?([a-zA-Z0-9_-]+)', url)
    if m_short:
        url = f"https://www.mediafire.com/file/{m_short.group(1)}"

    headers = dict(BROWSER_HEADERS)
    headers["Referer"] = "https://www.mediafire.com/"
    dl_headers = {"Referer": "https://www.mediafire.com/", "User-Agent": BROWSER_HEADERS["User-Agent"]}
    html_text = ""

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            cd = resp.headers.get("Content-Disposition", "").lower()

            if "attachment" in cd or ("text/html" not in content_type and "text/plain" not in content_type):
                return str(resp.url), dl_headers

            if resp.status == 200:
                html_text = await resp.text()
    except Exception as e:
        logger.warning(f"[Mediafire resolver] aiohttp request error: {e}")


    if not html_text or ("downloadButton" not in html_text and "download_link" not in html_text):
        curl_html = await _fetch_html_fallback_curl(url, referer="https://www.mediafire.com/")
        if curl_html:
            html_text = curl_html

    if html_text:
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            btn = soup.select_one("a#downloadButton, a.popsok, a.download_link, a[aria-label='Download file']")
            if btn and btn.get("href"):
                direct_url = btn["href"].replace("&amp;", "&").strip()
                if direct_url.startswith("//"):
                    direct_url = "https:" + direct_url
                if direct_url.startswith("http"):
                    return direct_url, dl_headers
        except Exception:
            pass

        patterns = [
            r'href=["\']((?:https?:)?//download\d*\.mediafire\.com/[^"\']+)["\']',
            r'id=["\']downloadButton["\'][^>]*href=["\']([^"\']+)["\']',
            r'href=["\']([^"\']+)["\'][^>]*id=["\']downloadButton["\']',
            r'aria-label=["\']Download file["\'][^>]*href=["\']([^"\']+)["\']',
            r'href=["\']([^"\']+)["\'][^>]*aria-label=["\']Download file["\']',
            r'class=["\'][^"\']*download_link[^"\']*["\'][^>]*href=["\']([^"\']+)["\']',
            r'window\.location\.href\s*=\s*[\'"]([^\'"]+mediafire\.com/[^\'"]+)[\'"]',
            r'kNO\s*=\s*[\'"]([^\'"]+)[\'"]',
            r'(https?://download\d*\.mediafire\.com/[^\s"\'<>]+)',
        ]
        for pat in patterns:
            m = re.search(pat, html_text, re.IGNORECASE)
            if m:
                direct_url = m.group(1).replace("&amp;", "&").strip()
                if direct_url.startswith("//"):
                    direct_url = "https:" + direct_url
                return direct_url, dl_headers

    return url, dl_headers


def _resolve_pixeldrain(url: str) -> Tuple[str, Dict[str, str]]:
    req_headers = {"User-Agent": BROWSER_HEADERS["User-Agent"]}
    m = re.search(r'pixeldrain\.com/(?:u|l)/([a-zA-Z0-9]+)', url)
    if m:
        return f"https://pixeldrain.com/api/file/{m.group(1)}", req_headers
    return url, req_headers


async def _resolve_gofile(session: aiohttp.ClientSession, url: str) -> Tuple[str, Dict[str, str]]:
    req_headers = {"User-Agent": BROWSER_HEADERS["User-Agent"]}
    m = re.search(r'gofile\.io/d/([a-zA-Z0-9_-]+)', url)
    if not m:
        return url, req_headers
    content_id = m.group(1)

    try:
        from mirror.gofile_api import resolve_gofile_content
        direct_url, dl_headers = await resolve_gofile_content(session, content_id)
        if direct_url:
            return direct_url, dl_headers
    except Exception as e:
        logger.warning(f"[Gofile resolver] Gagal resolve {url}: {e}")

    return url, req_headers



async def _resolve_krakenfiles(session: aiohttp.ClientSession, url: str) -> Tuple[str, Dict[str, str]]:
    headers = dict(BROWSER_HEADERS)
    headers["Referer"] = url
    dl_headers = {"Referer": url, "User-Agent": BROWSER_HEADERS["User-Agent"]}

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            html = await resp.text()

        token_match = re.search(r'name="token"\s+value="([^"]+)"', html)
        action_match = re.search(r'id="dl-form"\s+action="([^"]+)"', html)
        if not action_match:
            action_match = re.search(r'action="(/download/[^"]+)"', html)

        if token_match and action_match:
            action_url = action_match.group(1)
            if action_url.startswith("/"):
                action_url = urljoin(url, action_url)
            post_data = {"token": token_match.group(1)}
            async with session.post(action_url, data=post_data, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as post_resp:
                res_json = await post_resp.json()
                if res_json.get("status") == "ok" and res_json.get("url"):
                    return res_json["url"], dl_headers
    except Exception as e:
        logger.warning(f"[Krakenfiles resolver] Gagal resolve: {e}")

    return url, dl_headers


def _resolve_dropbox(url: str) -> Tuple[str, Dict[str, str]]:
    req_headers = {"User-Agent": BROWSER_HEADERS["User-Agent"]}
    if "dropbox.com" in url:
        if "dl=0" in url:
            return url.replace("dl=0", "dl=1"), req_headers
        elif "?" not in url:
            return url + "?dl=1", req_headers
        elif "dl=1" not in url:
            return url + "&dl=1", req_headers
    return url, req_headers


def _resolve_onedrive(url: str) -> Tuple[str, Dict[str, str]]:
    req_headers = {"User-Agent": BROWSER_HEADERS["User-Agent"]}
    if "1drv.ms" in url or "onedrive.live.com" in url:
        if "download=1" not in url:
            sep = "&" if "?" in url else "?"
            return url + sep + "download=1", req_headers
    return url, req_headers


async def _resolve_workupload(session: aiohttp.ClientSession, url: str) -> Tuple[str, Dict[str, str]]:
    dl_headers = {"Referer": url, "User-Agent": BROWSER_HEADERS["User-Agent"]}
    m = re.search(r'workupload\.com/(?:file|archive)/([a-zA-Z0-9]+)', url)
    if m:
        file_id = m.group(1)
        api_url = f"https://workupload.com/api/file/getDownloadServer/{file_id}"
        try:
            async with session.get(api_url, headers=BROWSER_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if data.get("success") and data.get("data"):
                    srv = data["data"].get("server")
                    token = data["data"].get("token")
                    if srv and token:
                        return f"https://{srv}.workupload.com/download/{token}/{file_id}", dl_headers
        except Exception as e:
            logger.debug(f"[Workupload resolver] error: {e}")
    return url, dl_headers


async def _resolve_sfile(session: aiohttp.ClientSession, url: str) -> Tuple[str, Dict[str, str]]:
    dl_headers = {"Referer": url, "User-Agent": BROWSER_HEADERS["User-Agent"]}
    try:
        async with session.get(url, headers=BROWSER_HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        btn = soup.select_one("a#download, a.download-btn, a.btn-download")
        if btn and btn.get("href"):
            direct_url = urljoin(url, btn["href"])
            return direct_url, dl_headers
    except Exception as e:
        logger.debug(f"[Sfile resolver] error: {e}")
    return url, dl_headers


def _extract_download_link_from_html(html: str, base_url: str) -> Optional[str]:
    """Ekstrak direct download link dari teks HTML menggunakan heuristic DOM & regex."""
    if not html:
        return None

    meta_refresh = re.search(r'<meta[^>]*http-equiv=[\'"]refresh[\'"][^>]*content=[\'"][^;\'"]*;\s*url=([^"\'\s>]+)[\'"]', html, re.I)
    if meta_refresh:
        target = meta_refresh.group(1).strip()
        if target and not target.startswith("#"):
            return urljoin(base_url, target)

    try:
        soup = BeautifulSoup(html, "html.parser")

        a_download = soup.find("a", attrs={"download": True, "href": True})
        if a_download and a_download["href"] and not a_download["href"].startswith("#"):
            return urljoin(base_url, a_download["href"])

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href.startswith("#") and not href.startswith("javascript:"):
                if BIN_EXT_PATTERN.search(href):
                    return urljoin(base_url, href)

        btn = soup.select_one(
            "a#downloadButton, a#download_link, a#download, a.btn-download, a.btn_download, "
            "a[class*='download' i], a[id*='download' i], a[aria-label*='download' i]"
        )
        if btn and btn.get("href"):
            href = btn["href"].strip()
            if not href.startswith("#") and not href.startswith("javascript:"):
                return urljoin(base_url, href)

        text_btn = soup.find(
            "a",
            string=re.compile(r"^\s*(?:direct\s+)?download(?:\s+now|\s+file)?\s*$|^\s*unduh(?:\s+sekarang|\s+file)?\s*$", re.I),
            href=True
        )
        if text_btn and text_btn["href"] and not text_btn["href"].startswith("#"):
            return urljoin(base_url, text_btn["href"])

        for tag in soup.find_all(attrs={"data-url": True}):
            d_url = tag["data-url"].strip()
            if d_url and not d_url.startswith("#") and not d_url.startswith("javascript:"):
                return urljoin(base_url, d_url)

        for tag in soup.find_all(attrs={"data-href": True}):
            d_href = tag["data-href"].strip()
            if d_href and not d_href.startswith("#") and not d_href.startswith("javascript:"):
                return urljoin(base_url, d_href)

        for form in soup.find_all("form"):
            action = form.get("action", "").strip()
            form_text = form.get_text().lower()
            submit_btn = form.find(["button", "input"], attrs={"type": ["submit", "button"]})
            is_dl_form = "download" in action.lower() or "download" in form_text or (submit_btn and "download" in str(submit_btn).lower())
            if is_dl_form and action:
                if action.startswith("/"):
                    action = urljoin(base_url, action)
                inputs = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
                if inputs:
                    return f"{action}?{urlencode(inputs)}"
                return action

    except Exception as soup_err:
        logger.debug(f"[Extract link from HTML] BS4 error: {soup_err}")

    js_patterns = [
        r'window\.location(?:\.href)?\s*=\s*[\'"]([^\'"]+)[\'"]',
        r'location\.replace\([\'"]([^\'"]+)[\'"]\)',
        r'var\s+(?:download_?url|file_?url|download_?link|direct_?url|target_?url)\s*=\s*[\'"]([^\'"]+)[\'"]',
        r'["\'](?:download_url|file_url|direct_url)["\']\s*:\s*["\']([^"\']+)["\']',
    ]
    for pat in js_patterns:
        m = re.search(pat, html, re.I)
        if m:
            target = m.group(1).strip().replace("\\/", "/")
            if not target.startswith("#") and not target.startswith("javascript:") and "http" in target:
                return urljoin(base_url, target)

    return None


async def _resolve_from_html_content(session: aiohttp.ClientSession, html_content: str, source_url: str) -> Tuple[str, Dict[str, str]]:
    """Mencoba mengekstrak dan me-resolve link unduhan biner langsung dari teks HTML yang sudah ada."""
    dl_headers = {"Referer": source_url, "User-Agent": BROWSER_HEADERS["User-Agent"]}
    extracted = _extract_download_link_from_html(html_content, source_url)
    if extracted and extracted != source_url:

        low_ext = extracted.lower()
        if not any(low_ext.endswith(ext) or f"{ext}?" in low_ext for ext in BINARY_EXTENSIONS):
            try:
                async with session.get(extracted, headers=dict(BROWSER_HEADERS, Referer=source_url), timeout=aiohttp.ClientTimeout(total=15), allow_redirects=True) as resp:
                    ct = resp.headers.get("Content-Type", "").lower()
                    cd = resp.headers.get("Content-Disposition", "").lower()
                    if "attachment" in cd or ("text/html" not in ct and "text/plain" not in ct):
                        return str(resp.url), dl_headers
                    h2 = await resp.text()
                    sub_link = _extract_download_link_from_html(h2, str(resp.url))
                    if sub_link:
                        return sub_link, dl_headers
            except Exception:
                pass
        return extracted, dl_headers
    return source_url, dl_headers


async def _resolve_generic_landing(session: aiohttp.ClientSession, url: str) -> Tuple[str, Dict[str, str]]:
    """
    Resolver umum untuk landing page dan situs direct mirror:
    - Mengikuti pengalihan HTTP (301/302/307/308) dengan browser headers
    - Mendeteksi apakah URL mengarah langsung ke biner (Content-Type non-HTML / Content-Disposition)
    - Mendeteksi <meta http-equiv="refresh"> dan JS redirects
    - Parsing DOM menggunakan BeautifulSoup (HTML5 download, tombol unduh, form submission)
    - Mendukung multi-hop (hingga 2 hop landing page)
    - Fallback curl dengan -w '%{url_effective}' jika anti-bot blocking
    """
    html = ""
    current_url = url
    dl_headers = {"Referer": url, "User-Agent": BROWSER_HEADERS["User-Agent"]}

    try:
        async with session.get(url, headers=BROWSER_HEADERS, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=True) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            cd = resp.headers.get("Content-Disposition", "").lower()
            current_url = str(resp.url)
            dl_headers["Referer"] = current_url

            if "attachment" in cd or ("text/html" not in content_type and "text/plain" not in content_type):
                return current_url, dl_headers

            html = await resp.text()
    except Exception as e:
        logger.debug(f"[Generic resolver] aiohttp error: {e}")

    if not html:
        curl_html = await _fetch_html_fallback_curl(url)
        if curl_html:
            html = curl_html

    if html:
        extracted_link = _extract_download_link_from_html(html, current_url)
        if extracted_link and extracted_link != current_url:
            low_ext = extracted_link.lower()
            is_bin = any(low_ext.endswith(ext) or f"{ext}?" in low_ext for ext in BINARY_EXTENSIONS)
            if is_bin:
                return extracted_link, dl_headers

            try:
                async with session.get(
                    extracted_link,
                    headers=dict(BROWSER_HEADERS, Referer=current_url),
                    timeout=aiohttp.ClientTimeout(total=15),
                    allow_redirects=True
                ) as resp2:
                    ct2 = resp2.headers.get("Content-Type", "").lower()
                    cd2 = resp2.headers.get("Content-Disposition", "").lower()
                    if "attachment" in cd2 or ("text/html" not in ct2 and "text/plain" not in ct2):
                        return str(resp2.url), dict(dl_headers, Referer=extracted_link)
                    html2 = await resp2.text()
                    sub_link = _extract_download_link_from_html(html2, str(resp2.url))
                    if sub_link:
                        return sub_link, dict(dl_headers, Referer=str(resp2.url))
            except Exception as e2:
                logger.debug(f"[Generic resolver] 2nd hop error: {e2}")

            return extracted_link, dl_headers

    try:
        cmd = ["curl", "-s", "-L", "-o", "/dev/null", "-w", "%{url_effective}", "-A", BROWSER_HEADERS["User-Agent"], url]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await proc.communicate()
        eff_url = out.decode("utf-8").strip()
        if eff_url and eff_url.startswith("http") and eff_url != url:
            return eff_url, dl_headers
    except Exception:
        pass

    return current_url, dl_headers


async def resolve_direct_url(session: aiohttp.ClientSession, url: str) -> Tuple[str, Dict[str, str]]:
    """
    Router utama - deteksi platform dari domain di URL, panggil resolver yang sesuai.
    Mengembalikan tuple: (direct_url, request_headers).
    """
    low = url.lower()
    default_headers = {"User-Agent": BROWSER_HEADERS["User-Agent"]}

    if is_mega_url(url):
        return url, default_headers
    if "drive.google.com" in low or "docs.google.com" in low:
        return await _resolve_gdrive(session, url)
    if "mediafire.com" in low:
        return await _resolve_mediafire(session, url)
    if "pixeldrain.com" in low:
        return _resolve_pixeldrain(url)
    if "gofile.io" in low:
        return await _resolve_gofile(session, url)
    if "krakenfiles.com" in low:
        return await _resolve_krakenfiles(session, url)
    if "dropbox.com" in low:
        return _resolve_dropbox(url)
    if "1drv.ms" in low or "onedrive.live.com" in low:
        return _resolve_onedrive(url)
    if "workupload.com" in low:
        return await _resolve_workupload(session, url)
    if "sfile.mobi" in low:
        return await _resolve_sfile(session, url)
    if "catbox.moe" in low:
        return url, default_headers

    return await _resolve_generic_landing(session, url)
