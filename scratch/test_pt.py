import asyncio
import sys
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

async def background_notifications():
    for i in range(1, 4):
        await asyncio.sleep(0.5)
        print(f"📩 [#{i}] User: Pesan notifikasi ke-{i}")

async def main():
    session = PromptSession()
    task = asyncio.create_task(background_notifications())
    
    # We can test prompt_async non-blocking or simulated
    print("Testing prompt_toolkit patch_stdout setup...")
    with patch_stdout():
        # Just check patch_stdout context manager
        print("Inside patch_stdout context")
    
    await task
    print("Test passed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
