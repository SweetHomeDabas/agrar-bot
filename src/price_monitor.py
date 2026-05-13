"""
Mezőgazdasági, vegyipari és takarmány alapanyagárak figyelése.
Tőzsdei árak: Yahoo Finance (USD/tonna)
Vegyipari árak: referencia + hírfigyelés alapján
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import httpx

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# TŐZSDEI TERMÉKEK (Yahoo Finance, USD/tonna)
# ─────────────────────────────────────────────
TRADED_COMMODITIES = {
    # GABONÁK
    "búza":      {"ticker": "ZW=F", "emoji": "🌾", "category": "Gabona",
                  "convert": lambda p: (p/100)*36.744},
    "kukorica":  {"ticker": "ZC=F", "emoji": "🌽", "category": "Gabona",
                  "convert": lambda p: (p/100)*39.368},
    "szójabab":  {"ticker": "ZS=F", "emoji": "🫘", "category": "Gabona",
                  "convert": lambda p: (p/100)*36.744},
    "árpa":      {"ticker": "ZW=F", "emoji": "🌿", "category": "Gabona",
                  "convert": lambda p: (p/100)*36.744*0.90},
    "rozs":      {"ticker": "ZW=F", "emoji": "🍞", "category": "Gabona",
                  "convert": lambda p: (p/100)*36.744*0.88},
    # OLAJOK
    "szójaolaj":      {"ticker": "ZL=F", "emoji": "🫙", "category": "Olajnövény",
                       "convert": lambda p: (p/100)*2204.62},
    "pálmaolaj":      {"ticker": "FCPO.KL", "emoji": "🌴", "category": "Olajnövény",
                       "convert": lambda p: p*0.21},
    "repceolaj":      {"ticker": "RS=F", "emoji": "🟡", "category": "Olajnövény",
                       "convert": lambda p: p*0.74},
    "napraforgóolaj": {"ticker": "ZL=F", "emoji": "🌻", "category": "Olajnövény",
                       "convert": lambda p: (p/100)*2204.62*1.05},
    # ENERGIA
    "nyersolaj": {"ticker": "CL=F", "emoji": "🛢️", "category": "Energia",
                  "convert": lambda p: p},
    "földgáz":   {"ticker": "NG=F", "emoji": "🔥", "category": "Energia",
                  "convert": lambda p: p},
    # EGYÉB
    "cukor":     {"ticker": "SB=F", "emoji": "🍬", "category": "Egyéb",
                  "convert": lambda p: (p/100)*2204.62},
}

# ─────────────────────────────────────────────
# VEGYIPARI / TAKARMÁNY ALAPANYAGOK
# Referencia árak + szezonális trend + forrás
# Árak: EU import ár közelítés (USD/tonna)
# ─────────────────────────────────────────────
SPECIALTY_COMMODITIES = {

    # === AMINOSAVAK ===
    "L-Lizin HCl 98.5%": {
        "emoji": "🧪", "category": "Aminosav",
        "ref_price": 1450,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: CJ BIO (KR), Evonik (DE), Global Bio-chem (CN)",
        "buy_strategy": "Q1 vége / Q2 eleje szokott olcsóbb lenni (kínai újév utáni készlet)",
        "seasonal_trend": {"Q1": "stabil", "Q2": "csökkenő", "Q3": "emelkedő", "Q4": "csúcs"},
        "price_drivers": ["kukorica ár", "kínai energia költség", "USD/CNY árfolyam"],
        "search_keywords": ["lysine price", "L-lysine HCl market", "CJ BIO lysine"],
    },
    "DL-Metionin 99%": {
        "emoji": "⚗️", "category": "Aminosav",
        "ref_price": 2800,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: Evonik (DE), Adisseo (FR/CN), Sumitomo (JP), Novus (US)",
        "buy_strategy": "Q2-Q3 kedvezőbb, Q4 előtt érdemes készletet építeni",
        "seasonal_trend": {"Q1": "stabil", "Q2": "enyhén csökkenő", "Q3": "stabil", "Q4": "emelkedő"},
        "price_drivers": ["propilén ár", "energia költség", "EU kereslet"],
        "search_keywords": ["methionine price", "DL-methionine market", "Evonik methionine"],
    },
    "L-Treonin 98.5%": {
        "emoji": "🔬", "category": "Aminosav",
        "ref_price": 1200,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: CJ BIO (KR), Meihua (CN), Fufeng (CN)",
        "buy_strategy": "Kínai gyártók dominálják, Q1-Q2 szokott kedvező lenni",
        "seasonal_trend": {"Q1": "csökkenő", "Q2": "stabil", "Q3": "emelkedő", "Q4": "stabil"},
        "price_drivers": ["kukorica ár", "kínai export kvóta", "USD/CNY"],
        "search_keywords": ["threonine price", "L-threonine market"],
    },
    "L-Triptofán 98%": {
        "emoji": "💉", "category": "Aminosav",
        "ref_price": 8500,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: CJ BIO (KR), Ajinomoto (JP), Meihua (CN)",
        "buy_strategy": "Magas ár, kisebb mennyiség — forward árazás ajánlott",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "emelkedő", "Q4": "csúcs"},
        "price_drivers": ["fermentációs kapacitás", "kereslet baromfi szektorból"],
        "search_keywords": ["tryptophan price", "L-tryptophan feed grade"],
    },
    "L-Valin 98%": {
        "emoji": "🧫", "category": "Aminosav",
        "ref_price": 4200,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: CJ BIO (KR), Evonik (DE), Meihua (CN)",
        "buy_strategy": "Viszonylag stabil, spot vásárlás ajánlott kisebb mennyiségnél",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "emelkedő", "Q4": "stabil"},
        "price_drivers": ["kínai kapacitás bővülés", "sertés szektor kereslet"],
        "search_keywords": ["valine price", "L-valine feed grade market"],
    },

    # === VITAMINOK ===
    "A-vitamin 1000kIU": {
        "emoji": "🟠", "category": "Vitamin",
        "ref_price": 28000,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: DSM (NL), BASF (DE), Zhejiang NHU (CN)",
        "buy_strategy": "NHU dominál — gyári karbantartás idején (tipikusan Q2/Q4) ár ugrik",
        "seasonal_trend": {"Q1": "stabil", "Q2": "emelkedő", "Q3": "csökkenő", "Q4": "emelkedő"},
        "price_drivers": ["NHU gyárleállás", "citral ár", "kínai energia"],
        "search_keywords": ["vitamin A price", "retinyl acetate market", "NHU vitamin A"],
    },
    "D3-vitamin 500kIU": {
        "emoji": "☀️", "category": "Vitamin",
        "ref_price": 15000,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: DSM (NL), BASF (DE), Zhejiang NHU (CN), Fermenta (IN)",
        "buy_strategy": "Télen nagyobb a kereslet, nyáron érdemes készletet építeni",
        "seasonal_trend": {"Q1": "csúcs", "Q2": "csökkenő", "Q3": "alacsony", "Q4": "emelkedő"},
        "price_drivers": ["lanolin ár", "birkagyapjú supply", "szezonális kereslet"],
        "search_keywords": ["vitamin D3 price", "cholecalciferol market feed grade"],
    },
    "E-vitamin 50% por": {
        "emoji": "💊", "category": "Vitamin",
        "ref_price": 3800,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: DSM (NL), BASF (DE), Zhejiang NHU (CN), Adisseo (FR)",
        "buy_strategy": "NHU árkövető — kínai újév előtt érdemes vásárolni",
        "seasonal_trend": {"Q1": "emelkedő", "Q2": "stabil", "Q3": "csökkenő", "Q4": "stabil"},
        "price_drivers": ["izobutilén ár", "NHU kapacitás", "antioxidáns kereslet"],
        "search_keywords": ["vitamin E price", "tocopherol acetate market", "NHU vitamin E"],
    },
    "B1-vitamin (Tiamin)": {
        "emoji": "🟡", "category": "Vitamin",
        "ref_price": 12000,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: DSM (NL), Jiangxi Tianxin (CN), Brother Enterprises (CN)",
        "buy_strategy": "Kínai gyártók dominálnak, stabil ár — spot vásárlás megfelelő",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "stabil", "Q4": "stabil"},
        "price_drivers": ["kínai export", "fermentációs kapacitás"],
        "search_keywords": ["thiamine price", "vitamin B1 feed grade"],
    },
    "B2-vitamin (Riboflavin)": {
        "emoji": "🟠", "category": "Vitamin",
        "ref_price": 9500,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: DSM (NL), BASF (DE), Hubei Guangji (CN)",
        "buy_strategy": "Q2-Q3 kedvezőbb historikusan",
        "seasonal_trend": {"Q1": "stabil", "Q2": "csökkenő", "Q3": "stabil", "Q4": "emelkedő"},
        "price_drivers": ["fermentáció energia költség", "baromfi takarmány kereslet"],
        "search_keywords": ["riboflavin price", "vitamin B2 market feed"],
    },
    "B12-vitamin 1%": {
        "emoji": "🔴", "category": "Vitamin",
        "ref_price": 45000,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: DSM (NL), Sanofi (FR), Hebei Yufeng (CN)",
        "buy_strategy": "Magas értékű — forward szerződés ajánlott nagyobb mennyiségnél",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "emelkedő", "Q4": "csúcs"},
        "price_drivers": ["kobalt ár", "fermentáció kapacitás", "humán/állat kereslet verseny"],
        "search_keywords": ["vitamin B12 price", "cyanocobalamin market"],
    },
    "K3-vitamin (MSB)": {
        "emoji": "🟢", "category": "Vitamin",
        "ref_price": 7500,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: DSM (NL), Jilin Zhongxin (CN), Hubei Shengbaiao (CN)",
        "buy_strategy": "Stabil ár, spot vásárlás ajánlott",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "stabil", "Q4": "stabil"},
        "price_drivers": ["kínai kémiai alapanyag árak"],
        "search_keywords": ["vitamin K3 price", "menadione MSB market"],
    },

    # === MIKROELEMEK ===
    "Cink-oxid 72%": {
        "emoji": "⬜", "category": "Mikroelem",
        "ref_price": 2800,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: Umicore (BE), Zinc Nacional (MX), kínai gyártók",
        "buy_strategy": "Cink LME árhoz kötött — emelkedő trendnél érdemes előre vásárolni",
        "seasonal_trend": {"Q1": "stabil", "Q2": "emelkedő", "Q3": "stabil", "Q4": "csökkenő"},
        "price_drivers": ["LME cink ár", "kínai termelés", "EU rendeletek (ZnO tiltás)"],
        "search_keywords": ["zinc oxide price feed grade", "zinc sulfate market"],
    },
    "Mangán-oxid 60%": {
        "emoji": "🟤", "category": "Mikroelem",
        "ref_price": 950,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: kínai bányák, Vale (BR)",
        "buy_strategy": "Viszonylag stabil, éves szerződés ajánlott",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "stabil", "Q4": "stabil"},
        "price_drivers": ["kínai bányatermelés", "acélipar kereslet"],
        "search_keywords": ["manganese oxide price feed", "manganese sulfate market"],
    },
    "Réz-szulfát 25%": {
        "emoji": "🔵", "category": "Mikroelem",
        "ref_price": 1650,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: Codelco (CL), kínai gyártók",
        "buy_strategy": "LME réz árhoz kötött — figyelj a réz trendekre",
        "seasonal_trend": {"Q1": "emelkedő", "Q2": "csúcs", "Q3": "csökkenő", "Q4": "stabil"},
        "price_drivers": ["LME réz ár", "kínai ipar kereslet", "elektromos autó boom"],
        "search_keywords": ["copper sulfate price feed grade", "LME copper"],
    },
    "Szelén (Na-szelenát)": {
        "emoji": "🔶", "category": "Mikroelem",
        "ref_price": 65000,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: Umicore (BE), kínai finomítók",
        "buy_strategy": "Kis mennyiség, magas ár — éves szerződés ajánlott fix áron",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "emelkedő", "Q4": "stabil"},
        "price_drivers": ["réz finomítás melléktermék", "félvezető ipar kereslet"],
        "search_keywords": ["selenium price feed grade", "sodium selenite market"],
    },
    "Jód (KI / KIO3)": {
        "emoji": "🟣", "category": "Mikroelem",
        "ref_price": 35000,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: SQM (CL), Algorta Norte (CL), ACF (JP)",
        "buy_strategy": "Chilei termelés dominál — geopolitikai kockázat figyelendő",
        "seasonal_trend": {"Q1": "stabil", "Q2": "emelkedő", "Q3": "stabil", "Q4": "stabil"},
        "price_drivers": ["chilei bányatermelés", "gyógyszer ipar kereslet", "USD/CLP"],
        "search_keywords": ["iodine price potassium iodide", "iodine market 2025"],
    },
    "Vas-szulfát 30%": {
        "emoji": "🔩", "category": "Mikroelem",
        "ref_price": 280,
        "unit": "USD/t",
        "supplier_hint": "Sok EU és kínai gyártó — alacsony ár, könnyen elérhető",
        "buy_strategy": "Helyi/EU forrás ajánlott szállítási költség miatt",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "stabil", "Q4": "stabil"},
        "price_drivers": ["acélipar melléktermék", "szállítási költség"],
        "search_keywords": ["ferrous sulfate price feed grade"],
    },

    # === EGYÉB TAKARMÁNY-ADALÉKOK ===
    "Fitáz (10000 FTU/g)": {
        "emoji": "🦠", "category": "Adalék",
        "ref_price": 18000,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: DSM (NL), BASF (DE), Novozymes (DK), AB Vista (UK)",
        "buy_strategy": "Éves tender ajánlott nagy volumenre — jelentős árkülönbség gyártónként",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "stabil", "Q4": "emelkedő"},
        "price_drivers": ["búza/árpa ár (foszfor tartalom)", "EU foszfor szabályozás"],
        "search_keywords": ["phytase price feed enzyme", "DSM Ronozyme BASF Natuphos"],
    },
    "Betain (anhidrid 97%)": {
        "emoji": "🌊", "category": "Adalék",
        "ref_price": 1800,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: Danisco (DK), Agrana (AT), DuCoa (NL) — cukorrépából",
        "buy_strategy": "EU cukorrépa szezonhoz kötött — Q4/Q1 kedvezőbb",
        "seasonal_trend": {"Q1": "alacsony", "Q2": "emelkedő", "Q3": "stabil", "Q4": "csökkenő"},
        "price_drivers": ["cukorrépa feldolgozás", "EU cukor ár", "metionin ár (alternatíva)"],
        "search_keywords": ["betaine price feed grade", "betaine anhydrous market"],
    },
    "Kolin-klorid 60%": {
        "emoji": "🧂", "category": "Adalék",
        "ref_price": 650,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: Balchem (US), Jubilant (IN), kínai gyártók",
        "buy_strategy": "Stabil ár, spot vásárlás megfelelő — helyi EU raktárak elérhetők",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "emelkedő", "Q4": "stabil"},
        "price_drivers": ["trimetilamin ár", "baromfi takarmány kereslet"],
        "search_keywords": ["choline chloride price feed grade", "choline market 2025"],
    },
    "Ca-szappan (CSFA)": {
        "emoji": "🧼", "category": "Adalék",
        "ref_price": 1200,
        "unit": "USD/t",
        "supplier_hint": "Fő gyártók: Bergafat (DE), Megalac (UK), Balakrishna (IN)",
        "buy_strategy": "Pálmaolaj árhoz kötött — olaj csökkenésekor érdemes vásárolni",
        "seasonal_trend": {"Q1": "stabil", "Q2": "emelkedő", "Q3": "csúcs", "Q4": "csökkenő"},
        "price_drivers": ["pálmaolaj ár", "tejhaszon szarvasmarha kereslet"],
        "search_keywords": ["calcium soap fatty acids price", "bypass fat rumen protected"],
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
    supplier_hint: str = ""
    buy_strategy: str = ""
    seasonal_trend: dict = field(default_factory=dict)
    price_drivers: list = field(default_factory=list)


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

    async def get_traded_price(self, name: str, info: dict) -> Optional[PriceData]:
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
                change_pct=change_pct, unit="USD/t", emoji=info["emoji"],
                category=info["category"], timestamp=datetime.now()
            )
        except Exception as e:
            log.warning(f"Nem sikerült lekérdezni {name} ({ticker}): {e}")
            return None

    async def get_all_prices(self) -> list[PriceData]:
        # Tőzsdei árak párhuzamosan
        traded_tasks = [
            self.get_traded_price(name, info)
            for name, info in TRADED_COMMODITIES.items()
        ]
        traded_results = await asyncio.gather(*traded_tasks)
        prices = [p for p in traded_results if p is not None]

        # Vegyipari referencia árak
        for name, info in SPECIALTY_COMMODITIES.items():
            prices.append(PriceData(
                name=name,
                ticker=None,
                price=info["ref_price"],
                prev_close=info["ref_price"],
                change_pct=0.0,
                unit=info["unit"],
                emoji=info["emoji"],
                category=info["category"],
                timestamp=datetime.now(),
                is_reference=True,
                supplier_hint=info.get("supplier_hint", ""),
                buy_strategy=info.get("buy_strategy", ""),
                seasonal_trend=info.get("seasonal_trend", {}),
                price_drivers=info.get("price_drivers", []),
            ))

        for p in prices:
            if not p.is_reference:
                self._previous_prices[p.name] = p.price

        return prices

    def get_specialty_by_category(self, prices: list[PriceData]) -> dict:
        by_cat: dict[str, list[PriceData]] = {}
        for p in prices:
            if p.is_reference:
                by_cat.setdefault(p.category, []).append(p)
        return by_cat

    def calculate_changes(self, prices: list[PriceData]) -> dict:
        up, down, stable = [], [], []
        by_category: dict[str, list[PriceData]] = {}
        for p in prices:
            by_category.setdefault(p.category, []).append(p)
            if p.is_reference:
                continue
            if p.change_pct >= ALERT_THRESHOLD_PCT:
                up.append(p)
            elif p.change_pct <= -ALERT_THRESHOLD_PCT:
                down.append(p)
            else:
                stable.append(p)
        return {"up": up, "down": down, "stable": stable,
                "all": prices, "by_category": by_category}

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
