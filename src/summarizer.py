"""
Claude API-alapú összefoglalók generálása az áradatokból és hírekből.
"""

import logging
import httpx
from price_monitor import PriceData
from news_monitor import NewsItem

log = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


class Summarizer:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def _ask_gemini(self, prompt: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    GEMINI_URL,
                    params={"key": self.api_key},
                    json={"contents": [{"parts": [{"text": prompt}]}]}
                )
                r.raise_for_status()
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            log.error(f"Gemini API hiba: {e}")
            return "⚠️ Az összefoglalót nem sikerült generálni."

    def _format_prices(self, changes: dict) -> str:
        lines = []
        for p in changes["all"]:
            arrow = "🔺" if p.change_pct > 0 else ("🔻" if p.change_pct < 0 else "➡️")
            lines.append(
                f"{p.emoji} {p.name}: {p.price:.2f} {p.unit} "
                f"({arrow}{p.change_pct:+.1f}%)"
            )
        return "\n".join(lines)

    def _format_news(self, news: list[NewsItem]) -> str:
        if not news:
            return "Nincs releváns friss hír."
        return "\n".join(f"• [{i.source}] {i.title}" for i in news[:10])

    async def create_morning_summary(self, changes: dict,
                                     news: list[NewsItem]) -> str:
        prompt = f"""
Te egy mezőgazdasági piacelemző vagy, aki magyar gazdálkodóknak ír.
Készíts tömör REGGELI PIACI ÖSSZEFOGLALÓT magyarul az alábbi adatok alapján.

MAI ÁRAK:
{self._format_prices(changes)}

FRISS HÍREK:
{self._format_news(news)}

Tartalmazza: legfontosabb árváltozások (1-2 mondat), hírek értékelése (2-3 mondat), rövid kitekintő.
Telegram üzenet formátum, emoji-kkal. Max 280 szó.
Kezdd: 🌅 *Reggeli piaci összefoglaló*
"""
        return await self._ask_gemini(prompt)

    async def create_breaking_summary(self, news: list[NewsItem]) -> str:
        news_text = "\n".join(
            f"• [{i.source}] {i.title}\n  {i.summary[:200]}"
            for i in news
        )
        prompt = f"""
Mezőgazdasági piacelemzőként írj rövid (max 150 szó) magyar RIASZTÁST ezekről a sürgős hírekről.
Magyarázd el mi történt, melyik alapanyagot érinti, milyen árirányt valószínűsít.

HÍREK:
{news_text}

Kezdd: 🚨 *SÜRGŐS PIACI RIASZTÁS*
"""
        return await self._ask_gemini(prompt)

    async def create_price_alert_summary(self, alerts: list[PriceData]) -> str:
        lines = [
            f"• {p.emoji} {p.name}: {p.price:.2f} {p.unit} "
            f"({'emelkedett' if p.change_pct > 0 else 'csökkent'} {abs(p.change_pct):.1f}%-ot)"
            for p in alerts
        ]
        prompt = f"""
Írj rövid (max 100 szó) magyar ÁRRIASZTÁST ezekről az extrém árváltozásokról.
Lehetséges okok és következmények, szakszerűen de közérthetően.

{chr(10).join(lines)}

Kezdd: ⚡ *EXTRÉM ÁRVÁLTOZÁS ÉSZLELVE*
"""
        return await self._ask_gemini(prompt)
