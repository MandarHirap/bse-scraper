"""
BSE Top Gainers Dashboard

Flask backend providing market data through a REST API.
A background worker periodically scrapes BSE India
and maintains the latest successfully retrieved data.
"""

import os
import time
import logging
import threading

from datetime import datetime
from flask import Flask, jsonify, render_template

from scraper import scrape


# --------------------------------------------------
# Configuration
# --------------------------------------------------

REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "300"))
HOST = os.getenv("FLASK_HOST", "127.0.0.1")
PORT = int(os.getenv("FLASK_PORT", "5000"))


# --------------------------------------------------
# Application Setup
# --------------------------------------------------

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# Shared Application State
# --------------------------------------------------

state = {
    "rows": [],
    "updated": None,
    "last_attempt": None,
    "error": None,
    "status": "Initializing"
}

lock = threading.Lock()


# --------------------------------------------------
# Background Scraping Worker
# --------------------------------------------------

def worker():
    """Periodically scrape BSE and update dashboard data."""

    logger.info("BSE background worker started.")

    while True:

        attempt_time = datetime.now().strftime(
            "%d %b %Y, %H:%M:%S"
        )

        try:

            logger.info("Starting BSE scraping cycle.")

            rows = scrape()

            with lock:

                state["last_attempt"] = attempt_time

                if rows:

                    state["rows"] = rows

                    state["updated"] = datetime.now().strftime(
                        "%d %b %Y, %H:%M:%S"
                    )

                    state["error"] = None
                    state["status"] = "Success"

                    logger.info(
                        "Updated %d market records.",
                        len(rows)
                    )

                else:

                    state["error"] = (
                        "Unable to retrieve market data from BSE. "
                        "Previous successful data has been retained."
                    )

                    state["status"] = (
                        "Stale" if state["rows"] else "Failed"
                    )

                    logger.warning(
                        "Scraping failed. Previous data retained."
                    )

        except Exception as error:

            with lock:

                state["last_attempt"] = attempt_time

                state["error"] = (
                    f"{type(error).__name__}: {error}"
                )[:300]

                state["status"] = (
                    "Stale" if state["rows"] else "Failed"
                )

            logger.exception("Scraping cycle failed.")

        time.sleep(REFRESH_SECONDS)


# --------------------------------------------------
# Dashboard Route
# --------------------------------------------------

@app.get("/")
def index():

    return render_template(
        "index.html",
        refresh=REFRESH_SECONDS
    )


# --------------------------------------------------
# Market Data API
# --------------------------------------------------

@app.get("/api/gainers")
def api():

    with lock:
        response = state.copy()

    return jsonify(response)


# --------------------------------------------------
# Application Entry Point
# --------------------------------------------------

if __name__ == "__main__":

    scraping_thread = threading.Thread(
        target=worker,
        name="BSE-Scraper",
        daemon=True
    )

    scraping_thread.start()

    logger.info(
        "Starting Flask application at http://%s:%s",
        HOST,
        PORT
    )

    app.run(
        host=HOST,
        port=PORT,
        debug=False,
        use_reloader=False,
        threaded=True
    )