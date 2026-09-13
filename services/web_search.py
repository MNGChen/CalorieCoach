"""Replaceable web-search boundary for food nutrition fallback."""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import logging
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

import requests
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from config import OPENAI_API_KEY, OPENAI_MODEL, REQUEST_TIMEOUT_SECONDS
from services.source_identity import canonical_url, source_host

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    snippet: str
    url: str
    domain: str
    serving_size: str | None = None
    serving_quantity: float | None = None
    serving_unit: str | None = None
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    nutrition_extracted: bool = False


class WebSearchError(RuntimeError):
    """The selected web-search provider could not return results."""


class WebSearchProvider(Protocol):
    def search_food_web(self, food_name: str) -> list[WebSearchResult]: ...
    def search_web(self, query: str) -> list[WebSearchResult]: ...


def nutrition_search_query(food_name: str) -> str:
    return f"{food_name} nutrition calories protein carbs fat serving"


class _OpenAIWebResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    snippet: str = Field(min_length=1, max_length=1_200)
    url: str = Field(min_length=8, max_length=1_000)
    serving_size: str | None = None
    serving_quantity: float | None = Field(default=None, gt=0)
    serving_unit: str | None = None
    calories: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)


class _OpenAIWebResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[_OpenAIWebResult] = Field(min_length=1, max_length=5)


class OpenAIWebSearchProvider:
    """One low-context OpenAI web search, adapted to the existing evidence boundary."""

    instructions = """Search for nutrition evidence. When the web-search tool returns sources, return one to five
results. Each result URL must be one of the sources returned by the tool. Copy only source-supported title, snippet,
serving, calories, protein, carbs, and fat; leave a field null when the source does not state it. Do not estimate
nutrition or invent a source."""

    def __init__(self, client: OpenAI | None = None) -> None:
        self.client = client

    def search_food_web(self, food_name: str) -> list[WebSearchResult]:
        return self.search_web(nutrition_search_query(food_name))

    def search_web(self, query: str) -> list[WebSearchResult]:
        try:
            if self.client is None:
                if not OPENAI_API_KEY:
                    raise WebSearchError("OPENAI_API_KEY is not configured.")
                self.client = OpenAI(api_key=OPENAI_API_KEY, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=1)
            response = self.client.responses.parse(
                model=OPENAI_MODEL,
                instructions=self.instructions,
                input=query,
                tools=[{"type": "web_search", "search_context_size": "low"}],
                tool_choice="required",
                max_tool_calls=1,
                max_output_tokens=1_000,
                text_format=_OpenAIWebResults,
                include=["web_search_call.action.sources"],
                store=False,
            )
        except WebSearchError:
            raise
        except Exception as exc:
            raise WebSearchError("OpenAI web search is currently unavailable.") from exc

        source_urls = {
            canonical_url(source.url): source.url
            for item in getattr(response, "output", [])
            if getattr(item, "type", None) == "web_search_call"
            for source in (getattr(getattr(item, "action", None), "sources", None) or [])
            if getattr(source, "url", None)
        }
        parsed = getattr(response, "output_parsed", None)
        if parsed is None or not source_urls:
            raise WebSearchError("OpenAI web search returned no usable sources.")
        results = [
            WebSearchResult(item.title, item.snippet, source_urls[canonical_url(item.url)], source_host(item.url),
                            getattr(item, "serving_size", None), getattr(item, "serving_quantity", None),
                            getattr(item, "serving_unit", None), getattr(item, "calories", None),
                            getattr(item, "protein_g", None), getattr(item, "carbs_g", None),
                            getattr(item, "fat_g", None), True)
            for item in parsed.results if canonical_url(item.url) in source_urls
        ]
        if parsed.results and not results:
            raise WebSearchError("OpenAI web search returned unverified sources.")
        logger.info("OpenAI web search returned %s usable result(s).", len(results))
        return results


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
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def search_food_web(self, food_name: str) -> list[WebSearchResult]:
        return self.search_web(nutrition_search_query(food_name))

    def search_web(self, query: str) -> list[WebSearchResult]:
        try:
            response = requests.get(self.endpoint, params={"q": query},
                                    timeout=REQUEST_TIMEOUT_SECONDS,
                                    headers=self.headers)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise WebSearchError("Web search is currently unavailable.") from exc

        parser = _DuckDuckGoResultParser()
        parser.feed(response.text)
        results = [self._to_result(item) for item in parser.results]
        usable = [result for result in results if result is not None]
        if not usable and "anomaly-modal" in response.text:
            raise WebSearchError("DuckDuckGo is temporarily blocking automated searches.")
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
