"""Search official restaurant pages for menu-only suggestions without inventing nutrition."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from ai.openai_client import OpenAIStructuredChain
from ai.prompts import RESTAURANT_MENU_SEARCH_PROMPT
from services.web_search import DuckDuckGoFoodSearchProvider, WebSearchError, WebSearchProvider, WebSearchResult


class RestaurantMenuSearchError(RuntimeError):
    pass


class RestaurantMenuItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    source_url: str = Field(min_length=8, max_length=1000)
    reason: str = Field(min_length=1, max_length=220)


class RestaurantMenuSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[RestaurantMenuItem] = Field(default_factory=list, max_length=6)


class RestaurantMenuSearchService:
    """Official-domain menu discovery. Results are never written to the food catalogue."""
    RESTAURANT_DOMAINS = {"KFC": ("kfc.com.sg",), "McDonald's": ("mcdonalds.com.sg",)}

    def __init__(self, search: WebSearchProvider | None = None, chain: Any | None = None) -> None:
        self.search = search or DuckDuckGoFoodSearchProvider()
        self.chain = chain

    def search_menu(self, restaurant: str, request: str) -> dict[str, Any]:
        domains = self.RESTAURANT_DOMAINS.get(restaurant, ())
        if not domains:
            return self._empty(restaurant, "No official-domain search configuration is available.")
        try:
            results = self.search.search_web(f"{restaurant} Singapore official menu dinner")
        except WebSearchError:
            return self._empty(restaurant, "Official menu search is currently unavailable.")
        official = [result for result in results if self._is_official(result, domains)]
        if not official:
            return self._empty(restaurant, "No official menu pages were found.")
        try:
            extracted = self._extract(request, official)
        except RestaurantMenuSearchError:
            extracted = []
        allowed_urls = {result.url for result in official}
        items = [{"name": item.name, "reason": item.reason, "source_url": item.source_url,
                  "nutrition_status": "official_menu_only"}
                 for item in extracted if item.source_url in allowed_urls]
        return {"restaurant": restaurant, "available": bool(items), "items": items,
                "sources": [{"title": item.title, "url": item.url} for item in official],
                "reason": "Official menu options only; nutrition values have not been verified for these items." if items
                else "Official menu pages were found, but no relevant menu item could be safely extracted."}

    def _extract(self, request: str, sources: list[WebSearchResult]) -> list[RestaurantMenuItem]:
        try:
            chain = self.chain or OpenAIStructuredChain(RESTAURANT_MENU_SEARCH_PROMPT,
                                                        "Restaurant menu evidence:\n{context}", RestaurantMenuSchema)
            context = {"user_request": request, "sources": [
                {"title": source.title, "snippet": source.snippet, "url": source.url} for source in sources
            ]}
            data = chain.invoke({"context": json.dumps(context, ensure_ascii=False)})
            return (data if isinstance(data, RestaurantMenuSchema) else RestaurantMenuSchema.model_validate(data)).items
        except Exception as exc:
            raise RestaurantMenuSearchError("Official menu snippets could not be safely extracted.") from exc

    @staticmethod
    def _is_official(result: WebSearchResult, domains: tuple[str, ...]) -> bool:
        domain = urlparse(result.url).netloc.casefold().removeprefix("www.")
        return any(domain == allowed or domain.endswith("." + allowed) for allowed in domains)

    @staticmethod
    def _empty(restaurant: str, reason: str) -> dict[str, Any]:
        return {"restaurant": restaurant, "available": False, "items": [], "sources": [], "reason": reason}
