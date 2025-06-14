import os
import subprocess
import sys
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import uvicorn
from loguru import logger
import signal
import time

app = FastAPI()

# --- Global State Management ---
# This dictionary holds the state of our bot process.
# This simple in-memory state is perfect for a single Render instance.
bot_state = {
    "process": None,
    "status": "STOPPED",  # Can be: STOPPED, STARTING, RUNNING, STOPPING
}

DAILY_ROOM_URL = os.getenv(
    "DAILY_SAMPLE_ROOM_URL", "https://your-room.daily.co/default-room"
)


def get_page_html():
    """Generates the HTML for the control page based on the current bot state."""
    status = bot_state["status"]

    if status == "RUNNING":
        return f"""
            <h1>GPU Bot is <span style="color: green;">RUNNING</span></h1>
            <p>The bot is active. You can now join the call.</p>
            <a href="{DAILY_ROOM_URL}" target="_blank" class="button">Join Daily Room</a>
            <form action="/stop-bot" method="post" style="margin-top: 20px;">
                <button type="submit">Stop Bot Session</button>
            </form>
        """
    elif status == "STOPPED":
        return """
            <h1>GPU Bot is <span style="color: red;">STOPPED</span></h1>
            <p>Click the button to start a new demo session.</p>
            <form action="/start-bot" method="post">
                <button type="submit">Start Bot Session</button>
            </form>
        """
    elif status == "STARTING":
        return """
            <h1>GPU Bot is <span style="color: orange;">STARTING...</span></h1>
            <p>Please wait, this can take up to 30 seconds.</p>
            <button disabled>Starting...</button>
        """
    elif status == "STOPPING":
        return """
            <h1>GPU Bot is <span style="color: orange;">STOPPING...</span></h1>
            <p>Please wait while the session is terminated.</p>
            <button disabled>Stopping...</button>
        """


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serves the main control page, which changes based on the bot's status."""
    return f"""
    <!DOCTYPE html><html><head><title>Bot Control</title>
    <meta http-equiv="refresh" content="5"> <!-- Auto-refresh page every 5 seconds to update status -->
    <style>
        body {{ font-family: sans-serif; text-align: center; padding-top: 50px; background-color: #f0f0f0; }}
        h1 {{ color: #333; }}
        p {{ color: #666; }}
        button, .button {{ display: inline-block; font-size: 1.2em; padding: 12px 24px; cursor: pointer; border: none; border-radius: 5px; text-decoration: none; color: white; }}
        button {{ background-color: #28a745; }}
        form button {{ background-color: #dc3545; }}
        .button {{ background-color: #007bff; }}
        button:disabled {{ background-color: #cccccc; cursor: not-allowed; }}
    </style>
    </head><body>
        <div id="control-panel">
            {get_page_html()}
        </div>
    </body></html>
    """


@app.post("/start-bot")
async def start_bot_endpoint():
    """Endpoint to launch the bot. Prevents starting if not STOPPED."""
    if bot_state["status"] != "STOPPED":
        logger.warning(f"Attempted to start bot while in state: {bot_state['status']}")
        return RedirectResponse(url="/", status_code=303)

    bot_state["status"] = "STARTING"
    logger.info("Bot state changed to STARTING.")

    try:
        script_path = os.path.join(os.path.dirname(__file__), "main.py")
        python_executable = sys.executable
        process = subprocess.Popen([python_executable, script_path])

        bot_state["process"] = process
        # Give it a moment to stabilize before changing state to RUNNING
        time.sleep(5)  # A small delay to let the process actually start
        bot_state["status"] = "RUNNING"
        logger.info(
            f"Bot process started with PID {process.pid}. State is now RUNNING."
        )

    except Exception as e:
        logger.error(f"Failed to launch bot process: {e}")
        bot_state["status"] = "STOPPED"

    return RedirectResponse(url="/", status_code=303)


@app.post("/stop-bot")
async def stop_bot_endpoint():
    """Endpoint to stop the bot. Prevents stopping if not RUNNING."""
    if bot_state["status"] != "RUNNING":
        logger.warning(f"Attempted to stop bot while in state: {bot_state['status']}")
        return RedirectResponse(url="/", status_code=303)

    bot_state["status"] = "STOPPING"
    logger.info("Bot state changed to STOPPING.")

    process = bot_state["process"]
    if process and process.poll() is None:
        logger.info(f"Sending SIGTERM to bot process with PID: {process.pid}")
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=15)
            logger.info("Bot process terminated gracefully.")
        except subprocess.TimeoutExpired:
            logger.warning("Bot did not terminate in time, sending SIGKILL.")
            process.kill()

    bot_state["process"] = None
    bot_state["status"] = "STOPPED"
    logger.info("Bot state changed to STOPPED.")

    return RedirectResponse(url="/", status_code=303)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting bot launcher on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
