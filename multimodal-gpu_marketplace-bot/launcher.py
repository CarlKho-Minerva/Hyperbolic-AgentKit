import asyncio
import threading
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn
import os
from loguru import logger

# We will import your bot's main function
from main import main as run_bot_pipeline

# Keep track of the bot's thread so we only run one at a time
bot_thread = None

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serves the simple HTML page with the start button."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Hyperbolic Bot Launcher</title>
        <style>
            body { font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f5f5f5; }
            .container { text-align: center; }
            button { font-size: 1.5rem; padding: 15px 30px; cursor: pointer; border-radius: 8px; border: none; background-color: #007bff; color: white; }
            p { margin-top: 20px; color: #666; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>GPU Marketplace Voice Assistant</h1>
            <form action="/start-bot" method="post">
                <button type="submit">Click to Start Demo Bot</button>
            </form>
            <p id="status"></p>
        </div>
        <script>
            const form = document.querySelector('form');
            const status = document.getElementById('status');
            form.addEventListener('submit', function(e) {
                e.preventDefault();
                status.textContent = 'Starting bot... Please join the Daily room in a moment.';
                fetch('/start-bot', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        status.textContent = data.message;
                    });
                form.querySelector('button').disabled = true;
            });
        </script>
    </body>
    </html>
    """


def run_bot_in_thread():
    """Runs the asyncio bot in a separate thread."""
    logger.info("Starting bot pipeline in a background thread.")
    try:
        asyncio.run(run_bot_pipeline())
        logger.info("Bot pipeline thread finished.")
    except Exception as e:
        logger.error(f"Error in bot thread: {e}")


@app.post("/start-bot")
async def start_bot_endpoint():
    """API endpoint to start the bot."""
    global bot_thread
    if bot_thread and bot_thread.is_alive():
        return {"message": "Bot is already running."}

    # Run the main bot function in a background thread
    bot_thread = threading.Thread(target=run_bot_in_thread)
    bot_thread.start()

    return {"message": "Bot has been started. It will join the Daily room shortly."}


if __name__ == "__main__":
    # Note: Use the port Render provides through the PORT environment variable.
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
