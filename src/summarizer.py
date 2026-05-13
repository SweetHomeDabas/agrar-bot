"""
Groq API alapú összefoglalók - INGYENES
"""

import logging
import httpx
from price_monitor import PriceData
from news_monitor import NewsItem

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class Summarizer:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def _ask_groq(self, prompt: str, max_tokens: int = 700) -> str:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": "llama-3.1-8b-instant",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens
                    }
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.error(f"Groq API hiba: {e}")
            return "⚠️ Az összefoglalót nem sikerült generálni."

    def _format_prices_by_category(self, changes: dict) -> str:
        by_cat = changes.get("by_category", {})
        lines = []
        category_order = ["Gabona", "Olajnövény", "Energia", "Egyéb", "Vegyipari"]

        for cat in category_order:
            items = by_cat.get(cat, [])
            if not items:
                continue
            lines.append(f"\n*{cat}:*")
            for p in items:
                if p.is_reference:
                    lines.append(f"  {p.emoji} {p.name}: ~{p.price:.0f} {p.unit} (referencia ár)")
                else:
                    arrow = "🔺" if p.change_pct > 0 else ("🔻" if p.change_pct < 0 else "➡️")
                    lines.append(
                        f"  {p.emoji} {p.name}: {p.price:.2f} {p.unit} "
                        f"({arrow}{p.change_pct:+.1f}%)"
                    )
        return "\n".join(lines)

    def _format_news(self, news: list[NewsItem]) -> str:
        if not news:
            return "Nincs releváns friss hír."
        return "\n".join(f"• [{i.source}] {i.title}" for i in news[:12])

    async def create_morning_summary(self, changes: dict, news: list[NewsItem]) -> str:
        prices_text = self._format_prices_by_category(changes)
        news_text = self._format_news(news)

        prompt = f"""Te egy mezőgazdasági és vegyipari alapanyag-piaci elemző vagy, aki magyar termelőknek és kereskedőknek ír napi összefoglalót.

MAI ÁRAK (USD/tonna alapon):
{prices_text}

FRISS HÍREK:
{news_text}

Írj tömör REGGELI PIACI ÖSSZEFOGLALÓT magyarul. Tartalmazza:
1. A legjelentősebb árváltozások kiemelése (gabonák, olajok, vegyipari)
2. Fontos hírek rövid értékelése (mi befolyásolhatja az árakat?)
3. Rövid kitekintő (mire érdemes figyelni ma?)

Formátum: Telegram üzenet, emoji-kkal tagolva, max 300 szó. Légy konkrét és szakszerű.
Kezdd: 🌅 *Reggeli piaci összefoglaló*"""

        return await self._ask_groq(prompt)

    async def create_breaking_summary(self, news: list[NewsItem]) -> str:
        news_text = "\n".join(
            f"• [{i.source}] {i.title}\n  {i.summary[:200]}"
            for i in news
        )
        prompt = f"""Mezőgazdasági és vegyipari alapanyag-piaci elemzőként írj rövid (max 150 szó) magyar RIASZTÁST.
Az alábbi hírek azonnal befolyásolhatják az alapanyagárakat (búza, kukorica, szója, lizin, metionin, vitaminok stb.)

BREAKING HÍREK:
{news_text}

Magyarázd el: mi történt, melyik alapanyagot érinti, milyen árirányt valószínűsít rövid távon.
Kezdd: 🚨 *SÜRGŐS PIACI RIASZTÁS*"""

        return await self._ask_groq(prompt, max_tokens=400)

    async def create_price_alert_summary(self, alerts: list[PriceData]) -> str:
        lines = [
            f"• {p.emoji} {p.name}: {p.price:.2f} {p.unit} "
            f"({'emelkedett' if p.change_pct > 0 else 'csökkent'} {abs(p.change_pct):.1f}%-ot)"
            for p in alerts
        ]
        prompt = f"""Írj rövid (max 120 szó) magyar ÁRRIASZTÁST ezekről az extrém mozgásokról.
Lehetséges okok, érintett kapcsolódó termékek és rövid távú következmények.

{chr(10).join(lines)}

Kezdd: ⚡ *EXTRÉM ÁRVÁLTOZÁS ÉSZLELVE*"""

        return await self._ask_groq(prompt, max_tokens=350)
