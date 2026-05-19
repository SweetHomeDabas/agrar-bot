"""
Valutaárfolyam lekérdezés Yahoo Finance-ről (real-time)
"""

import logging
import httpx

log = logging.getLogger(__name__)

# Fallback árfolyamok ha a lekérdezés nem sikerül
FALLBACK_RATES = {
    "USD_HUF": 360.0,
    "USD_EUR": 0.92,
}


async def get_exchange_rates() -> dict:
    """USD/HUF és USD/EUR árfolyam lekérdezése."""
    rates = dict(FALLBACK_RATES)
    pairs = {
        "USD_HUF": "USDHUF=X",
        "USD_EUR": "USDEUR=X",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for key, ticker in pairs.items():
                try:
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                    r = await client.get(url, params={"range": "1d", "interval": "1d"},
                                         headers={"User-Agent": "Mozilla/5.0"})
                    r.raise_for_status()
                    data = r.json()
                    closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
                    closes = [c for c in closes if c is not None]
                    if closes:
                        rates[key] = closes[-1]
                        log.info(f"{key}: {rates[key]:.4f}")
                except Exception as e:
                    log.warning(f"Arfolyam lekerdezesi hiba ({key}): {e}")
    except Exception as e:
        log.warning(f"Altalanos arfolyam hiba: {e}")
    return rates
