"""
Mezőgazdasági és vegyipari alapanyagárak figyelése.
Adatforrás: Yahoo Finance + referencia árak
Egység: USD/tonna (ahol lehetséges)
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import httpx

log = logging.getLogger(__name__)

COMMODITIES = {
    # --- GABONÁK ---
    "búza": {
        "ticker": "ZW=F", "unit": "USD/t", "emoji": "🌾",
        "convert": lambda p: (p / 100) * 36.744, "category": "Gabona"
    },
    "kukorica": {
        "ticker": "ZC=F", "unit": "USD/t", "emoji": "🌽",
        "convert": lambda p: (p / 100) * 39.368, "category": "Gabona"
    },
    "szójabab": {
        "ticker": "ZS=F", "unit": "USD/t", "emoji": "🫘",
        "convert": lambda p: (p / 100) * 36.744, "category": "Gabona"
    },
    "árpa": {
        "ticker": "ZW=F", "unit": "USD/t", "emoji": "🌿",
        "convert": lambda p: (p / 100) * 36.744 * 0.90, "category": "Gabona"
    },
    "tritikálé": {
        "ticker": "ZW=F", "unit": "USD/t", "emoji": "🌱",
        "convert": lambda p: (p / 100) * 36.744 * 0.92, "category": "Gabona"
    },
    "rozs": {
        "ticker": "ZW=F", "unit": "USD/t", "emoji": "🍞",
        "convert": lambda p: (p / 100) * 36.744 * 0.88, "category": "Gabona"
    },
    # --- OLAJNÖVÉNYEK ---
    "szójaolaj": {
        "ticker": "ZL=F", "unit": "USD/t", "emoji": "🫙",
        "convert": lambda p: (p / 100) * 2204.62, "category": "Olajnövény"
    },
    "pálmaolaj": {
        "ticker": "FCPO.KL", "unit": "USD/t", "emoji": "🌴",
        "convert": lambda p: p * 0.21, "category": "Olajnövény"
    },
    "repceolaj": {
        "ticker": "RS=F", "unit": "USD/t", "emoji": "🟡",
        "convert": lambda p: p * 0.74, "category": "Olajnövény"
    },
    "napraforgóolaj": {
        "ticker": "ZL=F", "unit": "USD/t", "emoji": "🌻",
        "convert": lambda p: (p / 100) * 2204.62 * 1.05, "category": "Olajnövény"
    },
    "lenolaj": {
        "ticker": "ZL=F", "unit": "USD/t", "emoji": "🔵",
        "convert": lambda p: (p / 100) * 2204.62 * 1.15, "category": "Olajnövény"
    },
    # --- ENERGIA ---
    "nyersolaj": {
        "ticker": "CL=F", "unit": "USD/hordó", "emoji": "🛢️",
        "convert": lambda p: p, "category": "Energia"
    },
    "földgáz": {
        "ticker": "NG=F", "unit": "USD/MMBtu", "emoji": "🔥",
        "convert": lambda p: p, "category": "Energia"
    },
    # --- EGYÉB ---
    "cukor": {
        "ticker": "SB=F", "unit": "USD/t", "emoji": "🍬",
        "convert": lambda p: (p / 100) * 2204.62, "category": "Egyéb"
    },
    # --- VEGYIPARI / TAKARMÁNY (referencia árak, nincs tőzsdei ticker) ---
    "lizin": {
        "ticker": None, "unit": "USD/t", "emoji": "🧪",
        "ref_price": 1450.0, "category": "Vegyipari"
    },
    "metionin": {
        "ticker": None, "unit": "USD/t", "emoji": "⚗️",
        "ref_price": 2800.0, "category": "Vegyipari"
    },
    "e-vitamin": {
        "ticker": None, "unit": "USD/t", "emoji": "💊",
        "ref_price": 9500.0, "category": "Vegyipari"
    },
    "ca-szappan": {
        "ticker": None, "unit": "USD/t", "emoji": "🧼",
        "ref_price": 1200.0, "category": "Vegyipari"
    },
}

ALERT_THRESHOLD_PCT = 3.0
EXTREME_THRESHOLD_PCT = 5.0


@dataclass
class PriceData:
    name: str
    ticker: Optional[str]
    price: float
    prev_close: float
    change_pct: float
    unit: str
    emoji: str
    category: str
    timestamp: datetime
    is_reference: bool = False


class PriceMonitor:
    def __init__(self):
        self._previous_prices: dict[str, float] = {}
        self._alert_sent_today: set[str] = set()
        self._last_alert_reset: datetime = datetime.now()

    def _reset_daily_alerts(self):
        now = datetime.now()
        if now.date() > self._last_alert_reset.date():
            self._alert_sent_today.clear()
            self._last_alert_reset = now

    async def get_price(self, name: str, info: dict) -> Optional[PriceData]:
        if info.get("ticker") is None:
            ref = info["ref_price"]
            return PriceData(
                name=name, ticker=None, price=ref, prev_close=ref,
                change_pct=0.0, unit=info["unit"], emoji=info["emoji"],
                category=info["category"], timestamp=datetime.now(),
                is_reference=True
            )

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

            convert = info.get("convert", lambda p: p)
            price = convert(closes[-1])
            prev = convert(closes[-2])
            change_pct = ((price - prev) / prev) * 100

            return PriceData(
                name=name, ticker=ticker, price=price, prev_close=prev,
                change_pct=change_pct, unit=info["unit"], emoji=info["emoji"],
                category=info["category"], timestamp=datetime.now()
            )
        except Exception as e:
            log.warning(f"Nem sikerült lekérdezni {name} ({ticker}): {e}")
            return None

    async def get_all_prices(self) -> list[PriceData]:
        tasks = [self.get_price(name, info) for name, info in COMMODITIES.items()]
        results = await asyncio.gather(*tasks)
        prices = [p for p in results if p is not None]
        for p in prices:
            if not p.is_reference:
                self._previous_prices[p.name] = p.price
        return prices

    def calculate_changes(self, prices: list[PriceData]) -> dict:
        up, down, stable = [], [], []
        by_category: dict[str, list[PriceData]] = {}
        for p in prices:
            cat = p.category
            by_category.setdefault(cat, []).append(p)
            if p.is_reference:
                continue
            if p.change_pct >= ALERT_THRESHOLD_PCT:
                up.append(p)
            elif p.change_pct <= -ALERT_THRESHOLD_PCT:
                down.append(p)
            else:
                stable.append(p)
        return {"up": up, "down": down, "stable": stable, "all": prices, "by_category": by_category}

    def detect_extreme_changes(self, prices: list[PriceData]) -> list[PriceData]:
        self._reset_daily_alerts()
        alerts = []
        for p in prices:
            if p.is_reference:
                continue
            if abs(p.change_pct) >= EXTREME_THRESHOLD_PCT:
                if p.name not in self._alert_sent_today and len(self._alert_sent_today) < 2:
                    alerts.append(p)
                    self._alert_sent_today.add(p.name)
        return alerts
