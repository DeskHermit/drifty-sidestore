"""Run LOCALLY to generate a Telegram StringSession. Never commit its output."""
import asyncio
import os
from getpass import getpass
from telethon import TelegramClient
from telethon.sessions import StringSession

async def main():
    api_id = int(os.getenv('TG_API_ID') or input('Telegram API ID: ').strip())
    api_hash = os.getenv('TG_API_HASH') or getpass('Telegram API hash: ')
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        print('\nCopy the following ONLY to a GitHub Actions secret named TG_SESSION:')
        print(client.session.save())
        print('\nSession grants Telegram account access. Treat it as a password.')

if __name__ == '__main__':
    asyncio.run(main())
