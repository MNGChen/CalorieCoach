"""Replaceable web-search boundary for food nutrition fallback."""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import logging
from typing import Protocol
from urllib.parse import parse_qs, urlparse

import requests

from config import REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    snippet: str
    url: str
    domain: str


class WebSearchError(RuntimeError):
    """The selected web-search provider could not return results."""


class WebSearchProvider(Protocol):
    def search_food_web(self, food_name: str) -> list[WebSearchResult]: ...
    def search_web(self, query: str) -> list[WebSearchResult]: ...


def nutrition_search_query(food_name: str) -> str:
    return f"{food_name} nutrition calories protein carbs fat serving"


class _DuckDuckGoResultParser(HTMLParser):
    """Small parser for the stable title/snippet portions of DDG's HTML view."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._field: str | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = attributes.get("class", "") or ""
        if tag == "a" and "result__a" in classes:
            self.results.append({"title": "", "snippet": "", "url": attributes.get("href", "") or ""})
            self._field, self._depth = "title", 1
        elif tag in {"a", "div"} and "result__snippet" in classes and self.results:
            self._field, self._depth = "snippet", 1
        elif self._field:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._field:
            self._depth -= 1
            if self._depth == 0:
                self._field = None

    def handle_data(self, data: str) -> None:
        if self._field and self.results:
            self.results[-1][self._field] += data


class DuckDuckGoFoodSearchProvider:
    """No-key default provider. It can be replaced later without changing food logic."""

    endpoint = "https://html.duckduckgo.com/html/"
    max_results = 5

    def search_food_web(self, food_name: str) -> list[WebSearchResult]:
        return self.search_web(nutrition_search_query(food_name))

    def search_web(self, query: str) -> list[WebSearchResult]:
        try:
            response = requests.get(self.endpoint, params={"q": query},
                                    timeout=REQUEST_TIMEOUT_SECONDS,
                                    headers={"User-Agent": "CalorieCoach/1.0 public nutrition lookup"})
            response.raise_for_status()
        except requests.RequestException as exc:
            raise WebSearchError("Web search is currently unavailable.") from exc

        parser = _DuckDuckGoResultParser()
        parser.feed(response.text)
        results = [self._to_result(item) for item in parser.results]
        usable = [result for result in results if result is not None]
        ranked = sorted(usable, key=self._source_priority)
        logger.info("Web search returned %s usable result(s).", len(ranked))
        return ranked[:self.max_results]

    @staticmethod
    def _to_result(item: dict[str, str]) -> WebSearchResult | None:
        url = item["url"]
        parsed = urlparse(url)
        if parsed.netloc.endswith("duckduckgo.com"):
            url = parse_qs(parsed.query).get("uddg", [""])[0]
        domain = urlparse(url).netloc.lower()
        title, snippet = " ".join(item["title"].split()), " ".join(item["snippet"].split())
        return WebSearchResult(title, snippet, url, domain) if title and url and domain else None

    @staticmethod
    def _source_priority(result: WebSearchResult) -> tuple[int, str]:
        domain = result.domain
        if ".gov" in domain or domain.endswith("nhs.uk"):
            return (0, domain)
        if any(name in domain for name in ("nutrition", "fatsecret", "myfitnesspal", "usda")):
            return (1, domain)
        return (2, domain)
