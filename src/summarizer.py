"""
Groq API alapú összefoglalók - INGYENES
Részletes reggeli elemzés: árak + hírek + stratégiai ajánlás
"""

import logging
from datetime import datetime
import httpx
from price_monitor import PriceData
from news_monitor import NewsItem

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

CURRENT_QUARTER = f"Q{(datetime.now().month - 1) // 3 + 1}"


class Summarizer:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def _ask_groq(self, prompt: str, max_tokens: int = 900) -> str:
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

    def _format_traded_prices(self, changes: dict) -> str:
        by_cat = changes.get("by_category", {})
        lines = []
        for cat in ["Gabona", "Olajnövény", "Energia", "Egyéb"]:
            items = [p for p in by_cat.get(cat, []) if not p.is_reference]
            if not items:
                continue
            lines.append(f"\n*{cat}:*")
            for p in items:
                arrow = "🔺" if p.change_pct > 0 else ("🔻" if p.change_pct < 0 else "➡️")
                lines.append(f"  {p.emoji} {p.name}: {p.price:.2f} USD/t ({arrow}{p.change_pct:+.1f}%)")
        return "\n".join(lines)

    def _format_specialty_prices(self, prices: list[PriceData]) -> str:
        by_cat: dict[str, list[PriceData]] = {}
        for p in prices:
            if p.is_reference:
                by_cat.setdefault(p.category, []).append(p)

        lines = []
        for cat in ["Aminosav", "Vitamin", "Mikroelem", "Adalék"]:
            items = by_cat.get(cat, [])
            if not items:
                continue
            lines.append(f"\n*{cat}:*")
            for p in items:
                trend = p.seasonal_trend.get(CURRENT_QUARTER, "stabil")
                lines.append(
                    f"  {p.emoji} {p.name}: ~{p.price:,.0f} USD/t "
                    f"| {CURRENT_QUARTER} trend: {trend}"
                )
        return "\n".join(lines)

    def _format_buy_strategy(self, prices: list[PriceData]) -> str:
        lines = []
        for p in prices:
            if p.is_reference and p.buy_strategy:
                trend = p.seasonal_trend.get(CURRENT_QUARTER, "stabil")
                lines.append(f"  {p.emoji} *{p.name}*: {p.buy_strategy}")
        return "\n".join(lines[:8])  # max 8 termék a tömörség miatt

    def _format_news(self, news: list[NewsItem]) -> str:
        if not news:
            return "Nincs releváns friss hír."
        return "\n".join(f"• [{i.source}] {i.title}" for i in news[:12])

    async def create_morning_summary(self, changes: dict, news: list[NewsItem]) -> str:
        traded_text = self._format_traded_prices(changes)
        specialty_text = self._format_specialty_prices(changes["all"])
        buy_text = self._format_buy_strategy(changes["all"])
        news_text = self._format_news(news)
        quarter = CURRENT_QUARTER

        # RÉSZ 1: Tőzsdei árak + hírek összefoglalója
        part1_prompt = f"""Te egy tapasztalt mezőgazdasági és takarmányipari alapanyag-piaci elemző vagy.
Magyar termelőknek, takarmánygyártóknak írsz napi összefoglalót.

MAI TŐZSDEI ÁRAK (USD/tonna):
{traded_text}

FRISS HÍREK:
{news_text}

Írj tömör PIACI ÖSSZEFOGLALÓT magyarul (max 200 szó):
1. Legfontosabb tőzsdei árváltozások és várható hatásuk a takarmányköltségekre
2. Hírek értékelése — mi befolyásolhatja az árakat rövid távon?
3. Mai fő kockázatok és lehetőségek

Légy konkrét, számszerű és szakszerű. Telegram formátum, emoji-kkal.
Kezdd: 🌅 *Reggeli piaci összefoglaló – {datetime.now().strftime('%Y. %m. %d.')}*"""

        part1 = await self._ask_groq(part1_prompt, max_tokens=500)

        # RÉSZ 2: Vegyipari + stratégiai ajánlás
        part2_prompt = f"""Te egy tapasztalt takarmányipari alapanyag-beszerző tanácsadó vagy.

JELENLEGI VEGYIPARI REFERENCIA ÁRAK (EU import, USD/tonna):
{specialty_text}

AKTUÁLIS NEGYEDÉV: {quarter}

VÁSÁRLÁSI STRATÉGIA ALAPANYAGONKÉNT:
{buy_text}

Írj rövid STRATÉGIAI AJÁNLÁST magyarul (max 200 szó):
1. {quarter}-ban mire érdemes most fókuszálni? (mely alapanyagoknál kedvező most vásárolni?)
2. Mely alapanyagoknál várható áremelkedés a következő negyedévben?
3. Top 3 konkrét javaslat: mit, mikor, mennyit érdemes most venni/tartani?

Légy konkrét és gyakorlatias. Telegram formátum.
Kezdd: 📊 *Stratégiai vásárlási ajánlás – {quarter}*"""

        part2 = await self._ask_groq(part2_prompt, max_tokens=500)

        return f"{part1}\n\n{part2}"

    async def create_breaking_summary(self, news: list[NewsItem]) -> str:
        news_text = "\n".join(
            f"• [{i.source}] {i.title}\n  {i.summary[:200]}"
            for i in news
        )
        prompt = f"""Takarmányipari alapanyag-piaci elemzőként írj rövid (max 180 szó) magyar RIASZTÁST.
Az alábbi hírek azonnal befolyásolhatják az alapanyagárakat.

BREAKING HÍREK:
{news_text}

Magyarázd el:
- Mi történt pontosan?
- Mely alapanyagokat érinti? (gabona, aminosav, vitamin, mikroelem?)
- Milyen árirányt valószínűsít rövid távon?
- Mit tegyen most a beszerző? (várjon / vegyen előre / fedezze magát)

Kezdd: 🚨 *SÜRGŐS PIACI RIASZTÁS*"""
        return await self._ask_groq(prompt, max_tokens=450)

    async def create_price_alert_summary(self, alerts: list[PriceData]) -> str:
        lines = [
            f"• {p.emoji} {p.name}: {p.price:.2f} USD/t "
            f"({'emelkedett' if p.change_pct > 0 else 'csökkent'} {abs(p.change_pct):.1f}%-ot)"
            for p in alerts
        ]
        prompt = f"""Írj rövid (max 150 szó) magyar ÁRRIASZTÁST.

EXTRÉM MOZGÁSOK:
{chr(10).join(lines)}

Elemezd: lehetséges okok, kapcsolódó alapanyagokra gyakorolt hatás, rövid távú kilátás.
Konkrét beszerző ajánlás: most vegyen, várjon, vagy fedezze magát?

Kezdd: ⚡ *EXTRÉM ÁRVÁLTOZÁS ÉSZLELVE*"""
        return await self._ask_groq(prompt, max_tokens=400)
