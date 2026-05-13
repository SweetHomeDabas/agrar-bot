"""
Mezőgazdasági és vegyipari hírek figyelése RSS feed-eken keresztül.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import httpx
import feedparser

log = logging.getLogger(__name__)

RSS_FEEDS = [
    {
        "name": "Google News – gabona/olaj árak",
        "url": "https://news.google.com/rss/search?q=búza+kukorica+szója+ár+mezőgazdaság&hl=hu&gl=HU&ceid=HU:hu",
        "keywords": [],
    },
    {
        "name": "Google News – vegyipari alapanyagok",
        "url": "https://news.google.com/rss/search?q=lizin+metionin+vitamins+feed+additives+price&hl=en&gl=US&ceid=US:en",
        "keywords": [],
    },
    {
        "name": "Google News – commodity prices",
        "url": "https://news.google.com/rss/search?q=commodity+prices+wheat+corn+soybean+palm+oil&hl=en&gl=US&ceid=US:en",
        "keywords": [],
    },
    {
        "name": "Google News – feed ingredients",
        "url": "https://news.google.com/rss/search?q=lysine+methionine+vitamin+E+calcium+soap+price+2025&hl=en&gl=US&ceid=US:en",
        "keywords": [],
    },
    {
        "name": "Agrárágazat.hu",
        "url": "https://agraragazat.hu/rss",
        "keywords": [],
    },
    {
        "name": "Agrárszakma.hu",
        "url": "https://news.google.com/rss/search?q=agrárpiac+takarmány+ár+site:agraragazat.hu&hl=hu&gl=HU&ceid=HU:hu",
        "keywords": [],
    },
]

BREAKING_KEYWORDS = [
    "háború", "war", "drought", "aszály", "flood", "árvíz",
    "export ban", "exporttilalom", "rekord", "record high", "record low",
    "válság", "crisis", "shortage", "hiány", "spike", "collapse",
    "sanctions", "szankció", "embargo", "hurricane", "hurrikán",
    "frost", "fagy", "hőség", "heatwave", "supply chain", "ellátási lánc",
    "factory shutdown", "gyárleállás", "contamination", "szennyezés",
    "outbreak", "járvány", "tariff", "vám", "quota", "kvóta",
]


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: Optional[datetime]
    summary: str
    is_breaking: bool


class NewsMonitor:
    def __init__(self):
        self._sent_hashes: set[str] = set()

    def _item_hash(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _is_breaking(self, title: str, summary: str) -> bool:
        text = (title + " " + summary).lower()
        return any(kw.lower() in text for kw in BREAKING_KEYWORDS)

    def _parse_feed(self, feed_info: dict, raw) -> list[NewsItem]:
        items = []
        cutoff = datetime.now() - timedelta(hours=12)

        for entry in raw.entries[:20]:
            title = getattr(entry, "title", "")
            url = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "")[:500]

            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6])
                except Exception:
                    pass

            if published and published < cutoff:
                continue

            kws = feed_info.get("keywords", [])
            if kws:
                text = (title + " " + summary).lower()
                if not any(k.lower() in text for k in kws):
                    continue

            items.append(NewsItem(
                title=title, url=url, source=feed_info["name"],
                published=published, summary=summary,
                is_breaking=self._is_breaking(title, summary)
            ))

        return items

    async def _fetch_feed(self, feed_info: dict) -> list[NewsItem]:
        try:
            async with httpx.AsyncClient(
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0"},
                follow_redirects=True
            ) as client:
                r = await client.get(feed_info["url"])
                r.raise_for_status()
                raw = feedparser.parse(r.text)
            return self._parse_feed(feed_info, raw)
        except Exception as e:
            log.warning(f"RSS hiba ({feed_info['name']}): {e}")
            return []

    async def get_latest_news(self) -> list[NewsItem]:
        all_items: list[NewsItem] = []
        for feed in RSS_FEEDS:
            items = await self._fetch_feed(feed)
            all_items.extend(items)

        seen = set()
        unique = []
        for item in all_items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)

        return unique[:20]

    async def get_breaking_news(self) -> list[NewsItem]:
        all_items = await self.get_latest_news()
        breaking = []
        for item in all_items:
            h = self._item_hash(item.url)
            if item.is_breaking and h not in self._sent_hashes:
                self._sent_hashes.add(h)
                breaking.append(item)

        if len(self._sent_hashes) > 1000:
            self._sent_hashes = set(list(self._sent_hashes)[-500:])

        return breaking
