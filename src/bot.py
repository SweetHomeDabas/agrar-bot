"""
Agrár Alapanyag Figyelő Telegram Bot
Minden reggel 7:00-kor és extrém árváltozáskor küld üzenetet.
"""

import asyncio
import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args):
        pass

def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import ApplicationBuilder

from price_monitor import PriceMonitor
from news_monitor import NewsMonitor
from summarizer import Summarizer
from notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


async def morning_report(notifier: Notifier, price_monitor: PriceMonitor,
                         news_monitor: NewsMonitor, summarizer: Summarizer):
    """Reggeli 7:00-ás összefoglaló."""
    log.info("Reggeli riport generálása...")

    prices = await price_monitor.get_all_prices()
    changes = price_monitor.calculate_changes(prices)
    news = await news_monitor.get_latest_news()
    summary = await summarizer.create_morning_summary(changes, news)

    await notifier.send_message(summary)
    log.info("Reggeli riport elküldve.")


async def check_breaking_news(notifier: Notifier, news_monitor: NewsMonitor,
                               summarizer: Summarizer):
    """Extrém fontos hírek valós idejű figyelése."""
    breaking = await news_monitor.get_breaking_news()
    if breaking:
        summary = await summarizer.create_breaking_summary(breaking)
        await notifier.send_urgent_message(summary)
        log.info(f"Sürgős hírek elküldve: {len(breaking)} cikk.")


async def check_price_alerts(notifier: Notifier, price_monitor: PriceMonitor,
                              summarizer: Summarizer):
    """Extrém árváltozások figyelése."""
    prices = await price_monitor.get_all_prices()
    alerts = price_monitor.detect_extreme_changes(prices)
    if alerts:
        summary = await summarizer.create_price_alert_summary(alerts)
        await notifier.send_urgent_message(summary)
        log.info(f"Árriasztás elküldve: {len(alerts)} termék.")


async def main():
    start_health_server()
    telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    gemini_key = os.environ["GEMINI_API_KEY"]

    app = ApplicationBuilder().token(telegram_token).build()

    notifier = Notifier(app.bot, chat_id)
    price_monitor = PriceMonitor()
    news_monitor = NewsMonitor()
    summarizer = Summarizer(gemini_key)

    scheduler = AsyncIOScheduler(timezone="Europe/Budapest")

    # Reggeli 7:00-ás riport
    scheduler.add_job(
        morning_report,
        CronTrigger(hour=7, minute=0),
        args=[notifier, price_monitor, news_monitor, summarizer],
        id="morning_report"
    )

    # Hírek figyelése 15 percenként
    scheduler.add_job(
        check_breaking_news,
        "interval",
        minutes=15,
        args=[notifier, news_monitor, summarizer],
        id="breaking_news"
    )

    # Árriasztás 10 percenként
    scheduler.add_job(
        check_price_alerts,
        "interval",
        minutes=10,
        args=[notifier, price_monitor, summarizer],
        id="price_alerts"
    )

    scheduler.start()
    log.info("Bot elindult. Várakozás feladatokra...")

    # Indítás utáni teszteléshez – azonnal küld egy tesztet
    if os.environ.get("SEND_TEST_ON_START") == "1":
        await morning_report(notifier, price_monitor, news_monitor, summarizer)

    # Futás fenntartása
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
