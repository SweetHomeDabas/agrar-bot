"""
Mezőgazdasági alapanyagárak figyelése.
Adatforrás: Yahoo Finance (ingyenes, API kulcs nélkül)
Figyelt termékek: búza, kukorica, szójabab, napraforgóolaj, repce, cukor
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import httpx

log = logging.getLogger(__name__)

# Yahoo Finance ticker szimbólumok
COMMODITIES = {
    "búza":         {"ticker": "ZW=F",  "unit": "cent/bushel", "emoji": "🌾"},
    "kukorica":     {"ticker": "ZC=F",  "unit": "cent/bushel", "emoji": "🌽"},
    "szójabab":     {"ticker": "ZS=F",  "unit": "cent/bushel", "emoji": "🫘"},
    "napraforgóolaj":{"ticker": "SUNO.MI","unit": "EUR/t",      "emoji": "🌻"},
    "repce":        {"ticker": "XRB=F", "unit": "EUR/t",       "emoji": "🟡"},
    "cukor":        {"ticker": "SB=F",  "unit": "cent/lb",     "emoji": "🍬"},
    "nyersolaj":    {"ticker": "CL=F",  "unit": "USD/hordó",   "emoji": "🛢️"},
}

# Riasztási küszöbök (%-os változás = azonnali riasztás)
ALERT_THRESHOLD_PCT = 3.0   # napi változásra
EXTREME_THRESHOLD_PCT = 5.0  # extrém riasztás


@dataclass
class PriceData:
    name: str
    ticker: str
    price: float
    prev_close: float
    change_pct: float
    unit: str
    emoji: str
    timestamp: datetime


class PriceMonitor:
    def __init__(self):
        self._previous_prices: dict[str, float] = {}

    async def get_price(self, name: str, info: dict) -> Optional[PriceData]:
        """Egy termék aktuális árának lekérdezése Yahoo Finance-ről."""
        ticker = info["ticker"]
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {"range": "2d", "interval": "1d"}
        headers = {"User-Agent": "Mozilla/5.0"}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, params=params, headers=headers)
                r.raise_for_status()
                data = r.json()

            result = data["chart"]["result"][0]
            closes = result["indicators"]["quote"][0]["close"]
            closes = [c for c in closes if c is not None]

            if len(closes) < 2:
                return None

            price = closes[-1]
            prev = closes[-2]
            change_pct = ((price - prev) / prev) * 100

            return PriceData(
                name=name,
                ticker=ticker,
                price=price,
                prev_close=prev,
                change_pct=change_pct,
                unit=info["unit"],
                emoji=info["emoji"],
                timestamp=datetime.now()
            )

        except Exception as e:
            log.warning(f"Nem sikerült lekérdezni {name} ({ticker}): {e}")
            return None

    async def get_all_prices(self) -> list[PriceData]:
        """Minden áru lekérdezése párhuzamosan."""
        tasks = [
            self.get_price(name, info)
            for name, info in COMMODITIES.items()
        ]
        results = await asyncio.gather(*tasks)
        prices = [p for p in results if p is not None]

        # Eltároljuk az aktuális árakat a folyamatos figyeléshez
        for p in prices:
            self._previous_prices[p.name] = p.price

        return prices

    def calculate_changes(self, prices: list[PriceData]) -> dict:
        """Kategorizálja az árváltozásokat (növekedés/csökkenés/stabil)."""
        up, down, stable = [], [], []
        for p in prices:
            if p.change_pct >= ALERT_THRESHOLD_PCT:
                up.append(p)
            elif p.change_pct <= -ALERT_THRESHOLD_PCT:
                down.append(p)
            else:
                stable.append(p)
        return {"up": up, "down": down, "stable": stable, "all": prices}

    def detect_extreme_changes(self, prices: list[PriceData]) -> list[PriceData]:
        """Azonnali riasztást igénylő extrém árváltozások szűrése."""
        return [
            p for p in prices
            if abs(p.change_pct) >= EXTREME_THRESHOLD_PCT
        ]
