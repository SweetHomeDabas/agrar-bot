"""
Groq API alapú összefoglalók
Tőzsdei árak: USD/t + HUF/t
Vegyipari árak: EUR/kg (valós piaci árak, CIF Magyarország)
"""

import logging
from datetime import datetime
import httpx
from price_monitor import PriceData
from news_monitor import NewsItem
from currency import get_exchange_rates

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CURRENT_QUARTER = f"Q{(datetime.now().month - 1) // 3 + 1}"
HU_LOGISTICS = 1.08  # 8% logisztikai felár


class Summarizer:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._rates = {"USD_HUF": 360.0, "USD_EUR": 0.92}

    async def refresh_rates(self):
        self._rates = await get_exchange_rates()

    async def _ask_groq(self, prompt: str, max_tokens: int = 800) -> str:
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
            return "Az osszefoglalot nem sikerult generalni."

    def _usd_to_huf(self, usd_t: float) -> int:
        return int(usd_t * HU_LOGISTICS * self._rates["USD_HUF"])

    def _format_traded(self, changes: dict) -> str:
        lines = [f"[Arfolyam: 1 USD = {self._rates['USD_HUF']:.0f} HUF]"]
        for cat in ["Gabona", "Olajnoveny", "Energia", "Egyeb"]:
            items = [p for p in changes["all"]
                     if not p.is_reference and p.category == cat]
            if not items:
                for key, val in changes.get("by_category", {}).items():
                    if cat[:5].lower() in key.lower():
                        items = [p for p in val if not p.is_reference]
                        break
            if not items:
                continue
            lines.append(f"\n-- {cat} --")
            for p in items:
                arrow = "fel" if p.change_pct > 0 else ("le" if p.change_pct < 0 else "=")
                huf = self._usd_to_huf(p.price)
                lines.append(
                    f"{p.emoji} {p.name}: {p.price:.1f} USD/t "
                    f"({huf:,} HUF/t) {arrow}{p.change_pct:+.1f}%"
                )
        return "\n".join(lines)

    def _format_specialty(self, prices: list[PriceData]) -> str:
        by_cat: dict[str, list[PriceData]] = {}
        for p in prices:
            if p.is_reference:
                by_cat.setdefault(p.category, []).append(p)

        lines = []
        for cat in ["Aminosav", "Vitamin", "Mikroelem", "Adalek"]:
            items = by_cat.get(cat, [])
            if not items:
                for key in by_cat:
                    if cat[:5].lower() in key.lower():
                        items = by_cat[key]
                        break
            if not items:
                continue
            lines.append(f"\n-- {cat} --")
            for p in items:
                buy_flag = " [MOST KEDVEZO]" if p.buy_now else ""
                lines.append(
                    f"{p.emoji} {p.name}: {p.eur_kg:.2f} EUR/kg "
                    f"(sav: {p.eur_range} EUR/kg) | {p.trend}{buy_flag}"
                )
                if p.outlook:
                    lines.append(f"   -> {p.outlook}")
        return "\n".join(lines)

    def _format_buy_recs(self, prices: list[PriceData]) -> str:
        now_list = [p for p in prices if p.is_reference and p.buy_now]
        watch_list = [p for p in prices if p.is_reference and not p.buy_now
                      and "emelk" in p.trend.lower()]
        lines = []
        if now_list:
            lines.append("MOST ERDEMES VASAROLNI:")
            for p in now_list:
                lines.append(f"  {p.emoji} {p.name}: {p.eur_kg:.2f} EUR/kg ({p.eur_range} EUR/kg)")
                lines.append(f"     {p.buy_strategy}")
        if watch_list:
            lines.append("\nFIGYELJ – AREMELKEDES VARHATO:")
            for p in watch_list[:4]:
                lines.append(f"  {p.emoji} {p.name}: {p.eur_kg:.2f} EUR/kg")
                lines.append(f"     {p.outlook}")
        return "\n".join(lines)

    def _format_news(self, news: list[NewsItem]) -> str:
        if not news:
            return "Nincs relevans friss hir."
        return "\n".join(f"[{i.source}] {i.title}" for i in news[:10])

    async def create_morning_summary(self, changes: dict, news: list[NewsItem]) -> str:
        await self.refresh_rates()
        traded = self._format_traded(changes)
        specialty = self._format_specialty(changes["all"])
        buy_recs = self._format_buy_recs(changes["all"])
        news_txt = self._format_news(news)
        q = CURRENT_QUARTER
        date_str = datetime.now().strftime("%Y. %m. %d.")

        p1 = await self._ask_groq(f"""Helyes magyar helyesirassal irj!
Mezogazdasagi es takarmanyipari elemzo vagy. Magyar termeloknek, takarmanygyartoknak irsz.

MAI TOZSDEI ARAK (vilagpiaci ar USD/t, magyar ar HUF/t):
{traded}

FRISS HIREK:
{news_txt}

Irj tomor PIACI OSSZEFOGLALOT magyarul (max 200 szo):
1. Legfontosabb arvaltozasok – emlitsd az USD es HUF arakat is
2. Hirek ertelelese – rovid tavu hatasa az alapanyag arakra
3. Fo kockazatok es lehetosegek ma

Telegram formatumu szoveg, rovid bekezdesek.
Kezdd: Reggeli piaci osszefoglalo – {date_str}""", max_tokens=600)

        p2 = await self._ask_groq(f"""Helyes magyar helyesirassal irj!
Tapasztalt takarmanyipari alapanyag-beszerzo tanacsado vagy.
Az arak EUR/kg-ban vannak megadva (CIF Magyarorszag, 2026 {q}).

VEGYIPARI ALAPANYAGOK AKTUALIS ARAI:
{specialty}

VASARLASI JAVASLATOK:
{buy_recs}

Irj STRATEGIAI VASARLASI AJANLAST magyarul (max 220 szo):
1. {q}-ban: melyiknel kedvezo most az ar EUR/kg-ban? Miert?
2. Hol varhato aremelkedes? Mennyivel?
3. Top 3 konkret javaslat – minden mellol irj EUR/kg arszintet!

Telegram formatumu szoveg.
Kezdd: Strategiai vasarlasi ajanlat – {q}""", max_tokens=600)

        return f"{p1}\n\n{p2}"

    async def create_breaking_summary(self, news: list[NewsItem]) -> str:
        news_txt = "\n".join(f"[{i.source}] {i.title}\n  {i.summary[:200]}" for i in news)
        return await self._ask_groq(f"""Helyes magyar helyesirassal irj!
Takarmanyipari elemzokent irj rovid (max 180 szo) magyar RIASZTAST.

BREAKING HIREK:
{news_txt}

Mi tortent? Mely alapanyagokat erinti? Milyen ariranyt valoszinusit?
Mit tegyen most a beszerzo?

Kezdd: SURGOS PIACI RIASZTAS""", max_tokens=450)

    async def create_price_alert_summary(self, alerts: list[PriceData]) -> str:
        await self.refresh_rates()
        lines = [
            f"{p.emoji} {p.name}: {p.price:.1f} USD/t ({self._usd_to_huf(p.price):,} HUF/t) "
            f"({'emelkedett' if p.change_pct > 0 else 'csokkent'} {abs(p.change_pct):.1f}%-ot)"
            for p in alerts
        ]
        return await self._ask_groq(f"""Helyes magyar helyesirassal irj!
Irj rovid (max 150 szo) magyar ARRIASZTAST.

EXTREM MOZGASOK:
{chr(10).join(lines)}

Lehetseges okok, kapcsolodo hatas, rovid tavu kilatas.
Beszerzo ajanlat: most vegyen, varjon, fedezze magat?

Kezdd: EXTREM ARVALTOZAS ESZLELVE""", max_tokens=400)
