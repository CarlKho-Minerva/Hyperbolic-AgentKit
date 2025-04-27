from typing import Callable, Dict, Any, Awaitable
from marketplace import fetch_marketplace_data

# Tool metadata definitions
TOOL_DEFINITIONS = [
    {
        "name": "get_available_gpus",
        "description": "Get the list of available GPU instances in the marketplace",
        "parameters": {
            "type": "object",
            "properties": {
                "filter_type": {
                    "type": "string",
                    "enum": ["all", "available_only"],
                    "description": "Filter type for GPU instances",
                }
            },
            "required": ["filter_type"],
        },
    },
    # Add more tool definitions here as needed
]

# Tool registry: maps tool name to handler function
TOOL_REGISTRY: Dict[str, Callable[..., Awaitable[Any]]] = {
    "get_available_gpus": fetch_marketplace_data,
    # Add more tool handlers here as needed
}

def get_tool_declarations() -> list:
    """Return tool declarations in the format expected by the LLM service."""
    return [{"function_declarations": TOOL_DEFINITIONS}]


def register_all_tools(llm):
    """Register all tools in the registry with the LLM service."""
    for tool_name, handler in TOOL_REGISTRY.items():
        llm.register_function(tool_name, handler)
