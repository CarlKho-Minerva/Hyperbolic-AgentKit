from dotenv import dotenv_values
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.gemini_multimodal_live.gemini import GeminiMultimodalLiveLLMService
from marketplace import fetch_marketplace_data
from tools import tools

# Load all env variables from .env file
config = dotenv_values()

def create_llm_and_context():
    system_instruction = config.get("SYSTEM_INSTRUCTION")
    initial_context = config.get("INITIAL_CONTEXT")
    llm = GeminiMultimodalLiveLLMService(
        api_key=config.get("GOOGLE_API_KEY"),
        system_instruction=system_instruction,
        tools=tools,
    )
    llm.register_function("get_available_gpus", fetch_marketplace_data)
    context = OpenAILLMContext(
        [
            {
                "role": "user",
                "content": initial_context,
            }
        ],
    )
    context_aggregator = llm.create_context_aggregator(context)
    return llm, context_aggregator
