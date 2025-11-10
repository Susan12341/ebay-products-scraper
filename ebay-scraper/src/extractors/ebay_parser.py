import json
import math
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse, urljoin

import requests
from bs4 import BeautifulSoup

from .html_utils import (
    fetch_html,
    safe_text,
    parse_price,
    normalize_space,
    extract_number,
)
from .proxy_handler import ProxyManager

EBAY_DOMAINS = {
    "US": "https://www.ebay.com",
    "UK": "https://www.ebay.co.uk",
    "DE": "https://www.ebay.de",
    "AU": "https://www.ebay.com.au",
    "CA": "https://www.ebay.ca",
    "IN": "https://www.ebay.in",
    "FR": "https://www.ebay.fr",
    "IT": "https://www.ebay.it",
    "ES": "https://www.ebay.es",
    "NL": "https://www.benl.ebay.be",  # NL often uses ebay.nl redirecting to be
}

@dataclass
class Item:
    url: Optional[str] = None
    categories: Optional[List[str]] = None
    itemNumber: Optional[str] = None
    title: Optional[str] = None
    subTitle: Optional[str] = None
    whyToBuy: Optional[List[str]] = None
    price: Optional[float] = None
    priceWithCurrency: Optional[str] = None
    wasPrice: Optional[float] = None
    wasPriceWithCurrency: Optional[str] = None
    available: Optional[int] = None
    availableText: Optional[str] = None
    sold: Optional[int] = None
    image: Optional[str] = None
    seller: Optional[str] = None
    itemLocation: Optional[str] = None
    brand: Optional[str] = None
    ean: Optional[str] = None
    upc: Optional[str] = None
    mpn: Optional[str] = None
    type: Optional[str] = None

class EbayParser:
    def __init__(
        self,
        region: str = "US",
        max_items: int = 200,
        delay: float = 0.5,
        proxy_manager: Optional[ProxyManager] = None,
        user_agent: Optional[str] = None,
        timeout: int = 20,
        follow_item_page: bool = False,
    ) -> None:
        self.base = EBAY_DOMAINS.get(region.upper(), EBAY_DOMAINS["US"])
        self.max_items = max_items
        self.delay = delay
        self.proxy_manager = proxy_manager or ProxyManager()
        self.headers = {"User-Agent": user_agent} if user_agent else {}
        self.timeout = timeout
        self.follow_item_page = follow_item_page

    # ---------- Public API ----------

    def run(self, urls: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
        search_urls = list(urls or [])
        for kw in keywords or []:
            search_urls.append(self.keyword_to_url(kw))

        results: List[Item] = []
        for url in search_urls:
            for item in self.scrape_search(url):
                results.append(item)
                if len(results) >= self.max_items:
                    break
            if len(results) >= self.max_items:
                break

        return [asdict(x) for x in results]

    # ---------- URL Helpers ----------

    def keyword_to_url(self, keyword: str) -> str:
        q = {"_nkw": keyword}
        url = f"{self.base}/sch/i.html?{urlencode(q)}"
        return url

    def normalize_search_url(self, url: str) -> str:
        """
        Ensures pagination params are explicit and removes volatile tracking params.
        """
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        # _pgn = page number, _ipg = items per page
        if "_pgn" not in query:
            query["_pgn"] = ["1"]
        if "_ipg" not in query:
            query["_ipg"] = ["60"]
        # drop telemetry params
        for k in list(query.keys()):
            if k.lower().startswith("rt"):
                query.pop(k, None)
        new_q = urlencode({k: v[0] for k, v in query.items()})
        return urlunparse(parsed._replace(query=new_q))

    # ---------- Scrape Flow ----------

    def scrape_search(self, url: str) -> Iterable[Item]:
        url = self.normalize_search_url(url)
        total_collected = 0
        current_page = 1

        while True:
            page_url = self._set_page(url, current_page)
            html = fetch_html(
                page_url,
                headers=self.headers,
                proxy=self.proxy_manager.next() if self.proxy_manager else None,
                timeout=self.timeout,
            )
            soup = BeautifulSoup(html, "lxml")

            cards = self._select_result_cards(soup)
            if not cards:
                # Try alternate layout (sometimes ebay serves different DOMs)
                cards = soup.select("li.s-item")
            if not cards:
                break

            for card in cards:
                item = self._parse_card(card)
                if item and self.follow_item_page and item.url:
                    try:
                        self._enrich_from_item_page(item)
                        time.sleep(self.delay)
                    except Exception:
                        # ignore enrichment errors, keep baseline card data
                        pass

                if item:
                    yield item
                    total_collected += 1
                    if total_collected >= self.max_items:
                        return

            current_page += 1
            time.sleep(self.delay)

    # ---------- DOM Parsing ----------

    def _select_result_cards(self, soup: BeautifulSoup):
        # Common container for modern search results
        return soup.select("ul.srp-results li.s-item")

    def _parse_card(self, card) -> Optional[Item]:
        title_el = card.select_one("h3.s-item__title")
        if not title_el:
            # Sometimes title is in alt attr of image when sponsored
            title_el = card.select_one("img.s-item__image-img[alt]")
        title = safe_text(title_el)

        # URL
        url_el = card.select_one("a.s-item__link")
        url = url_el["href"].strip() if url_el and url_el.has_attr("href") else None

        # Price and was-price
        price_el = card.select_one(".s-item__price")
        price_text = safe_text(price_el)
        price_value, currency = parse_price(price_text)
        was_el = card.select_one(".s-item__dynamic .STRIKETHROUGH")
        if not was_el:
            was_el = card.select_one(".s-item__wasPrice")
        was_text = safe_text(was_el)
        was_value, was_currency = parse_price(was_text)

        # Availability / sold
        avail_text = safe_text(card.select_one(".s-item__availability, .s-item__quantity"))
        sold_text = safe_text(card.select_one(".s-item__hotness, .s-item__quantitySold"))
        available = extract_number(avail_text)
        sold = extract_number(sold_text)

        # Image
        img_el = card.select_one("img.s-item__image-img")
        image = img_el["src"].strip() if img_el and img_el.has_attr("src") else None
        if image and "gif" in image and img_el and img_el.has_attr("data-src"):
            image = img_el["data-src"].strip()

        # Seller/location (not always present in search results)
        seller = safe_text(card.select_one(".s-item__seller-info-text a"))
        location = safe_text(card.select_one(".s-item__location.s-item__itemLocation"))
        subtitle = safe_text(card.select_one(".s-item__subtitle"))
        badges = [normalize_space(x.get_text(" ", strip=True)) for x in card.select(".s-item__dynamic .s-item__freeReturns, .s-item__dynamic .s-item__shipping, .s-item__dynamic .s-item__hotness") if normalize_space(x.get_text(" ", strip=True))]

        # Item number (not in search results; attempt from data-view or link)
        item_number = None
        if url:
            m = re.search(r"/(\d{9,})\b", url)
            if m:
                item_number = m.group(1)

        price_with_currency = price_text if price_text else (f"{currency} {price_value}" if price_value and currency else None)
        was_with_currency = was_text if was_text else (f"{was_currency} {was_value}" if was_value and was_currency else None)

        item = Item(
            url=url,
            categories=None,  # can be filled on item page
            itemNumber=item_number,
            title=title or None,
            subTitle=subtitle or None,
            whyToBuy=badges or None,
            price=price_value,
            priceWithCurrency=price_with_currency,
            wasPrice=was_value,
            wasPriceWithCurrency=was_with_currency,
            available=available,
            availableText=avail_text or None,
            sold=sold,
            image=image,
            seller=seller or None,
            itemLocation=location or None,
        )
        return item

    def _enrich_from_item_page(self, item: Item) -> None:
        if not item.url:
            return
        html = fetch_html(
            item.url,
            headers=self.headers,
            proxy=self.proxy_manager.next() if self.proxy_manager else None,
            timeout=self.timeout,
        )
        soup = BeautifulSoup(html, "lxml")

        # Categories / breadcrumbs
        cats = [normalize_space(a.get_text(" ", strip=True)) for a in soup.select("#vi-VR-brumb-lnkLst a, nav.breadcrumbs a")]
        item.categories = cats or item.categories

        # Seller
        seller = safe_text(soup.select_one("#RightSummaryPanel .ux-seller-section__item--seller a, .x-about-this-seller__about-seller-info a"))
        item.seller = seller or item.seller

        # Item location
        loc = safe_text(soup.select_one("#itemLocation, .ux-layout-section__textual-display .ux-textspans"))
        if not loc:
            loc = safe_text(soup.find(string=re.compile("Item location", re.I)))
        item.itemLocation = loc or item.itemLocation

        # Specs table
        specs = {}
        for row in soup.select("#viTabs_0_pd, #vi-desc-maincntr, .itemAttr"):
            txt = row.get_text(" ", strip=True)
            if not txt:
                continue

        # Better: Key/Value from item specifics
        for li in soup.select("#vi-desc-maincntr #viTabs_0_is li, .ux-layout-section .ux-labels-values__labels, .ux-labels-values__values"):
            pass  # layout differs a lot; we extract from microdata below where possible

        # Microdata / meta tags
        brand = self._meta_content(soup, ["og:brand", "product:brand"])
        if not brand:
            brand = self._from_item_specifics(soup, ["Brand"])
        upc = self._from_item_specifics(soup, ["UPC"])
        ean = self._from_item_specifics(soup, ["EAN"])
        mpn = self._from_item_specifics(soup, ["MPN"])
        ptype = self._from_item_specifics(soup, ["Type", "Product Type"])

        item.brand = brand or item.brand
        item.upc = upc or item.upc
        item.ean = ean or item.ean
        item.mpn = mpn or item.mpn
        item.type = ptype or item.type

    # ---------- Utilities ----------

    def _meta_content(self, soup: BeautifulSoup, names: List[str]) -> Optional[str]:
        for n in names:
            el = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if el and el.get("content"):
                return normalize_space(el["content"])
        return None

    def _from_item_specifics(self, soup: BeautifulSoup, keys: List[str]) -> Optional[str]:
        # Try structured specifics tables
        for key in keys:
            # Modern layout
            label = soup.find(string=re.compile(rf"^{re.escape(key)}\b", re.I))
            if label:
                # parent may hold the value near-by
                val = None
                if hasattr(label, "parent"):
                    siblings = label.parent.find_next_siblings()
                    if siblings:
                        val = normalize_space(siblings[0].get_text(" ", strip=True))
                if not val:
                    # fallback: search value element by aria-label
                    el = soup.find(attrs={"aria-label": re.compile(key, re.I)})
                    val = normalize_space(el.get_text(" ", strip=True)) if el else None
                if val:
                    return val

        # Alternate specifics grid
        for row in soup.select("div.ux-layout-section-evo__row"):
            cells = [normalize_space(c.get_text(" ", strip=True)) for c in row.select(".ux-labels-values__labels, .ux-labels-values__values")]
            if len(cells) >= 2:
                for key in keys:
                    if re.search(rf"\b{re.escape(key)}\b", cells[0], re.I):
                        return cells[1]
        return None

    def _set_page(self, url: str, page: int) -> str:
        parsed = urlparse(url)
        q = parse_qs(parsed.query)
        q["_pgn"] = [str(page)]
        new_q = urlencode({k: v[0] for k, v in q.items()})
        return urlunparse(parsed._replace(query=new_q))