import asyncio
import os
from telethon import TelegramClient
from dotenv import load_dotenv

# Load local environment variables from .env
load_dotenv()

API_ID = int(os.environ.get("TELEGRAM_API_ID", 0))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")

async def main():
    if not API_ID or not API_HASH:
        print("❌ Error: TELEGRAM_API_ID or TELEGRAM_API_HASH not set in .env file.")
        return
        
    client = TelegramClient('session_get_ids', API_ID, API_HASH)
    await client.start()
    
    print("\n📦 PULLING ALL YOUR GROUPS AND PAID CHANNELS...\n")
    async for dialog in client.iter_dialogs():
        if dialog.is_channel or dialog.is_group:
            print(f"📌 Channel: {dialog.name} | ID: {dialog.id}")
            
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())