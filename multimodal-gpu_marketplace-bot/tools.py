tools = [
    {
        "function_declarations": [
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
            }
        ]
    }
]
