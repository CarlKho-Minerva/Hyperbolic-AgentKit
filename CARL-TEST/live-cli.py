"""
## Documentation
Quickstart: https://github.com/google-gemini/cookbook/blob/main/quickstarts/Get_started_LiveAPI.py

## Setup

To install the dependencies for this script, run:

```
pip install google-genai opencv-python pyaudio pillow mss
```
"""

import asyncio
import base64
import io
import os
import traceback

import cv2
import pyaudio
import PIL.Image
import mss

import argparse
from dotenv import load_dotenv

from google import genai
from google.genai import types

FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

MODEL = "models/gemini-2.0-flash-live-001"

DEFAULT_MODE = "camera"

# Load environment variables from .env file
load_dotenv()

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("Missing GEMINI_API_KEY environment variable. Please set it to your Google Gemini API key in the .env file.")

client = genai.Client(
    api_key=API_KEY,
    http_options={"api_version": "v1beta"},
)

tools = [
    types.Tool(code_execution=types.ToolCodeExecution),
    types.Tool(google_search=types.GoogleSearch()),
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="getWeather",
                description="gets the weather for a requested city",
                parameters=genai.types.Schema(
                    type = genai.types.Type.OBJECT,
                    properties = {
                        "city": genai.types.Schema(
                            type = genai.types.Type.STRING,
                        ),
                    },
                ),
            ),
        ]
    ),
]

# While Gemini 2.0 Flash is in experimental preview mode, only one of AUDIO or
# TEXT may be passed here.
CONFIG = types.LiveConnectConfig(
    response_modalities=[
        "audio",
    ],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
        )
    ),
    tools=tools,
)

pya = pyaudio.PyAudio()


class AudioLoop:
    def __init__(self, video_mode=DEFAULT_MODE):
        self.video_mode = video_mode

        self.audio_in_queue = None
        self.out_queue = None

        self.session = None

        self.send_text_task = None
        self.receive_audio_task = None
        self.play_audio_task = None

    async def send_text(self):
        while True:
            text = await asyncio.to_thread(
                input,
                "message > ",
            )
            if text.lower() == "q":
                break
            # Debug: print transcribed text
            print(f"[DEBUG] Transcribed: {text}")
            # Use send_client_content for text input (correct args)
            await self.session.send_client_content(
                turns={"role": "user", "parts": [{"text": text or "."}]},
                turn_complete=True
            )

    def _get_frame(self, cap):
        # Read the frameq
        ret, frame = cap.read()
        # Check if the frame was read successfully
        if not ret:
            print("[DEBUG] Camera frame not captured.")
            return None
        print("[DEBUG] Camera frame captured.")
        # Fix: Convert BGR to RGB color space
        # OpenCV captures in BGR but PIL expects RGB format
        # This prevents the blue tint in the video feed
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(frame_rgb)  # Now using RGB frame
        img.thumbnail([1024, 1024])

        image_io = io.BytesIO()
        img.save(image_io, format="jpeg")
        image_io.seek(0)

        mime_type = "image/jpeg"
        image_bytes = image_io.read()
        return {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}

    async def get_frames(self):
        # This takes about a second, and will block the whole program
        # causing the audio pipeline to overflow if you don't to_thread it.
        cap = await asyncio.to_thread(
            cv2.VideoCapture, 0
        )  # 0 represents the default camera
        print("[DEBUG] Camera capture started.")
        while True:
            frame = await asyncio.to_thread(self._get_frame, cap)
            if frame is None:
                print("[DEBUG] No frame to send.")
                break
            print("[DEBUG] Sending camera frame to out_queue.")
            await asyncio.sleep(1.0)
            await self.out_queue.put(frame)

        # Release the VideoCapture object
        cap.release()
        print("[DEBUG] Camera capture released.")

    def _get_screen(self):
        sct = mss.mss()
        monitor = sct.monitors[0]

        i = sct.grab(monitor)

        mime_type = "image/jpeg"
        image_bytes = mss.tools.to_png(i.rgb, i.size)
        img = PIL.Image.open(io.BytesIO(image_bytes))

        image_io = io.BytesIO()
        img.save(image_io, format="jpeg")
        image_io.seek(0)

        image_bytes = image_io.read()
        return {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}

    async def get_screen(self):
        print("[DEBUG] Screen sharing started.")
        while True:
            frame = await asyncio.to_thread(self._get_screen)
            if frame is None:
                print("[DEBUG] No screen frame to send.")
                break
            print("[DEBUG] Sending screen frame to out_queue.")
            await asyncio.sleep(1.0)
            await self.out_queue.put(frame)
        print("[DEBUG] Screen sharing stopped.")

    async def send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            mime_type = msg.get("mime_type")
            data = msg.get("data")
            blob = types.Blob(data=data, mime_type=mime_type)
            if mime_type == "audio/pcm":
                await self.session.send_realtime_input(audio=blob)
            elif mime_type in ["image/jpeg", "video/mp4"]:
                await self.session.send_realtime_input(video=blob)
            else:
                print(f"[WARN] Unknown mime_type for realtime input: {mime_type}")

    async def listen_audio(self):
        mic_info = pya.get_default_input_device_info()
        self.audio_stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=mic_info["index"],
            frames_per_buffer=CHUNK_SIZE,
        )
        if __debug__:
            kwargs = {"exception_on_overflow": False}
        else:
            kwargs = {}
        while True:
            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
            await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})

    async def receive_audio(self):
        """Background task to read from the websocket and write pcm chunks to the output queue, and handle tool calls."""
        while True:
            turn = self.session.receive()
            async for response in turn:
                # Handle tool (function) calls
                if response.tool_call:
                    for tool_call in response.tool_call:
                        tool_name = tool_call.name
                        tool_args = tool_call.args
                        # Example: print tool call info (replace with your tool logic)
                        print(f"Tool call: {tool_name}({tool_args})")
                        # You can implement your tool logic here and send the result back:
                        # result = ...
                        # await self.session.send_tool_response(tool_call_id=tool_call.id, content=result)
                    continue
                if data := response.data:
                    self.audio_in_queue.put_nowait(data)
                    continue
                if text := response.text:
                    print(text, end="")

            # If you interrupt the model, it sends a turn_complete.
            # For interruptions to work, we need to stop playback.
            # So empty out the audio queue because it may have loaded
            # much more audio than has played yet.
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()

    async def play_audio(self):
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        while True:
            bytestream = await self.audio_in_queue.get()
            await asyncio.to_thread(stream.write, bytestream)

    async def run(self):
        try:
            async with (
                client.aio.live.connect(model=MODEL, config=CONFIG) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session

                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue(maxsize=5)

                send_text_task = tg.create_task(self.send_text())
                tg.create_task(self.send_realtime())
                tg.create_task(self.listen_audio())
                if self.video_mode == "camera":
                    tg.create_task(self.get_frames())
                elif self.video_mode == "screen":
                    tg.create_task(self.get_screen())

                tg.create_task(self.receive_audio())
                tg.create_task(self.play_audio())

                await send_text_task
                raise asyncio.CancelledError("User requested exit")

        except asyncio.CancelledError:
            pass
        except ExceptionGroup as EG:
            self.audio_stream.close()
            traceback.print_exception(EG)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        type=str,
        default=None,
        help="pixels to stream from",
        choices=["camera", "screen", "none"],
    )
    args = parser.parse_args()

    # Interactive CLI select if --mode not provided
    mode = args.mode
    if mode is None:
        print("Select video mode:")
        print("1) camera (default)")
        print("2) screen")
        print("3) none (audio only)")
        choice = input("Enter choice [1-3]: ").strip()
        if choice == "2":
            mode = "screen"
        elif choice == "3":
            mode = "none"
        else:
            mode = "camera"

    # Add CLI confirmation before accessing camera/mic
    if mode == "camera":
        confirm = input("This will access your CAMERA and MICROPHONE. Continue? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            exit(0)
    elif mode == "none":
        confirm = input("This will access your MICROPHONE. Continue? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            exit(0)
    elif mode == "screen":
        confirm = input("This will access your SCREEN and MICROPHONE. Continue? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            exit(0)

    main = AudioLoop(video_mode=mode)
    asyncio.run(main.run())
