<<<<<<< HEAD
# bse-scraper
=======
# Project 1: BSE India Live Data Scraper

```bash
pip install -r requirements.txt
playwright install chromium
python app.py        # open http://127.0.0.1:5000
```
- `scraper.py`: Playwright loads the page, waits for the table to hydrate (`wait_for_function`), BeautifulSoup parses the DOM. No finance wrappers.
- `app.py`: Flask serves the page and `/api/gainers`; a background thread re-scrapes every 60 s and keeps the last good data on failure.
- If BSE changes its markup, adjust `READY_JS` and the column keys in `scraper.py`.
>>>>>>> caa0e41 (Initial commit: BSE Top Gainers Scraper)
