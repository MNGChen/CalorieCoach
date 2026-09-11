"""CalorieCoach read-only Nutrition MCP Server.

Run locally with:
    python mcp_server/nutrition_server.py
"""
from __future__ import annotations

from mcp.server import MCPServer

from services.nutrition_mcp_tools import NutritionCatalogTools

mcp = MCPServer(
    "CalorieCoach Nutrition",
    instructions=("Read-only access to CalorieCoach's shared local food catalogue. "
                  "Never use these tools to access or modify personal food logs, profiles, or weight records."),
)
tools = NutritionCatalogTools()


@mcp.tool()
def search_local_food(query: str) -> dict:
    """Find the best local food-catalogue match and its typical-serving nutrition."""
    return tools.search_local_food(query)


@mcp.tool()
def lookup_food_nutrition(query: str, quantity: float | None = None, unit: str | None = None) -> dict:
    """Match a food name and return its nutrition; use grams to scale a measured portion."""
    return tools.lookup_food_nutrition(query, quantity, unit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
