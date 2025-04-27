import aiohttp
from loguru import logger

REGION_MAP = {
    "region-1": "US, North America",
    # Add more mappings as needed
}

def format_memory(mb):
    if mb >= 1024 * 1024:
        return f"{mb / (1024 * 1024):.2f} TB"
    elif mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    else:
        return f"{mb} MB"

async def fetch_marketplace_data(
    function_name, tool_call_id, args, llm, context, result_callback
):
    async with aiohttp.ClientSession() as session:
        try:
            url = "https://api.hyperbolic.xyz/v1/marketplace"
            headers = {"Content-Type": "application/json"}
            filters = {} if args["filter_type"] == "all" else {"available": True}
            data = {"filters": filters}

            async with session.post(url, json=data, headers=headers) as response:
                if response.status == 200:
                    marketplace_data = await response.json()
                    available_instances = [
                        {
                            "gpu_model": instance["hardware"]["gpus"][0]["model"],
                            "gpu_memory": format_memory(instance["hardware"]["gpus"][0]["ram"]),
                            "price_per_hour": f"${instance['pricing']['price']['amount'] / 100:.2f}",
                            "location": REGION_MAP.get(instance["location"]["region"], instance["location"]["region"]),
                            "available": not instance["reserved"]
                            and instance["gpus_reserved"] < instance["gpus_total"],
                        }
                        for instance in marketplace_data["instances"]
                        if "gpus" in instance["hardware"]
                        and instance["hardware"]["gpus"]
                    ]
                    await result_callback({"instances": available_instances})
                else:
                    await result_callback(
                        {"error": f"API request failed with status {response.status}"}
                    )
        except Exception as e:
            logger.error(f"Error fetching marketplace data: {e}")
            await result_callback({"error": str(e)})
