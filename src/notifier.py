"""
Telegram üzenetküldő modul.
"""

import logging
from telegram import Bot

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot: Bot, chat_id: str):
        self.bot = bot
        self.chat_id = chat_id

    async def send_message(self, text: str):
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
            )
            log.info("Üzenet elküldve.")
        except Exception as e:
            log.error(f"Telegram küldési hiba: {e}")

    async def send_urgent_message(self, text: str):
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
            )
            log.info("Sürgős üzenet elküldve.")
        except Exception as e:
            log.error(f"Telegram küldési hiba (sürgős): {e}")
