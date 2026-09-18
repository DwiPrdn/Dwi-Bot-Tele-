import asyncio
import aiohttp
import hashlib
import time
import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger("GofileAPI")

GOFILE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
GOFILE_LANG = "en-US"
GOFILE_SALT = "12af056dacea0b"

# In-memory cache
_cached_token: Optional[str] = None
_cached_proxy: Optional[str] = "http://181.78.74.252:999"
_proxy_checked_at: float = 0.0
_direct_working: bool = False
_direct_checked_at: float = 0.0


async def check_direct_connectivity(session: aiohttp.ClientSession) -> bool:
    global _direct_working, _direct_checked_at
    now = time.time()
    if now - _direct_checked_at < 60:
        return _direct_working
    _direct_checked_at = now
    try:
        async with session.get("https://api.gofile.io/servers", timeout=aiohttp.ClientTimeout(total=2.5)) as resp:
            if resp.status == 200:
                _direct_working = True
                return True
    except Exception:
        pass
    _direct_working = False
    return False


async def get_working_proxy(session: aiohttp.ClientSession) -> Optional[str]:
    global _cached_proxy, _proxy_checked_at
    if await check_direct_connectivity(session):
        return None

    now = time.time()
    if _cached_proxy and (now - _proxy_checked_at < 300):
        # Quick test cached proxy
        try:
            async with session.get("https://api.gofile.io/servers", proxy=_cached_proxy, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    return _cached_proxy
        except Exception:
            _cached_proxy = None

    # Fetch fresh proxies
    logger.info("[Gofile] Scanning for a working proxy for Gofile API...")
    url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=yes&anonymity=all"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            text = await resp.text()
            candidates = [p.strip() for p in text.strip().splitlines() if p.strip()]
    except Exception as e:
        logger.debug(f"[Gofile] Failed to fetch proxy list: {e}")
        candidates = []

    # Priority to known fast proxies
    priorities = ["181.78.74.252:999"]
    for pr in candidates:
        if pr not in priorities:
            priorities.append(pr)

    for p in priorities[:25]:
        proxy_url = f"http://{p}"
        try:
            async with session.get("https://api.gofile.io/servers", proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    logger.info(f"[Gofile] Found working proxy: {proxy_url}")
                    _cached_proxy = proxy_url
                    _proxy_checked_at = now
                    return proxy_url
        except Exception:
            continue

    return None


def calculate_website_token(account_token: str, ua: str = GOFILE_UA, lang: str = GOFILE_LANG) -> str:
    time_slice = str(int(time.time()) // 14400)
    to_hash = f"{ua}::{lang}::{account_token}::{time_slice}::{GOFILE_SALT}"
    return hashlib.sha256(to_hash.encode("utf-8")).hexdigest()


async def get_or_create_account_token(session: aiohttp.ClientSession, user_token: Optional[str] = None) -> Optional[str]:
    global _cached_token
    if user_token:
        return user_token.strip()
    if _cached_token:
        return _cached_token

    proxy = await get_working_proxy(session)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": GOFILE_UA,
        "Origin": "https://gofile.io",
        "Referer": "https://gofile.io/",
    }
    try:
        async with session.post(
            "https://api.gofile.io/accounts",
            json={},
            headers=headers,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            data = await resp.json()
            if data.get("status") == "ok":
                token = data.get("data", {}).get("token")
                if token:
                    _cached_token = token
                    return token
    except Exception as e:
        logger.warning(f"[Gofile] Gagal create guest account: {e}")

    return None


async def resolve_gofile_content(
    session: aiohttp.ClientSession,
    content_id: str,
    user_token: Optional[str] = None,
    password: Optional[str] = None,
) -> Tuple[Optional[str], Dict[str, str]]:
    token = await get_or_create_account_token(session, user_token=user_token)
    if not token:
        return None, {}

    wt = calculate_website_token(token)
    proxy = await get_working_proxy(session)

    query = f"page=1&pageSize=100&sortField=name&sortDirection=1"
    if password:
        query += f"&password={hashlib.sha256(password.encode()).hexdigest()}"

    api_url = f"https://api.gofile.io/contents/{content_id}?{query}"
    headers = {
        "User-Agent": GOFILE_UA,
        "Authorization": f"Bearer {token}",
        "X-Website-Token": wt,
        "X-BL": GOFILE_LANG,
        "Origin": "https://gofile.io",
        "Referer": f"https://gofile.io/d/{content_id}",
        "Cookie": f"accountToken={token}",
        "Accept": "application/json",
    }

    dl_headers = {
        "User-Agent": GOFILE_UA,
        "Cookie": f"accountToken={token}",
        "Referer": "https://gofile.io/",
    }

    try:
        async with session.get(
            api_url,
            headers=headers,
            proxy=proxy,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json()
            if data.get("status") == "ok":
                content_info = data.get("data", {})
                # Single direct link
                if content_info.get("link"):
                    return content_info["link"], dl_headers

                # Children items
                children = content_info.get("children", {})
                if isinstance(children, dict):
                    for child in children.values():
                        if isinstance(child, dict) and child.get("link"):
                            return child["link"], dl_headers
                elif isinstance(children, list):
                    for child in children:
                        if isinstance(child, dict) and child.get("link"):
                            return child["link"], dl_headers
    except Exception as e:
        logger.warning(f"[Gofile] Resolve error: {e}")

    return None, dl_headers
