"""
Claude API-alapú összefoglalók generálása az áradatokból és hírekből.
"""

import logging
from anthropic import AsyncAnthropic
from price_monitor import PriceData
from news_monitor import NewsItem

log = logging.getLogger(__name__)


class Summarizer:
    def __init__(self, api_key: str):
        self.client = AsyncAnthropic(api_key=api_key)

    async def _ask_claude(self, prompt: str, max_tokens: int = 700) -> str:
        try:
            msg = await self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return msg.content[0].text
        except Exception as e:
            log.error(f"Claude API hiba: {e}")
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
        lines = []
        for item in news[:10]:
            lines.append(f"• [{item.source}] {item.title}")
        return "\n".join(lines)

    async def create_morning_summary(self, changes: dict,
                                     news: list[NewsItem]) -> str:
        prices_text = self._format_prices(changes)
        news_text = self._format_news(news)

        prompt = f"""
Te egy mezőgazdasági piacelemző vagy, aki magyar gazdálkodóknak és kereskedőknek ír.
Készíts egy tömör, szakszerű REGGELI PIACI ÖSSZEFOGLALÓT az alábbi adatok alapján.

MAI ÁRAK:
{prices_text}

FRISS HÍREK:
{news_text}

Kérlek, az összefoglalót magyarul írd meg, és tartalmazza:
1. A legfontosabb árváltozások kiemelése (1-2 mondat)
2. A legjelentősebb hírek rövid értékelése (2-3 mondat)
3. Rövid piaci kitekintő (mi várható ma?)

Formátum: Telegram üzenet, emoji-kkal tagolva. Max 280 szó. Ne legyenek fejlécek, legyen folyó szöveg bekezdésekkel.
Kezdd ezzel: 🌅 *Reggeli piaci összefoglaló*
"""
        return await self._ask_claude(prompt)

    async def create_breaking_summary(self, news: list[NewsItem]) -> str:
        news_text = "\n".join(
            f"• [{item.source}] {item.title}\n  {item.summary[:200]}"
            for item in news
        )

        prompt = f"""
Te egy mezőgazdasági piacelemző vagy. Az alábbi SÜRGŐS hírek azonnal befolyásolhatják az alapanyagárakat (búza, kukorica, olaj).

BREAKING HÍREK:
{news_text}

Írj egy rövid (max 150 szó), magyar nyelvű RIASZTÁST, ami elmagyarázza:
- Mi történt pontosan
- Melyik alapanyagot (búza/kukorica/olaj/szójabab) érintheti
- Milyen árirányt valószínűsít ez rövid távon

Kezdd ezzel: 🚨 *SÜRGŐS PIACI RIASZTÁS*
"""
        return await self._ask_claude(prompt, max_tokens=400)

    async def create_price_alert_summary(self, alerts: list[PriceData]) -> str:
        lines = []
        for p in alerts:
            direction = "emelkedett" if p.change_pct > 0 else "csökkent"
            lines.append(
                f"• {p.emoji} {p.name}: {p.price:.2f} {p.unit} "
                f"({direction} {abs(p.change_pct):.1f}%-ot)"
            )
        prices_text = "\n".join(lines)

        prompt = f"""
Az alábbi mezőgazdasági alapanyagoknál extrém árváltozás történt:

{prices_text}

Írj egy rövid (max 100 szó) ÁRRIASZTÁST magyarul, ami elmagyarázza a lehetséges okokat és következményeket. Legyen szakszerű de közérthető.

Kezdd ezzel: ⚡ *EXTRÉM ÁRVÁLTOZÁS ÉSZLELVE*
"""
        return await self._ask_claude(prompt, max_tokens=300)
