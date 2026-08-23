"""The tool registry: every tool the LLM is allowed to call must be listed here. This doubles
as the allowlist — get_tool() returning None for an unrecognized name is how an unknown/rogue
tool request gets rejected, and TOOL_DECLARATIONS (what's actually shown to the LLM) is built
from exactly this same list, so a tool can never be *callable* without also being *offered*."""

from app.services.tools.add_food_to_catalog import ADD_FOOD_TO_CATALOG
from app.services.tools.base import ToolSpec
from app.services.tools.get_day_totals import GET_DAY_TOTALS
from app.services.tools.log_food_entry import LOG_FOOD_ENTRY
from app.services.tools.search_food import SEARCH_FOOD

TOOL_REGISTRY: dict[str, ToolSpec] = {
    tool.name: tool for tool in [SEARCH_FOOD, ADD_FOOD_TO_CATALOG, LOG_FOOD_ENTRY, GET_DAY_TOTALS]
}

TOOL_DECLARATIONS: list[dict] = [
    {"name": tool.name, "description": tool.description, "parameters": tool.parameters}
    for tool in TOOL_REGISTRY.values()
]


def get_tool(name: str) -> ToolSpec | None:
    return TOOL_REGISTRY.get(name)
