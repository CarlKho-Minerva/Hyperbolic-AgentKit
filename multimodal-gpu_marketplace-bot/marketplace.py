import aiohttp
from config import REGION_MAP


def format_memory(mb: int) -> str:
    if mb >= 1024 * 1024:
        return f"{mb / (1024 * 1024):.2f} TB"
    elif mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    else:
        return f"{mb} MB"

def format_price(amount_cents: int) -> str:
    if amount_cents < 100:
        return f"{amount_cents}¢/hr"
    else:
        return f"${amount_cents / 100:.2f}/hr"

def extract_instance_summary(instance: dict) -> dict:
    gpu = instance["hardware"]["gpus"][0]
    return {
        "gpu_model": gpu["model"],
        "gpu_memory": format_memory(gpu["ram"]),
        "price_per_hour": format_price(instance["pricing"]["price"]["amount"]),
        "location": REGION_MAP.get(instance["location"]["region"], instance["location"]["region"]),
        "available": not instance["reserved"] and instance["gpus_reserved"] < instance["gpus_total"],
    }

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
                        extract_instance_summary(instance)
                        for instance in marketplace_data["instances"]
                        if "gpus" in instance["hardware"] and instance["hardware"]["gpus"]
                    ]
                    await result_callback({"instances": available_instances})
                else:
                    await result_callback({"error": f"API request failed with status {response.status}"})
        except Exception as e:
            await result_callback({"error": str(e)})
