from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from src.utils.io import ensure_dir
from src.utils.text import clean_string

LOGGER = logging.getLogger(__name__)
HLTV_BASE_URL = "https://www.hltv.org"


@dataclass
class HltvFetchResult:
    html: str | None
    html_path: Path | None
    fetched_from_cache: bool
    error: str | None = None


class HltvClient:
    def __init__(self, cache_dir: Path, *, cache_enabled: bool = True, rate_limit_seconds: int = 5) -> None:
        self.cache_dir = ensure_dir(cache_dir)
        self.cache_enabled = cache_enabled
        self.rate_limit_seconds = rate_limit_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "cs2-tactical-analytics/0.1 (+local research; conservative requests)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def fetch_match_page(self, match_url: str, match_id: str | None = None) -> HltvFetchResult:
        cache_path = self._cache_path(match_url, match_id)
        return self._fetch_page(match_url, cache_path)

    def fetch_results_page(
        self,
        team_id: int,
        date_start: date,
        date_end: date,
        *,
        map_codes: list[str] | None = None,
        offset: int = 0,
    ) -> HltvFetchResult:
        results_url = build_results_url(
            team_id,
            date_start,
            date_end,
            map_codes=map_codes,
            offset=offset,
        )
        maps_key = "-".join(sorted(map_codes or [])) or "all-maps"
        cache_path = self.cache_dir / (
            f"hltv_results_team_{team_id}_{date_start.isoformat()}_{date_end.isoformat()}_"
            f"{maps_key}_offset_{offset}.html"
        )
        return self._fetch_page(results_url, cache_path)

    def _fetch_page(self, url: str, cache_path: Path) -> HltvFetchResult:
        if self.cache_enabled and cache_path.exists():
            LOGGER.info("Using cached HLTV page: %s", cache_path)
            html = cache_path.read_text(encoding="utf-8")
            if is_security_challenge(html):
                return HltvFetchResult(None, cache_path, True, "cached page is an HLTV security challenge")
            return HltvFetchResult(html, cache_path, True)

        if self.rate_limit_seconds > 0:
            time.sleep(self.rate_limit_seconds)

        try:
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            LOGGER.warning("Failed to fetch HLTV page %s: %s", url, exc)
            return HltvFetchResult(None, cache_path, False, str(exc))

        html = response.text
        if is_security_challenge(html):
            error = "HLTV returned a security challenge; manual fallback is required"
            LOGGER.warning("%s for %s", error, url)
            return HltvFetchResult(None, cache_path, False, error)
        if self.cache_enabled:
            cache_path.write_text(html, encoding="utf-8")
        return HltvFetchResult(html, cache_path if self.cache_enabled else None, False)

    def _cache_path(self, match_url: str, match_id: str | None) -> Path:
        safe_id = clean_string(match_id) or extract_match_id(match_url) or hashlib.sha1(match_url.encode()).hexdigest()[:12]
        return self.cache_dir / f"hltv_match_{safe_id}.html"


def extract_match_id(match_url: str | None) -> str | None:
    if not match_url:
        return None
    match = re.search(r"/matches/(\d+)", str(match_url))
    return match.group(1) if match else None


def build_match_url(match_id: str | None) -> str | None:
    match_id = clean_string(match_id)
    if not match_id:
        return None
    return f"{HLTV_BASE_URL}/matches/{match_id}/match"


def build_results_url(
    team_id: int,
    date_start: date,
    date_end: date,
    *,
    map_codes: list[str] | None = None,
    offset: int = 0,
) -> str:
    params: list[tuple[str, object]] = [
        ("team", team_id),
        ("startDate", date_start.isoformat()),
        ("endDate", date_end.isoformat()),
    ]
    params.extend(("map", map_code) for map_code in map_codes or [])
    if offset:
        params.append(("offset", offset))
    return f"{HLTV_BASE_URL}/results?{urlencode(params)}"


def parse_results_page(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    matches: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for link in soup.select(".result-con a.a-reset[href^='/matches/']"):
        href = clean_string(link.get("href"))
        match_id = extract_match_id(href)
        if not href or not match_id or match_id in seen_ids:
            continue
        seen_ids.add(match_id)
        matches.append(
            {
                "hltv_match_id": match_id,
                "match_url": f"{HLTV_BASE_URL}{href}",
            }
        )
    return matches


def results_has_next_page(html: str, *, next_offset: int) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return soup.select_one(f"a[href*='offset={next_offset}']") is not None


def is_security_challenge(html: str) -> bool:
    lowered = html.lower()
    challenge_markers = (
        "cf-chl-",
        "executando verificação de segurança",
        "performing security verification",
        "just a moment",
    )
    return any(marker in lowered for marker in challenge_markers)


def parse_match_page(html: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    parsed: dict[str, object] = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    timestamp = soup.select_one(".timeAndEvent .date, .date[data-unix], [data-unix]")
    if timestamp and timestamp.get("data-unix"):
        try:
            parsed["match_date"] = datetime.fromtimestamp(int(timestamp["data-unix"]) / 1000, tz=timezone.utc).date().isoformat()
        except (TypeError, ValueError, OSError):
            pass

    event = soup.select_one(".timeAndEvent .event a, .event.text-ellipsis a, .event")
    if event:
        parsed["event_name"] = event.get_text(" ", strip=True)

    teams = [node.get_text(" ", strip=True) for node in soup.select(".teamName")]
    if len(teams) >= 2:
        parsed["team_1"] = teams[0]
        parsed["team_2"] = teams[1]

    demo_link = soup.find("a", href=re.compile(r"demo|download", re.I))
    if demo_link and demo_link.get("href"):
        href = demo_link["href"]
        parsed["demo_link"] = href if href.startswith("http") else f"{HLTV_BASE_URL}{href}"

    maps = []
    for holder in soup.select(".mapholder"):
        node = holder.select_one(".mapname")
        if node is None:
            continue
        scores = [score.get_text(" ", strip=True) for score in holder.select(".results-team-score")]
        if scores and all(score == "-" for score in scores):
            continue
        text = node.get_text(" ", strip=True)
        if text:
            maps.append(text)
    if not maps:
        for node in soup.select(".mapname"):
            text = node.get_text(" ", strip=True)
            if text:
                maps.append(text)
    if maps:
        parsed["maps"] = list(dict.fromkeys(maps))

    return parsed


def enrich_row_with_html(row: dict[str, object], parsed: dict[str, object], html_path: Path | None) -> dict[str, object]:
    enriched = dict(row)
    for key in ["match_date", "event_name", "team_1", "team_2", "demo_link"]:
        if not clean_string(enriched.get(key)) and clean_string(parsed.get(key)):
            enriched[key] = parsed[key]
    parsed_maps = parsed.get("maps")
    if not clean_string(enriched.get("map_name")) and isinstance(parsed_maps, list) and len(parsed_maps) == 1:
        enriched["map_name"] = parsed_maps[0]
    if not clean_string(enriched.get("map_number")) and isinstance(parsed_maps, list) and len(parsed_maps) == 1:
        enriched["map_number"] = "1"
    if clean_string(html_path):
        enriched["source_html_path"] = str(html_path)
    enriched["scraped_at"] = parsed.get("scraped_at")
    return enriched
