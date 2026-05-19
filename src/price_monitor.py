"""
Mezőgazdasági, vegyipari és takarmány alapanyagárak figyelése.
Tőzsdei árak: Yahoo Finance (USD/tonna és HUF/tonna)
Vegyipari árak: EUR/kg (piaci kutatás alapján, 2026 Q2, CIF Magyarország)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import httpx

log = logging.getLogger(__name__)

TRADED_COMMODITIES = {
    "búza":           {"ticker": "ZW=F",    "emoji": "🌾", "category": "Gabona",    "convert": lambda p: (p/100)*36.744},
    "kukorica":       {"ticker": "ZC=F",    "emoji": "🌽", "category": "Gabona",    "convert": lambda p: (p/100)*39.368},
    "szójabab":       {"ticker": "ZS=F",    "emoji": "🫘", "category": "Gabona",    "convert": lambda p: (p/100)*36.744},
    "árpa":           {"ticker": "ZW=F",    "emoji": "🌿", "category": "Gabona",    "convert": lambda p: (p/100)*36.744*0.90},
    "rozs":           {"ticker": "ZW=F",    "emoji": "🍞", "category": "Gabona",    "convert": lambda p: (p/100)*36.744*0.88},
    "szójaolaj":      {"ticker": "ZL=F",    "emoji": "🫙", "category": "Olajnövény","convert": lambda p: (p/100)*2204.62},
    "pálmaolaj":      {"ticker": "FCPO.KL", "emoji": "🌴", "category": "Olajnövény","convert": lambda p: p*0.21},
    "repceolaj":      {"ticker": "RS=F",    "emoji": "🟡", "category": "Olajnövény","convert": lambda p: p*0.74},
    "napraforgóolaj": {"ticker": "ZL=F",    "emoji": "🌻", "category": "Olajnövény","convert": lambda p: (p/100)*2204.62*1.05},
    "nyersolaj":      {"ticker": "CL=F",    "emoji": "🛢️", "category": "Energia",   "convert": lambda p: p},
    "földgáz":        {"ticker": "NG=F",    "emoji": "🔥", "category": "Energia",   "convert": lambda p: p},
    "cukor":          {"ticker": "SB=F",    "emoji": "🍬", "category": "Egyéb",     "convert": lambda p: (p/100)*2204.62},
}

# Vegyipari referencia árak – EUR/kg (CIF Magyarország, 2026 Q2)
# Forrás: Chemanalyst, Feedinfo, IMARC, Tradeasia, piaci adatok
SPECIALTY_COMMODITIES = {

    # === AMINOSAVAK ===
    "L-Lizin HCl 98.5%": {
        "emoji": "🧪", "category": "Aminosav",
        "eur_kg": 1.55,          # EU spot: 1.45–1.65 EUR/kg (Q2 2026, anti-dumping vám után stabilizálódott)
        "eur_range": "1.45–1.65",
        "trend": "stabil",
        "outlook": "Q1 2026-ban anti-dumping vámok emelték az árat, most stabilizálódott. Q3 enyhe emelkedés lehetséges.",
        "buy_now": False,
        "supplier_hint": "CJ BIO (KR), Evonik (DE), Meihua (CN), Ningxia Eppen (CN)",
        "buy_strategy": "Most stabil ár – spot vásárlás megfelelő. Q3 emelkedés előtt érdemes 6-8 heti készletet tartani.",
        "seasonal_trend": {"Q1": "emelkedő", "Q2": "stabil", "Q3": "enyhe emelkedés", "Q4": "stabil"},
        "price_drivers": ["kukorica ár", "anti-dumping vámok EU-ban", "kínai export"],
    },
    "DL-Metionin 99%": {
        "emoji": "⚗️", "category": "Aminosav",
        "eur_kg": 3.10,          # EU CIF: 2.90–3.30 EUR/kg (Q2 2026, ~3000 USD/t Németország)
        "eur_range": "2.90–3.30",
        "trend": "stabil",
        "outlook": "2026-ban 2,800–3,400 USD/t sávban stabil. Q3 enyhe emelkedés várható.",
        "buy_now": False,
        "supplier_hint": "Evonik (DE) – MetAMINO, Adisseo (FR) – Rhodimet, Novus (US) – ALIMET, NHU (CN)",
        "buy_strategy": "Q2 vége – Q3 közepe a legjobb időszak. Q4 előtt érdemes 2-3 havi készletet venni.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "enyhe emelkedés", "Q4": "csúcs"},
        "price_drivers": ["propilén ár", "energia EU", "takarmány kereslet Q4"],
    },
    "L-Treonin 98.5%": {
        "emoji": "🔬", "category": "Aminosav",
        "eur_kg": 1.15,          # EU CIF: 1.05–1.25 EUR/kg (Q2 2026)
        "eur_range": "1.05–1.25",
        "trend": "csökkenő",
        "outlook": "Kínai túlkínálat nyomja, most historikusan alacsony szinten. Q3 stabilizálódás várható.",
        "buy_now": True,
        "supplier_hint": "CJ BIO (KR), Meihua (CN), Fufeng (CN)",
        "buy_strategy": "MOST KEDVEZO – historikusan alacsony ár. 2-3 havi készlet felvétele ajánlott.",
        "seasonal_trend": {"Q1": "csökkenő", "Q2": "alacsony", "Q3": "stabil", "Q4": "enyhe emelkedés"},
        "price_drivers": ["kukorica ár", "kínai termelési kapacitás", "USD/CNY"],
    },
    "L-Triptofán 98%": {
        "emoji": "💉", "category": "Aminosav",
        "eur_kg": 7.80,          # EU CIF: 7.20–8.40 EUR/kg (Q2 2026)
        "eur_range": "7.20–8.40",
        "trend": "stabil",
        "outlook": "Stabil, Q3-Q4 emelkedés lehetséges szezonális kereslet miatt.",
        "buy_now": False,
        "supplier_hint": "CJ BIO (KR), Ajinomoto (JP), Meihua (CN)",
        "buy_strategy": "Forward árazás ajánlott nagyobb mennyiségnél. Q3 előtt érdemes biztosítani.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "emelkedő", "Q4": "csúcs"},
        "price_drivers": ["fermentációs kapacitás", "baromfi kereslet"],
    },
    "L-Valin 98%": {
        "emoji": "🧫", "category": "Aminosav",
        "eur_kg": 3.90,          # EU CIF: 3.60–4.20 EUR/kg (Q2 2026)
        "eur_range": "3.60–4.20",
        "trend": "stabil",
        "outlook": "Stabil, spot vásárlás megfelelő.",
        "buy_now": False,
        "supplier_hint": "CJ BIO (KR), Evonik (DE), Meihua (CN)",
        "buy_strategy": "Spot vásárlás megfelelő – stabil ár, nincs különleges sürgetés.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "enyhe emelkedés", "Q4": "stabil"},
        "price_drivers": ["kínai kapacitás", "sertés szektor kereslet"],
    },

    # === VITAMINOK ===
    "A-vitamin 1000 IU/g": {
        "emoji": "🟠", "category": "Vitamin",
        "eur_kg": 20.00,         # EU CIF: 17–23 EUR/kg (Q2 2026, NHU-függő)
        "eur_range": "17–23",
        "trend": "stabil",
        "outlook": "NHU gyárleállás esetén hirtelen +30-50% lehetséges! Q4 előtt emelkedés szokásos.",
        "buy_now": False,
        "supplier_hint": "Zhejiang NHU (CN) – piaci domináns, DSM-Firmenich (NL), BASF (DE)",
        "buy_strategy": "Q3 közepéig érdemes 3-4 havi készletet építeni. NHU hírek kritikusak!",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "emelkedő", "Q4": "csúcs"},
        "price_drivers": ["NHU gyárleállás", "citral ár", "kínai energia"],
    },
    "D3-vitamin 500 IU/g": {
        "emoji": "☀️", "category": "Vitamin",
        "eur_kg": 13.50,         # EU CIF: 11–16 EUR/kg (Q2 2026, nyáron alacsonyabb)
        "eur_range": "11–16",
        "trend": "csökkenő",
        "outlook": "Nyáron most a legolcsóbb. Q4-ben emelkedés biztos. Most érdemes venni!",
        "buy_now": True,
        "supplier_hint": "DSM-Firmenich (NL), BASF (DE), NHU (CN), Fermenta (IN)",
        "buy_strategy": "MOST KEDVEZO – nyáron mindig a legalacsonyabb. Q3 végéig vedd meg a téli szükségletet.",
        "seasonal_trend": {"Q1": "csúcs", "Q2": "csökkenő", "Q3": "alacsony", "Q4": "emelkedő"},
        "price_drivers": ["lanolin ár", "birkagyapjú supply", "szezonális kereslet télen"],
    },
    "E-vitamin 50% por": {
        "emoji": "💊", "category": "Vitamin",
        "eur_kg": 11.50,         # EU CIF: 10.5–12.5 EUR/kg (Q2 2026, a te adatod alapján ~11 EUR)
        "eur_range": "10.5–12.5",
        "trend": "stabil",
        "outlook": "Stabil Q2-Q3. NHU kapacitás határozza meg. Kínai újév előtt szokott emelkedni.",
        "buy_now": False,
        "supplier_hint": "Zhejiang NHU (CN) – domináns, DSM-Firmenich (NL), BASF (DE), Adisseo (FR)",
        "buy_strategy": "Jelenlegi ár reális. December előtt érdemes vásárolni a tavaszi szükségletre.",
        "seasonal_trend": {"Q1": "emelkedő", "Q2": "stabil", "Q3": "stabil", "Q4": "enyhe emelkedés"},
        "price_drivers": ["izobutilén ár", "NHU kapacitás", "kínai energia"],
    },
    "B1-vitamin (Tiamin)": {
        "emoji": "🟡", "category": "Vitamin",
        "eur_kg": 12.00,         # EU CIF: 10–14 EUR/kg (Q2 2026)
        "eur_range": "10–14",
        "trend": "stabil",
        "outlook": "Stabil, kínai gyártók dominálják a piacot.",
        "buy_now": False,
        "supplier_hint": "DSM-Firmenich (NL), Jiangxi Tianxin (CN), Brother Enterprises (CN)",
        "buy_strategy": "Spot vásárlás megfelelő – stabil ár.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "stabil", "Q4": "stabil"},
        "price_drivers": ["kínai export", "fermentációs kapacitás"],
    },
    "B2-vitamin (Riboflavin)": {
        "emoji": "🟠", "category": "Vitamin",
        "eur_kg": 9.50,          # EU CIF: 8.5–11 EUR/kg (Q2 2026)
        "eur_range": "8.5–11",
        "trend": "stabil",
        "outlook": "Q2-Q3 kedvezőbb historikusan. Q4 előtt érdemes beszerezni.",
        "buy_now": False,
        "supplier_hint": "DSM-Firmenich (NL), BASF (DE), Hubei Guangji (CN)",
        "buy_strategy": "Most megfelelő időszak. Q4 emelkedés szokásos.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "csökkenő", "Q3": "stabil", "Q4": "emelkedő"},
        "price_drivers": ["fermentáció energia", "baromfi takarmány kereslet"],
    },
    "B12-vitamin 1%": {
        "emoji": "🔴", "category": "Vitamin",
        "eur_kg": 43.00,         # EU CIF: 37–49 EUR/kg (Q2 2026)
        "eur_range": "37–49",
        "trend": "stabil",
        "outlook": "Stabil, Q3-Q4 enyhe emelkedés lehetséges. Éves szerződés ajánlott.",
        "buy_now": False,
        "supplier_hint": "DSM-Firmenich (NL), Hebei Yufeng (CN), Sanofi (FR)",
        "buy_strategy": "Éves fix áras szerződés ajánlott nagyobb mennyiségnél.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "emelkedő", "Q4": "csúcs"},
        "price_drivers": ["kobalt ár", "fermentáció kapacitás", "humán/állat kereslet verseny"],
    },
    "K3-vitamin (MSB)": {
        "emoji": "🟢", "category": "Vitamin",
        "eur_kg": 7.00,          # EU CIF: 6–8 EUR/kg (Q2 2026)
        "eur_range": "6–8",
        "trend": "stabil",
        "outlook": "Stabil, spot vásárlás megfelelő.",
        "buy_now": False,
        "supplier_hint": "DSM-Firmenich (NL), Jilin Zhongxin (CN), Hubei Shengbaiao (CN)",
        "buy_strategy": "Spot vásárlás megfelelő – stabil ár.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "stabil", "Q4": "stabil"},
        "price_drivers": ["kínai kémiai alapanyag árak"],
    },

    # === MIKROELEMEK ===
    "Cink-oxid 72%": {
        "emoji": "⬜", "category": "Mikroelem",
        "eur_kg": 2.60,          # EU CIF: 2.30–2.90 EUR/kg (Q2 2026)
        "eur_range": "2.30–2.90",
        "trend": "enyhén emelkedő",
        "outlook": "LME cink emelkedő trend. Q3-ban áremelkedés várható.",
        "buy_now": True,
        "supplier_hint": "Umicore (BE), EverZinc (BE), Zinc Nacional (MX)",
        "buy_strategy": "FIGYELJ – LME cink emelkedő. Most érdemes Q3 szükségletet biztosítani.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "emelkedő", "Q3": "csúcs", "Q4": "csökkenő"},
        "price_drivers": ["LME cink ár", "elektromos jármű kereslet", "kínai termelés"],
    },
    "Mangán-szulfát 32%": {
        "emoji": "🟤", "category": "Mikroelem",
        "eur_kg": 0.90,          # EU CIF: 0.75–1.05 EUR/kg (Q2 2026)
        "eur_range": "0.75–1.05",
        "trend": "stabil",
        "outlook": "Stabil, éves szerződés ajánlott.",
        "buy_now": False,
        "supplier_hint": "Kínai bányák dominálnak, Vale (BR)",
        "buy_strategy": "Éves szerződés ajánlott – stabil, kiszámítható ár.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "stabil", "Q4": "stabil"},
        "price_drivers": ["kínai bányatermelés", "acélipar kereslet"],
    },
    "Réz-szulfát 25%": {
        "emoji": "🔵", "category": "Mikroelem",
        "eur_kg": 1.55,          # EU CIF: 1.35–1.75 EUR/kg (Q2 2026)
        "eur_range": "1.35–1.75",
        "trend": "emelkedő",
        "outlook": "LME réz emelkedő trend. Q3 áremelkedés valószínű.",
        "buy_now": True,
        "supplier_hint": "Codelco (CL), Aurubis (DE), kínai finomítók",
        "buy_strategy": "FIGYELJ – LME réz emelkedő. Most érdemes beszerezni.",
        "seasonal_trend": {"Q1": "emelkedő", "Q2": "csúcs", "Q3": "csökkenő", "Q4": "stabil"},
        "price_drivers": ["LME réz ár", "elektromos autó kereslet", "kínai ipar"],
    },
    "Szelén (Na-szelenát 45%)": {
        "emoji": "🔶", "category": "Mikroelem",
        "eur_kg": 55.00,         # EU CIF: 48–62 EUR/kg (Q2 2026)
        "eur_range": "48–62",
        "trend": "stabil",
        "outlook": "Stabil. Félvezető ipar versenyez az ellátásért – kockázat.",
        "buy_now": False,
        "supplier_hint": "Umicore (BE), kínai réz finomítók melléktermék",
        "buy_strategy": "Éves fix áras szerződés ajánlott – kis mennyiség, nagy érték.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "enyhe emelkedés", "Q4": "stabil"},
        "price_drivers": ["réz finomítás melléktermék", "félvezető ipar kereslet"],
    },
    "Jód (KIO3 99%)": {
        "emoji": "🟣", "category": "Mikroelem",
        "eur_kg": 30.00,         # EU CIF: 26–34 EUR/kg (Q2 2026)
        "eur_range": "26–34",
        "trend": "stabil",
        "outlook": "Chilei termelés határozza meg – geopolitikai kockázat.",
        "buy_now": False,
        "supplier_hint": "SQM (CL), Algorta Norte (CL), ACF Minera (JP)",
        "buy_strategy": "Éves szerződés ajánlott – Chiléből való függőség kockázat.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "emelkedő", "Q3": "stabil", "Q4": "stabil"},
        "price_drivers": ["chilei bányatermelés", "gyógyszer ipar kereslet"],
    },
    "Vas-szulfát 30%": {
        "emoji": "🔩", "category": "Mikroelem",
        "eur_kg": 0.28,          # EU CIF: 0.23–0.33 EUR/kg (Q2 2026, helyi EU olcsóbb)
        "eur_range": "0.23–0.33",
        "trend": "stabil",
        "outlook": "Stabil – helyi EU forrás ajánlott szállítási költség miatt.",
        "buy_now": False,
        "supplier_hint": "Sok EU gyártó – helyi/regionális forrás ajánlott",
        "buy_strategy": "Helyi EU forrásból spot vásárlás – szállítási költség a döntő tényező.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "stabil", "Q4": "stabil"},
        "price_drivers": ["acélipar melléktermék", "szállítási költség"],
    },

    # === ADALÉKOK ===
    "Betain anhidrid 97%": {
        "emoji": "🌊", "category": "Adalék",
        "eur_kg": 1.75,          # EU CIF: 1.50–2.00 EUR/kg (Q2 2026)
        "eur_range": "1.50–2.00",
        "trend": "stabil",
        "outlook": "Q4/Q1 kedvezőbb (cukorrépa kampány szezon).",
        "buy_now": False,
        "supplier_hint": "Danisco/IFF (DK), Agrana (AT), DuCoa (NL) – EU cukorrépa alapú",
        "buy_strategy": "Q4/Q1 a legjobb áridőszak – cukorrépa feldolgozás után bőséges kínálat.",
        "seasonal_trend": {"Q1": "alacsony", "Q2": "emelkedő", "Q3": "stabil", "Q4": "csökkenő"},
        "price_drivers": ["cukorrépa feldolgozás", "EU cukor ár", "metionin ár (alternatíva)"],
    },
    "Kolin-klorid 60%": {
        "emoji": "🧂", "category": "Adalék",
        "eur_kg": 0.62,          # EU CIF: 0.52–0.72 EUR/kg (Q2 2026)
        "eur_range": "0.52–0.72",
        "trend": "stabil",
        "outlook": "Stabil. EU etilén-oxid szabályozás szűkíti a kínai importot – EU-konform forrás kötelező!",
        "buy_now": False,
        "supplier_hint": "Balchem (US), Jubilant (IN), BASF (DE) – EU etilén-oxid limit fontos!",
        "buy_strategy": "EU-konform forrás kötelező. Spot vásárlás megfelelő.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "stabil", "Q3": "enyhe emelkedés", "Q4": "stabil"},
        "price_drivers": ["metanol ár", "ammónia ár", "EU etilén-oxid szabályozás"],
    },
    "Ca-szappan (CSFA)": {
        "emoji": "🧼", "category": "Adalék",
        "eur_kg": 1.10,          # EU CIF: 0.95–1.25 EUR/kg (Q2 2026)
        "eur_range": "0.95–1.25",
        "trend": "stabil",
        "outlook": "Pálmaolaj árral együtt mozog.",
        "buy_now": False,
        "supplier_hint": "Bergafat/Evonik (DE), Megalac/Volac (UK), Balakrishna (IN)",
        "buy_strategy": "Pálmaolaj csökkenésekor érdemes vásárolni – most stabil.",
        "seasonal_trend": {"Q1": "stabil", "Q2": "emelkedő", "Q3": "csúcs", "Q4": "csökkenő"},
        "price_drivers": ["pálmaolaj ár", "tejhaszon szarvasmarha kereslet"],
    },
}

ALERT_THRESHOLD_PCT = 3.0
EXTREME_THRESHOLD_PCT = 5.0


@dataclass
class PriceData:
    name: str
    ticker: Optional[str]
    price: float          # USD/t tőzsdeieknél, EUR/kg vegyipariaknál
    prev_close: float
    change_pct: float
    unit: str
    emoji: str
    category: str
    timestamp: datetime
    is_reference: bool = False
    eur_kg: float = 0.0
    eur_range: str = ""
    trend: str = ""
    outlook: str = ""
    buy_now: bool = False
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
            log.warning(f"Nem sikerult lekerdezni {name} ({ticker}): {e}")
            return None

    async def get_all_prices(self) -> list[PriceData]:
        traded_tasks = [self.get_traded_price(n, i) for n, i in TRADED_COMMODITIES.items()]
        traded_results = await asyncio.gather(*traded_tasks)
        prices = [p for p in traded_results if p is not None]

        for name, info in SPECIALTY_COMMODITIES.items():
            prices.append(PriceData(
                name=name, ticker=None,
                price=info["eur_kg"],      # EUR/kg-ban tároljuk
                prev_close=info["eur_kg"],
                change_pct=0.0,
                unit="EUR/kg",
                emoji=info["emoji"],
                category=info["category"],
                timestamp=datetime.now(),
                is_reference=True,
                eur_kg=info["eur_kg"],
                eur_range=info.get("eur_range", ""),
                trend=info.get("trend", "stabil"),
                outlook=info.get("outlook", ""),
                buy_now=info.get("buy_now", False),
                supplier_hint=info.get("supplier_hint", ""),
                buy_strategy=info.get("buy_strategy", ""),
                seasonal_trend=info.get("seasonal_trend", {}),
                price_drivers=info.get("price_drivers", []),
            ))

        for p in prices:
            if not p.is_reference:
                self._previous_prices[p.name] = p.price
        return prices

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
