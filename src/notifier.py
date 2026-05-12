"""
Telegram üzenetküldő modul.
"""

import logging
from telegram import Bot
from telegram.constants import ParseMode

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot: Bot, chat_id: str):
        self.bot = bot
        self.chat_id = chat_id

    async def send_message(self, text: str):
        """Normál napi üzenet küldése."""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN
            )
            log.info("Üzenet elküldve.")
        except Exception as e:
            log.error(f"Telegram küldési hiba: {e}")

    async def send_urgent_message(self, text: str):
        """Sürgős riasztás – kiemelten jelzett üzenet."""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                # disable_notification=False biztosítja, hogy hangjelzés is legyen
            )
            log.info("Sürgős üzenet elküldve.")
        except Exception as e:
            log.error(f"Telegram küldési hiba (sürgős): {e}")
