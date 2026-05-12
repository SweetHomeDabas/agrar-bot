"""
Mezőgazdasági hírek figyelése RSS feed-eken keresztül.
Forrás: Reuters, Agrárágazat, Google News, FAO
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import httpx
import feedparser

log = logging.getLogger(__name__)

# RSS feed URL-ek (ingyenes, API kulcs nélkül)
RSS_FEEDS = [
    {
        "name": "Reuters – Commodities",
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "keywords": ["wheat", "corn", "grain", "soy", "búza", "kukorica",
                     "agri", "crop", "harvest", "harvest", "food price"],
    },
    {
        "name": "Google News – agrárárak",
        "url": "https://news.google.com/rss/search?q=búza+kukorica+ár+mezőgazdaság&hl=hu&gl=HU&ceid=HU:hu",
        "keywords": [],  # már szűrt keresés
    },
    {
        "name": "Agrárágazat.hu",
        "url": "https://www.agraragazat.hu/rss",
        "keywords": [],
    },
    {
        "name": "FAO Food Price Index",
        "url": "https://www.fao.org/news/rss-feed/en/",
        "keywords": ["price", "food", "cereal", "crop", "grain"],
    },
]

# Kulcsszavak, amelyek azonnali (breaking) riasztást jeleznek
BREAKING_KEYWORDS = [
    "háború", "war", "drought", "aszály", "flood", "árvíz",
    "export ban", "exporttilalom", "rekord", "record high", "record low",
    "válság", "crisis", "shortage", "hiány", "spike", "collapse",
    "sanctions", "szankció", "embargo", "hurricane", "hurrikán",
    "frost", "fagy", "hőség", "heatwave"
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
        # Már elküldött cikkek hash-ei (duplikáció szűrés)
        self._sent_hashes: set[str] = set()

    def _item_hash(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _is_breaking(self, title: str, summary: str) -> bool:
        text = (title + " " + summary).lower()
        return any(kw.lower() in text for kw in BREAKING_KEYWORDS)

    def _parse_feed(self, feed_info: dict, raw) -> list[NewsItem]:
        items = []
        cutoff = datetime.now() - timedelta(hours=6)

        for entry in raw.entries[:20]:
            title = getattr(entry, "title", "")
            url = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "")[:500]

            # Dátum parse
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6])
                except Exception:
                    pass

            # Csak friss hírek
            if published and published < cutoff:
                continue

            # Kulcsszó szűrés (ha van megadva)
            kws = feed_info.get("keywords", [])
            if kws:
                text = (title + " " + summary).lower()
                if not any(k.lower() in text for k in kws):
                    continue

            items.append(NewsItem(
                title=title,
                url=url,
                source=feed_info["name"],
                published=published,
                summary=summary,
                is_breaking=self._is_breaking(title, summary)
            ))

        return items

    async def _fetch_feed(self, feed_info: dict) -> list[NewsItem]:
        try:
            async with httpx.AsyncClient(timeout=15,
                                          headers={"User-Agent": "Mozilla/5.0"}) as client:
                r = await client.get(feed_info["url"])
                r.raise_for_status()
                raw = feedparser.parse(r.text)
            return self._parse_feed(feed_info, raw)
        except Exception as e:
            log.warning(f"RSS hiba ({feed_info['name']}): {e}")
            return []

    async def get_latest_news(self) -> list[NewsItem]:
        """Összes friss hír lekérdezése (reggeli riporthoz)."""
        all_items: list[NewsItem] = []
        for feed in RSS_FEEDS:
            items = await self._fetch_feed(feed)
            all_items.extend(items)

        # Deduplikálás URL alapján
        seen = set()
        unique = []
        for item in all_items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)

        return unique[:15]  # Max 15 hír a riporthoz

    async def get_breaking_news(self) -> list[NewsItem]:
        """Csak a breaking (sürgős) hírek, amelyeket még nem küldtünk el."""
        all_items = await self.get_latest_news()
        breaking = []
        for item in all_items:
            h = self._item_hash(item.url)
            if item.is_breaking and h not in self._sent_hashes:
                self._sent_hashes.add(h)
                breaking.append(item)

        # Hash készlet takarítása (max 1000 elem)
        if len(self._sent_hashes) > 1000:
            self._sent_hashes = set(list(self._sent_hashes)[-500:])

        return breaking
