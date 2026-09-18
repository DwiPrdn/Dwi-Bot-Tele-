import os
import math
import random
import asyncio
import logging
from telethon.tl.functions.upload import SaveBigFilePartRequest
from telethon.tl.types import InputFileBig

logger = logging.getLogger("FastTelethon")

async def fast_upload(client, file_path, progress_callback=None, workers=12):
    """
    High-throughput pipelined multi-worker Telegram file upload.
    Uses bounded async queue to stream chunks without batch stalls and low memory footprint.
    """
    part_size = 512 * 1024  # 512KB per chunk (Telegram maximum)
    file_size = os.path.getsize(file_path)
    file_id = random.getrandbits(63)
    total_parts = math.ceil(file_size / part_size)
    if total_parts == 0:
        total_parts = 1

    actual_workers = max(1, min(workers, total_parts))
    queue = asyncio.Queue(maxsize=actual_workers * 2)
    uploaded_bytes = 0
    upload_error = None

    async def worker():
        nonlocal uploaded_bytes, upload_error
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break
            part_num, chunk = item
            try:
                if not upload_error:
                    await client(SaveBigFilePartRequest(file_id, part_num, total_parts, chunk))
                    uploaded_bytes += len(chunk)
                    if progress_callback:
                        try:
                            res = progress_callback(min(uploaded_bytes, file_size), file_size)
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception:
                            pass
            except Exception as e:
                upload_error = e
                logger.error(f"[FastTelethon] Part {part_num} upload failed: {e}")
            finally:
                queue.task_done()

    worker_tasks = [asyncio.create_task(worker()) for _ in range(actual_workers)]

    try:
        with open(file_path, "rb") as f:
            for part_num in range(total_parts):
                if upload_error:
                    break
                chunk = f.read(part_size)
                await queue.put((part_num, chunk))
    finally:
        for _ in worker_tasks:
            await queue.put(None)

    await asyncio.gather(*worker_tasks)

    if upload_error:
        raise upload_error

    return InputFileBig(file_id, total_parts, os.path.basename(file_path))
