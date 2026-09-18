import asyncio
import sys
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

async def notify_task():
    await asyncio.sleep(0.1)
    print("📩 [#101] Alice: Halo apa kabar?")
    await asyncio.sleep(0.1)
    print("🔔 [PM #102 dari Bob (123)]: Tes pesan pribadi")

async def main():
    session = PromptSession()
    asyncio.create_task(notify_task())
    with patch_stdout():
        # wait a bit for notifications to finish
        await asyncio.sleep(0.3)
    print("Done testing!")

if __name__ == "__main__":
    asyncio.run(main())
