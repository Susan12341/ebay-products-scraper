import math
import re
from typing import Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _session(timeout: int = 20):
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.timeout = timeout
    return s

def fetch_html(url: str, headers=None, proxy: Optional[str] = None, timeout: int = 20) -> str:
    session = _session(timeout=timeout)
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = session.get(url, headers=headers or {}, proxies=proxies, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text

def safe_text(el) -> str:
    if not el:
        return ""
    # Some eBay titles contain placeholder text "New Listing" in a span; strip it
    text = el.get_text(" ", strip=True) if hasattr(el, "get_text") else str(el)
    text = re.sub(r"\bNew Listing\b", "", text, flags=re.I)
    return normalize_space(text)

def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def parse_price(s: str) -> Tuple[Optional[float], Optional[str]]:
    if not s:
        return None, None
    # Extract currency symbol or code and numeric part
    # Handles formats like "US $39.00", "$39.00", "EUR 12,34", "GBP 10.99"
    currency = None
    csym = re.findall(r"(US\s*\$|\$|€|£|AUD|\bUSD\b|\bEUR\b|\bGBP\b|\bCAD\b|\bINR\b)", s)
    if csym:
        currency = csym[0].strip()
    # Normalize decimal separators
    num = s
    num = num.replace(",", "")
    m = re.search(r"(\d+(?:\.\d{1,2})?)", num)
    if not m:
        return None, currency
    try:
        return float(m.group(1)), currency
    except Exception:
        return None, currency

def extract_number(s: str) -> Optional[int]:
    if not s:
        return None
    # Finds first integer in the string
    m = re.search(r"(\d{1,6})", s.replace(",", ""))
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None