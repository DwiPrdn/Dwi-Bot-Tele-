"""
aria2_dl.py

Utility buat download SATU file pake aria2c (multi-koneksi/split) - jauh lebih
kenceng dibanding aiohttp yang narik satu koneksi doang. Kebanyakan CDN (IG,
TikTok, dst) throttle bandwidth PER-KONEKSI, jadi mecah satu file ke beberapa
koneksi paralel biasanya kasih speedup yang lumayan berasa, apalagi buat video
yang agak gede.

PREREQUISITE: aria2c harus keinstall di server dan ada di PATH:
    sudo apt install aria2        # Debian/Ubuntu
    sudo dnf install aria2        # Fedora/RHEL

Kalo aria2c nggak ketemu, fungsi ini OTOMATIS fallback ke aiohttp 1-koneksi
biasa - jadi scraper tetep jalan, cuma nggak secepat biasanya. Dicek sekali
terus di-cache (nggak ngecek ulang tiap panggilan).

Dipake sebagai drop-in buat gantiin pola lama di tiap scraper:
    async with session.get(url, headers=...) as r:
        f.write(await r.read())
jadi:
    await aria2_download(url, dest_path, headers=...)
"""
import os
import re
import time
import asyncio
import logging
from typing import Dict, Optional, Any, Callable

logger = logging.getLogger("Aria2DL")

_ARIA2_AVAILABLE: Optional[bool] = None

DEFAULT_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Mode": "navigate",
}


def _build_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    merged = dict(DEFAULT_BROWSER_HEADERS)
    if headers:
        merged.update(headers)
    return merged


def _format_speed(bps: float) -> str:
    f = float(bps)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024.0 or unit == "GB":
            return f"{f:.1f} {unit}/s"
        f /= 1024.0
    return f"{f:.1f} B/s"


def _format_eta_sec(secs: float) -> str:
    if secs <= 0 or secs > 86400 * 7:
        return "--:--"
    total_sec = int(round(secs))
    if total_sec >= 3600:
        h = total_sec // 3600
        m = (total_sec % 3600) // 60
        s = total_sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    else:
        m = total_sec // 60
        s = total_sec % 60
        return f"{m:02d}:{s:02d}"


async def _check_aria2_available() -> bool:
    global _ARIA2_AVAILABLE
    if _ARIA2_AVAILABLE is not None:
        return _ARIA2_AVAILABLE
    try:
        proc = await asyncio.create_subprocess_exec(
            "aria2c", "--version",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
        _ARIA2_AVAILABLE = (proc.returncode == 0)
    except FileNotFoundError:
        _ARIA2_AVAILABLE = False

    if not _ARIA2_AVAILABLE:
        logger.warning(
            "aria2c nggak ketemu di PATH - install dulu (`apt install aria2`) biar "
            "download-nya kenceng. Sementara jalan pake fallback aiohttp 1-koneksi."
        )
    return _ARIA2_AVAILABLE


async def _fallback_aiohttp_download(url: str, dest_path: str, headers: Optional[Dict[str, str]]) -> bool:
    import aiohttp
    try:
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        req_headers = _build_headers(headers)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=req_headers, timeout=aiohttp.ClientTimeout(total=60), allow_redirects=True) as resp:
                if resp.status != 200:
                    logger.error(f"Fallback aiohttp gagal, HTTP {resp.status}: {url}")
                    return False
                with open(dest_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                return True
    except Exception as e:
        logger.error(f"Fallback aiohttp download gagal: {e}")
        return False


def _parse_aria2_eta(eta_str: Optional[str]) -> Optional[str]:
    if not eta_str:
        return None
    if ":" in eta_str:
        return eta_str
    h_m = re.search(r'(\d+)h', eta_str)
    m_m = re.search(r'(\d+)m', eta_str)
    s_m = re.search(r'(\d+)s', eta_str)
    total_sec = 0
    if h_m: total_sec += int(h_m.group(1)) * 3600
    if m_m: total_sec += int(m_m.group(1)) * 60
    if s_m: total_sec += int(s_m.group(1))
    if total_sec >= 3600:
        h = total_sec // 3600
        m = (total_sec % 3600) // 60
        s = total_sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    else:
        m = total_sec // 60
        s = total_sec % 60
        return f"{m:02d}:{s:02d}"


async def aria2_download(
    url: str,
    dest_path: str,
    headers: Optional[Dict[str, str]] = None,
    connections: int = 16,
    timeout: int = 60,
) -> bool:
    if not await _check_aria2_available():
        return await _fallback_aiohttp_download(url, dest_path, headers)

    out_dir = os.path.dirname(dest_path) or "."
    out_name = os.path.basename(dest_path)
    os.makedirs(out_dir, exist_ok=True)

    cmd = [
        "aria2c",
        "-x", str(connections),
        "-s", str(connections),
        "-j", str(connections),
        "-k", "1M",
        "--disk-cache=32M",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--file-allocation=none",
        "--max-tries=3",
        "--retry-wait=2",
        f"--connect-timeout={min(timeout, 30)}",
        f"--timeout={timeout}",
        "--summary-interval=0",
        "--console-log-level=warn",
        "-d", out_dir,
        "-o", out_name,
    ]

    effective_headers = _build_headers(headers)
    for key, value in effective_headers.items():
        cmd += ["--header", f"{key}: {value}"]

    cmd.append(url)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await proc.communicate()
    except FileNotFoundError:
        return await _fallback_aiohttp_download(url, dest_path, headers)

    if proc.returncode != 0 or not os.path.exists(dest_path) or os.path.getsize(dest_path) < 1:
        log_tail = stdout.decode("utf-8", errors="ignore").strip()[-500:] if stdout else ""
        logger.warning(f"aria2c gagal (exit={proc.returncode}) buat {url}: {log_tail}. Coba fallback aiohttp...")
        return await _fallback_aiohttp_download(url, dest_path, headers)

    logger.info(f"[aria2] Berhasil unduh: {dest_path}")
    return True


async def _fallback_smart_stream_download(
    url: str,
    dest_dir: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 300,
    progress_callback: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """Chunked streaming fallback untuk aria2_download_smart jika aria2c gagal atau tidak tersedia."""
    import aiohttp
    os.makedirs(dest_dir, exist_ok=True)
    req_headers = _build_headers(headers)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=req_headers, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=True) as resp:
                if resp.status != 200:
                    return {
                        "success": False,
                        "file_path": None,
                        "error": f"HTTP {resp.status} saat streaming download URL: {url}",
                        "looks_like_html": False,
                    }

                cd = resp.headers.get("Content-Disposition", "")
                filename = None
                if "filename=" in cd:
                    fn_match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)["\']?', cd, re.I)
                    if fn_match:
                        filename = os.path.basename(fn_match.group(1).strip())
                if not filename:
                    from urllib.parse import urlparse, unquote
                    path = unquote(urlparse(str(resp.url)).path)
                    filename = os.path.basename(path) or f"download_{int(time.time())}"

                filename = re.sub(r'[\\/*?:"<>|]', "", filename).strip() or f"file_{int(time.time())}"
                dest_path = os.path.join(dest_dir, filename)

                total_size = 0
                cl = resp.headers.get("Content-Length")
                if cl and cl.isdigit():
                    total_size = int(cl)

                downloaded_bytes = 0
                start_time = time.time()
                last_emit = 0.0

                with open(dest_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded_bytes += len(chunk)

                        now = time.time()
                        is_done = (total_size > 0 and downloaded_bytes >= total_size)
                        if progress_callback and (now - last_emit > 2.0 or is_done):
                            last_emit = now
                            elapsed = max(now - start_time, 0.001)
                            speed_bps = downloaded_bytes / elapsed
                            eta_sec = (total_size - downloaded_bytes) / speed_bps if (speed_bps > 0 and total_size > downloaded_bytes) else 0
                            pct = (downloaded_bytes / total_size) * 100 if total_size > 0 else 0.0

                            spd_display = _format_speed(speed_bps)
                            eta_display = _format_eta_sec(eta_sec)

                            try:
                                res = progress_callback(
                                    percent=pct,
                                    speed=spd_display,
                                    eta=eta_display,
                                    current=_format_speed(downloaded_bytes).replace("/s", ""),
                                    total=_format_speed(total_size).replace("/s", "") if total_size else "N/A",
                                )
                                if asyncio.iscoroutine(res):
                                    await res
                            except TypeError:
                                try:
                                    res = progress_callback(pct)
                                    if asyncio.iscoroutine(res):
                                        await res
                                except Exception:
                                    pass
                            except Exception:
                                pass

                looks_like_html = False
                try:
                    with open(dest_path, "rb") as f:
                        head = f.read(1024)
                    text_head = head.decode("utf-8", errors="ignore").strip().lower()
                    if text_head.startswith("<!doctype") or text_head.startswith("<html") or "<html" in text_head[:300]:
                        looks_like_html = True
                    elif os.path.getsize(dest_path) < 20_000 and "<" in text_head and ("<script" in text_head or "<body" in text_head):
                        looks_like_html = True
                except Exception:
                    pass

                return {"success": True, "file_path": dest_path, "error": None, "looks_like_html": looks_like_html}
    except Exception as e:
        logger.error(f"[Fallback Smart DL] Gagal: {e}")
        return {"success": False, "file_path": None, "error": str(e), "looks_like_html": False}


async def aria2_download_smart(
    url: str,
    dest_dir: str,
    headers: Optional[Dict[str, str]] = None,
    connections: int = 16,
    timeout: int = 300,
    progress_callback: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    if not await _check_aria2_available():
        logger.info("[aria2_download_smart] aria2c tidak ada, beralih ke chunked streaming fallback.")
        return await _fallback_smart_stream_download(url, dest_dir, headers=headers, timeout=timeout, progress_callback=progress_callback)

    os.makedirs(dest_dir, exist_ok=True)
    before = set(os.listdir(dest_dir))

    cmd = [
        "aria2c",
        "-x", str(connections),
        "-s", str(connections),
        "-j", str(connections),
        "-k", "1M",
        "--disk-cache=64M",
        "--allow-overwrite=true",
        "--auto-file-renaming=true",
        "--file-allocation=none",
        "--max-tries=3",
        "--retry-wait=2",
        f"--connect-timeout={min(timeout, 30)}",
        f"--timeout={timeout}",
        "--summary-interval=1",
        "--console-log-level=warn",
        "-d", dest_dir,
    ]
    effective_headers = _build_headers(headers)
    for key, value in effective_headers.items():
        cmd += ["--header", f"{key}: {value}"]
    cmd.append(url)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    except FileNotFoundError:
        return await _fallback_smart_stream_download(url, dest_dir, headers=headers, timeout=timeout, progress_callback=progress_callback)

    last_emit = 0.0
    log_tail = []
    full_pattern = re.compile(
        r'\[#[0-9a-fA-F]+\s+([\d\.]+\w+)/([\d\.]+\w+)\((\d+)%\).*?DL:([\d\.]+\w+)(?:\s+ETA:(\w+))?\]'
    )

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text_line = line.decode("utf-8", errors="ignore").strip()
        if text_line:
            log_tail.append(text_line)
            if len(log_tail) > 10:
                log_tail.pop(0)

        if progress_callback:
            full_match = full_pattern.search(text_line)
            pct_match = re.search(r'\((\d{1,3})%\)', text_line) if not full_match else None

            if full_match or pct_match:
                now = time.time()
                if now - last_emit > 2.0:
                    last_emit = now
                    try:
                        if full_match:
                            cur_str, tot_str, pct_str, spd_str, eta_raw = full_match.groups()
                            pct = float(pct_str)
                            spd_clean = spd_str.replace("iB", "B")
                            spd_display = f"{spd_clean}/s" if not spd_clean.endswith("/s") else spd_clean
                            eta_display = _parse_aria2_eta(eta_raw)
                            try:
                                res = progress_callback(
                                    percent=pct,
                                    speed=spd_display,
                                    eta=eta_display,
                                    current=cur_str.replace("iB", "B"),
                                    total=tot_str.replace("iB", "B"),
                                )
                            except TypeError:
                                res = progress_callback(pct)
                        else:
                            pct = float(pct_match.group(1))
                            res = progress_callback(pct)

                        if asyncio.iscoroutine(res):
                            await res
                    except Exception:
                        pass

    await proc.wait()

    after = set(os.listdir(dest_dir))
    new_files = [f for f in (after - before) if not f.endswith((".aria2", ".part"))]

    if proc.returncode != 0 or not new_files:
        tail_msg = "\n".join(log_tail[-5:])
        logger.warning(f"aria2c gagal (exit={proc.returncode}): {tail_msg}. Mencoba streaming fallback...")
        fallback_res = await _fallback_smart_stream_download(url, dest_dir, headers=headers, timeout=timeout, progress_callback=progress_callback)
        if fallback_res["success"]:
            return fallback_res
        return {
            "success": False,
            "file_path": None,
            "error": tail_msg or f"aria2c exit code {proc.returncode}",
            "looks_like_html": False,
        }

    file_path = os.path.join(dest_dir, new_files[0])

    looks_like_html = False
    try:
        with open(file_path, "rb") as f:
            head = f.read(1024)
        text_head = head.decode("utf-8", errors="ignore").strip().lower()
        if text_head.startswith("<!doctype") or text_head.startswith("<html") or "<html" in text_head[:300]:
            looks_like_html = True
        elif os.path.getsize(file_path) < 20_000 and "<" in text_head and ("<script" in text_head or "<body" in text_head):
            looks_like_html = True
    except Exception:
        pass

    return {"success": True, "file_path": file_path, "error": None, "looks_like_html": looks_like_html}
