import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.environ.get("TELEGRAM_API_ID", 0))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")

async def main():
    if not API_ID or not API_HASH:
        print("❌ Error: TELEGRAM_API_ID or TELEGRAM_API_HASH not set in .env file.")
        return
        
    print("Connecting to Telegram...")
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    
    await client.start()
    
    session_string = client.session.save()
    print("\n✅ LOGIN SUCCESSFUL!")
    print("Here is your TELEGRAM_SESSION_STRING:\n")
    print(session_string)
    print("\nCopy the long string above and paste it into your .env file as:")
    print('TELEGRAM_SESSION_STRING="your_session_string"')
    print("\nAlso add it to your Streamlit Cloud Secrets and Render Environment Variables.")
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
