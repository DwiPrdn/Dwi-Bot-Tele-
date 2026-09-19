"""
gofile_upload.py

Upload file ke gofile.io dengan streaming, live progress updates, dan resilience.
"""
import os
import io
import time
import json
import asyncio
import logging
from typing import Optional, Callable, Any
import aiohttp

logger = logging.getLogger("GofileUpload")

UPLOAD_URL = "https://upload.gofile.io/uploadfile"


class _ProgressFileReader(io.RawIOBase):
    """Bungkus file object buat ngitung bytes yang udah kebaca oleh aiohttp streaming.
    WAJIB turunan io.RawIOBase agar kompatibel dengan aiohttp FormData payload registry.
    """

    def __init__(self, file_obj, total_size: int):
        super().__init__()
        self._file = file_obj
        self.total_size = max(total_size, 1)
        self.bytes_read = 0
        self.start_time = time.time()

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        chunk = self._file.read(size)
        self.bytes_read += len(chunk)
        return chunk

    def fileno(self) -> int:
        return self._file.fileno()

    def tell(self) -> int:
        return self._file.tell()

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._file.seek(offset, whence)

    def seekable(self) -> bool:
        return True

    def close(self) -> None:
        pass


async def get_best_gofile_server(session: aiohttp.ClientSession) -> str:
    """Ambil server terbaik dari API gofile.io jika cepat (<1.5s), fallback langsung ke UPLOAD_URL default."""
    try:
        async with session.get(
            "https://api.gofile.io/servers",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=aiohttp.ClientTimeout(total=1.5),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("status") == "ok":
                    servers = data.get("data", {}).get("servers", [])
                    if servers and isinstance(servers, list):
                        srv_name = servers[0].get("name")
                        if srv_name:
                            return f"https://{srv_name}.gofile.io/contents/uploadfile"
    except Exception:
        pass
    return UPLOAD_URL


async def upload_to_gofile(
    file_path: str,
    token: Optional[str] = None,
    folder_id: Optional[str] = None,
    progress_callback: Optional[Callable[..., Any]] = None,
) -> dict:
    """
    Upload SATU file ke gofile.io dengan chunked streaming dan live progress updates.
    Return dict hasil dari API ('downloadPage', 'fileId', dst).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File tidak ditemukan: {file_path}")

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)

    raw_file = open(file_path, "rb")
    reader = _ProgressFileReader(raw_file, file_size)

    data = aiohttp.FormData()
    data.add_field(
        "file",
        reader,
        filename=file_name,
    )
    if folder_id:
        data.add_field("folderId", folder_id)

    done_event = asyncio.Event()

    async def _progress_loop():
        last_bytes = 0
        last_time = time.time()
        while not done_event.is_set():
            try:
                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                break
            if done_event.is_set():
                break

            now = time.time()
            current = reader.bytes_read
            interval = max(now - last_time, 0.001)
            instant_speed = max(0.0, (current - last_bytes) / interval)
            last_bytes = current
            last_time = now

            if current >= file_size:
                action = "📤 Processing on Gofile..."
                percent = 100.0
                speed_val = 0.0
                eta_val = 0.0
            else:
                action = "📤 Uploading ke Gofile..."
                percent = min(99.0, (current / file_size) * 100) if file_size > 0 else 0.0
                eta_val = (file_size - current) / instant_speed if instant_speed > 0 and file_size > current else 0.0
                speed_val = instant_speed

            if progress_callback:
                try:
                    res = progress_callback(
                        percent=percent,
                        current=current,
                        total=file_size,
                        speed=speed_val,
                        eta=eta_val,
                        filename=file_name,
                        action=action,
                    )
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass

    monitor_task = None
    if progress_callback:
        monitor_task = asyncio.create_task(_progress_loop())

    try:
        async with aiohttp.ClientSession() as session:
            target_url = await get_best_gofile_server(session)
            async with session.post(
                target_url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=1800)
            ) as resp:
                resp_text = await resp.text()
                try:
                    result = json.loads(resp_text)
                except Exception:
                    raise RuntimeError(f"Gofile upload gagal (HTTP {resp.status}): {resp_text[:300]}")
    finally:
        done_event.set()
        if monitor_task:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        raw_file.close()

    if result.get("status") != "ok":
        raise RuntimeError(f"Gofile upload gagal: {result}")

    if progress_callback:
        try:
            res = progress_callback(
                percent=100.0,
                current=file_size,
                total=file_size,
                speed=0.0,
                eta=0.0,
                filename=file_name,
                action="📤 Processing on Gofile...",
            )
            if asyncio.iscoroutine(res):
                await res
        except Exception:
            pass

    return result["data"]
