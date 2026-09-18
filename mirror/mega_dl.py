"""
mega_dl.py

Downloader untuk Mega (mega.nz / mega.co.nz) dengan chunked streaming dan
on-the-fly AES-128-CTR decryption menggunakan library standard cryptography.
Mendukung progress callback untuk memantau kecepatan, ETA, dan persentase unduhan.
"""
import base64
import struct
import json
import re
import os
import time
import asyncio
import logging
from typing import Optional, Callable, Dict, Any, Tuple
import aiohttp
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger("MegaDL")


def is_mega_url(url: str) -> bool:
    """Cek apakah URL adalah tautan file Mega."""
    return bool(re.search(r'mega(?:\.co)?\.nz/(?:file/|#!|#N!)?[a-zA-Z0-9_-]+[#!][a-zA-Z0-9_-]+', url))


def parse_mega_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Ekstrak file_id dan decryption key dari URL Mega."""
    # Format modern: mega.nz/file/FILE_ID#FILE_KEY
    # Format legacy: mega.nz/#!FILE_ID!FILE_KEY
    # Format export: mega.nz/#N!FILE_ID!FILE_KEY
    m = re.search(r'mega(?:\.co)?\.nz/(?:file/|#!)?([a-zA-Z0-9_-]+)[#!]([a-zA-Z0-9_-]+)', url)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r'mega(?:\.co)?\.nz/#N!([a-zA-Z0-9_-]+)!([a-zA-Z0-9_-]+)', url)
    if m:
        return m.group(1), m.group(2)
    return None, None


def base64_url_decode(data: str) -> bytes:
    """Decode string base64url Mega."""
    data += '=' * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data.replace('-', '+').replace('_', '/'))


def base64_to_a32(s: str) -> Tuple[int, ...]:
    """Ubah base64url string menjadi tuple 32-bit integer."""
    b = base64_url_decode(s)
    if len(b) % 4 != 0:
        b += b'\x00' * (4 - len(b) % 4)
    return struct.unpack('>' + 'I' * (len(b) // 4), b)


def a32_to_bytes(a: Tuple[int, ...]) -> bytes:
    """Ubah tuple 32-bit integer menjadi bytes."""
    return struct.pack('>' + 'I' * len(a), *a)


def decrypt_attr(at_b64: str, key: bytes) -> dict:
    """Dekripsi metadata file (nama file) dari Mega."""
    try:
        enc_bytes = base64_url_decode(at_b64)
        cipher = Cipher(algorithms.AES(key), modes.CBC(b'\x00' * 16), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(enc_bytes) + decryptor.finalize()
        if decrypted.startswith(b'MEGA{'):
            txt = decrypted[4:].decode('utf-8', errors='ignore')
            end = txt.rfind('}')
            if end != -1:
                return json.loads(txt[:end + 1])
    except Exception as e:
        logger.warning(f"Gagal mendekripsi atribut file Mega: {e}")
    return {}


async def download_mega(
    url: str,
    dest_dir: str,
    progress_callback: Optional[Callable[..., Any]] = None,
    chunk_size: int = 1024 * 1024,
    timeout: int = 600,
) -> Dict[str, Any]:
    """
    Download file dari mega.nz langsung secara chunked dan streaming decrypt AES-CTR.
    Dukungan progress_callback(percent=..., current=..., total=..., speed=..., eta=..., filename=...).
    """
    file_id, file_key_str = parse_mega_url(url)
    if not file_id or not file_key_str:
        return {"success": False, "file_path": None, "error": "URL Mega tidak valid.", "looks_like_html": False}

    try:
        key_a32 = base64_to_a32(file_key_str)
        if len(key_a32) < 8:
            return {"success": False, "file_path": None, "error": "Decryption key Mega rusak atau kurang lengkap.", "looks_like_html": False}

        # Kunci AES 128-bit: key[0]^key[4], key[1]^key[5], key[2]^key[6], key[3]^key[7]
        k = (
            key_a32[0] ^ key_a32[4],
            key_a32[1] ^ key_a32[5],
            key_a32[2] ^ key_a32[6],
            key_a32[3] ^ key_a32[7],
        )
        aes_key = a32_to_bytes(k)

        # IV 16 bytes: key[4], key[5], 0, 0
        iv = struct.pack('>II', key_a32[4], key_a32[5]) + b'\x00' * 8

        api_url = "https://g.api.mega.co.nz/cs?id=0"
        payload = [{"a": "g", "g": 1, "p": file_id}]

        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                data = await resp.json()

            if isinstance(data, int) and data < 0:
                err_map = {
                    -2: "File tidak ditemukan atau telah dihapus.",
                    -9: "URL atau decryption key salah.",
                    -16: "File sedang diblokir oleh Mega.",
                    -17: "Bandwidth limit kuota Mega terlampaui.",
                }
                err_msg = err_map.get(data, f"Mega API error code {data}")
                return {"success": False, "file_path": None, "error": err_msg, "looks_like_html": False}

            if not isinstance(data, list) or not data or not isinstance(data[0], dict):
                return {"success": False, "file_path": None, "error": f"Format respon Mega tidak dikenali: {data}", "looks_like_html": False}

            file_info = data[0]
            if "g" not in file_info:
                return {"success": False, "file_path": None, "error": f"Mega tidak memberikan link unduhan: {file_info}", "looks_like_html": False}

            download_url = file_info["g"]
            file_size = file_info.get("s", 0)
            at = file_info.get("at", "")

            # Dekripsi nama file
            attrs = decrypt_attr(at, aes_key)
            filename = attrs.get("n", f"mega_{file_id}")
            filename = re.sub(r'[\\/*?:"<>|]', "", filename).strip() or f"mega_{file_id}"

            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, filename)

            cipher = Cipher(algorithms.AES(aes_key), modes.CTR(iv), backend=default_backend())
            decryptor = cipher.decryptor()

            downloaded_bytes = 0
            start_time = time.time()
            last_emit = 0.0

            async with session.get(download_url, timeout=aiohttp.ClientTimeout(total=timeout)) as dl_resp:
                if dl_resp.status != 200:
                    return {"success": False, "file_path": None, "error": f"HTTP {dl_resp.status} saat mengunduh dari storage Mega.", "looks_like_html": False}

                with open(dest_path, "wb") as f:
                    while True:
                        chunk = await dl_resp.content.read(chunk_size)
                        if not chunk:
                            break
                        decrypted_chunk = decryptor.update(chunk)
                        f.write(decrypted_chunk)
                        downloaded_bytes += len(chunk)

                        now = time.time()
                        if progress_callback and (now - last_emit > 2.0 or downloaded_bytes >= file_size):
                            last_emit = now
                            elapsed = max(now - start_time, 0.001)
                            speed = downloaded_bytes / elapsed
                            eta = (file_size - downloaded_bytes) / speed if speed > 0 and file_size > downloaded_bytes else 0
                            pct = (downloaded_bytes / file_size) * 100 if file_size > 0 else 0
                            try:
                                res = progress_callback(
                                    percent=pct,
                                    current=downloaded_bytes,
                                    total=file_size,
                                    speed=speed,
                                    eta=eta,
                                    filename=filename,
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

            return {"success": True, "file_path": dest_path, "error": None, "looks_like_html": False}

    except Exception as e:
        logger.error(f"Gagal download dari Mega: {e}", exc_info=True)
        return {"success": False, "file_path": None, "error": str(e), "looks_like_html": False}
