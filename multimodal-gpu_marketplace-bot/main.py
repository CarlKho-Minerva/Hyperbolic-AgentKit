#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

# Carl's note: we extended this code from the Daily SDK, which is licensed under the BSD 2-Clause License.
# # The Daily SDK is available at https://github.com/pipecat-ai/pipecat/tree/main

import asyncio
import os
import sys
import threading
from datetime import datetime

import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI
from loguru import logger
from runner import configure
import uvicorn
from websockets.exceptions import ConnectionClosedError

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.gemini_multimodal_live.gemini import (
    GeminiMultimodalLiveLLMService,
)
from pipecat.transports.services.daily import DailyParams, DailyTransport
from config import SYSTEM_INSTRUCTION, LLMCONTEXT_CONTENT
from tools import get_tool_declarations, register_all_tools

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


async def main():
    async with aiohttp.ClientSession() as session:
        (room_url, token) = await configure(session)

        transport = DailyTransport(
            room_url,
            token,
            "Respond bot",
            DailyParams(
                audio_out_enabled=True,
                vad_enabled=True,
                vad_audio_passthrough=True,
                # set stop_secs to something roughly similar to the internal setting
                # of the Multimodal Live api, just to align events. This doesn't really
                # matter because we can only use the Multimodal Live API's phrase
                # endpointing, for now.
                vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)),
            ),
        )

        llm = GeminiMultimodalLiveLLMService(
            api_key=os.getenv("GOOGLE_API_KEY"),
            system_instruction=SYSTEM_INSTRUCTION,
            tools=get_tool_declarations(),
            transcribe_user_audio=True,
            transcribe_model_audio=True,
            inference_on_context_initialization=True,
        )

        register_all_tools(llm)

        context = OpenAILLMContext(
            [
                {
                    "role": "user",
                    "content": LLMCONTEXT_CONTENT,
                }
            ],
        )
        context_aggregator = llm.create_context_aggregator(context)

        pipeline = Pipeline(
            [
                transport.input(),
                context_aggregator.user(),
                llm,
                context_aggregator.assistant(),
                transport.output(),
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
        )

        @transport.event_handler("on_participant_joined")
        async def on_first_participant_joined(transport, participant):
            await task.queue_frames([context_aggregator.user().get_context_frame()])
            await asyncio.sleep(3)
            await transport.capture_participant_video(
                participant["id"], framerate=1, video_source="screenVideo"
            )
            await transport.capture_participant_video(
                participant["id"], framerate=1, video_source="camera"
            )

            logger.debug("Unpausing audio and video")
            llm.set_audio_input_paused(False)
            llm.set_video_input_paused(False)

        runner = PipelineRunner()

        try:
            await runner.run(task)
        except ConnectionClosedError as e:
            logger.error(f"WebSocket connection closed unexpectedly: {e}")
            logger.error("This might be a temporary issue with the Gemini service. Please try running the script again later.")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            # Optionally re-raise or handle other errors as needed


def start_healthcheck_server():
    app = FastAPI()

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), log_level="warning")

# Start FastAPI health check server in a background thread
threading.Thread(target=start_healthcheck_server, daemon=True).start()


if __name__ == "__main__":
    asyncio.run(main())
