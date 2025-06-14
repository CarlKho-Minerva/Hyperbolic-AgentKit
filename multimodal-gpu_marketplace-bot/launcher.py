# launcher.py
import os
import subprocess
import sys
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
from loguru import logger

app = FastAPI()

# Get the URL from environment variables to pass to the frontend
DAILY_ROOM_URL = "https://hyperbolic.daily.co/MkJPeAMVfgruvM1zVGg4"

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serves the simple HTML page with the start button."""
    # We will now pass the room URL to the HTML so the button can open it.
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Hyperbolic Bot Launcher</title>
        <style>
            body {{ font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f5f5f5; }}
            .container {{ text-align: center; }}
            button {{ font-size: 1.5rem; padding: 15px 30px; cursor: pointer; border-radius: 8px; border: none; background-color: #007bff; color: white; }}
            button:disabled {{ background-color: #cccccc; }}
            p {{ margin-top: 20px; color: #666; }}
            a {{ color: #007bff; text-decoration: none; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>GPU Marketplace Voice Assistant</h1>
            <button id="startButton">Click to Start Demo Bot</button>
            <p id="status"></p>
        </div>
        <script>
            const startButton = document.getElementById('startButton');
            const status = document.getElementById('status');
            const roomUrl = "{DAILY_ROOM_URL}";

            startButton.addEventListener('click', function() {{
                startButton.disabled = true;
                status.innerHTML = 'Starting bot... This may take a moment. <br>The bot will join the Daily room automatically.';

                fetch('/start-bot', {{ method: 'POST' }})
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            status.innerHTML = `Bot is starting! <br> <a href="${{roomUrl}}" target="_blank">Click here to join the Daily room.</a>`;
                            // The bot will stop on its own after being idle.
                        }} else {{
                            status.textContent = `Error: ${{data.message}}`;
                            startButton.disabled = false;
                        }}
                    }})
                    .catch(err => {{
                        status.textContent = 'Failed to start the bot. Please check server logs.';
                        startButton.disabled = false;
                    }});
            }});
        </script>
    </body>
    </html>
    """

# Variable to track if the bot process is running
bot_process = None

@app.post("/start-bot")
async def start_bot_endpoint():
    """API endpoint to launch the bot script as a separate process."""
    global bot_process

    # Check if the bot process is already running
    if bot_process and bot_process.poll() is None:
        logger.info("Bot process is already running.")
        return JSONResponse({"success": False, "message": "Bot is already running."})

    try:
        # Find the path to the main.py script
        script_path = os.path.join(os.path.dirname(__file__), "main.py")

        # We need to use the same Python interpreter that is running this launcher
        python_executable = sys.executable

        logger.info(f"Launching bot script: {python_executable} {script_path}")

        # Launch main.py as a new, independent process
        # This completely avoids threading/multiprocessing issues with asyncio
        bot_process = subprocess.Popen([python_executable, script_path])

        return JSONResponse({"success": True, "message": "Bot started successfully."})

    except Exception as e:
        logger.error(f"Failed to launch bot process: {e}")
        return JSONResponse({"success": False, "message": f"Failed to start bot: {e}"}, status_code=500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting launcher web server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)