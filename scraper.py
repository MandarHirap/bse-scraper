"""
BSE Top Gainers Scraper

Extracts equity market data directly from BSE India
using Playwright and BeautifulSoup.

Fields:
    - Security Code
    - Company Name
    - Last Traded Price (LTP)
    - Percentage Change
"""

import os
import re
import logging

from bs4 import BeautifulSoup
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError
)


# --------------------------------------------------
# Configuration
# --------------------------------------------------

URL = (
    "https://www.bseindia.com/markets/equity/"
    "EQReports/mktwatchR.html?filter=gainer*all$all$"
)

# BSE previously returned HTTP 403 in headless mode.
# Visible browser mode is therefore the default.

HEADLESS = os.getenv(
    "BSE_HEADLESS", "false"
).lower() in ("true", "1", "yes")

PAGE_TIMEOUT = 60000
TABLE_TIMEOUT = 45000
MINIMUM_ROWS = 5


# --------------------------------------------------
# Logging
# --------------------------------------------------

logger = logging.getLogger(__name__)


# --------------------------------------------------
# Utility Functions
# --------------------------------------------------

def extract_number(text):
    """
    Extract a numeric value from text.

    Examples:
        '1,250.50' -> 1250.50
        '+12.50%'  -> 12.50
        '-3.25%'   -> -3.25
    """

    if not text:
        return None

    match = re.search(
        r"[+-]?\d[\d,]*\.?\d*",
        text.replace(",", "")
    )

    if not match:
        return None

    try:
        return float(match.group())
    except ValueError:
        return None


def find_column(headers, *keywords):
    """Find a column index using specific header keywords."""

    for index, header in enumerate(headers):

        header = re.sub(
            r"\s+",
            " ",
            header.lower().strip()
        )

        if any(keyword in header for keyword in keywords):
            return index

    return None


def extract_security_code(row):
    """
    Extract the six-digit BSE security code
    from the table row.
    """

    for cell in row.find_all("td"):

        text = cell.get_text(" ", strip=True)

        match = re.fullmatch(r"\d{6}", text)

        if match:
            return match.group()

    for link in row.find_all("a"):

        href = link.get("href", "")

        match = re.search(r"\b\d{6}\b", href)

        if match:
            return match.group()

    return ""


def extract_company_name(row, security_code, name_index=None):
    """
    Extract the company name without confusing it
    with the six-digit security code.
    """

    cells = row.find_all("td")

    # First preference: use the identified company-name column.
    if name_index is not None and name_index < len(cells):

        company_name = cells[name_index].get_text(
            " ",
            strip=True
        )

        if (
            company_name
            and company_name != security_code
            and re.search(r"[A-Za-z]{2,}", company_name)
        ):
            return company_name

    # Second preference: inspect links for company names.
    for link in row.find_all("a"):

        link_text = link.get_text(" ", strip=True)

        if (
            link_text
            and link_text != security_code
            and re.search(r"[A-Za-z]{2,}", link_text)
            and not re.fullmatch(r"\d{6}", link_text)
        ):
            return link_text

    # Final fallback: inspect the remaining table cells.
    for index, cell in enumerate(cells):

        if index == name_index:
            continue

        text = cell.get_text(" ", strip=True)

        if not text or text == security_code:
            continue

        # Ignore numeric values and percentages.
        if re.fullmatch(r"[\d,.\s+-]+%?", text):
            continue

        if "%" in text:
            continue

        if re.search(r"[A-Za-z]{2,}", text):
            return text

    return ""


# --------------------------------------------------
# HTML Parsing
# --------------------------------------------------

def parse(html):
    """
    Parse BSE HTML and extract Top Gainers data.

    Returns:
        List of dictionaries containing:
        code, name, ltp and pct.
    """

    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")

    if not tables:
        logger.warning("No HTML tables found.")
        return []

    best_table = None
    best_headers = []
    best_rows = []

    # --------------------------------------------------
    # Identify the BSE Top Gainers table
    # --------------------------------------------------

    for table in tables:

        table_rows = table.find_all("tr")

        headers = [
            th.get_text(" ", strip=True).lower()
            for th in table.find_all("th")
        ]

        data_rows = [
            row for row in table_rows
            if len(row.find_all("td")) >= 4
        ]

        if len(data_rows) < MINIMUM_ROWS:
            continue

        has_price_column = find_column(
            headers,
            "ltp",
            "last traded price"
        ) is not None

        has_change_column = find_column(
            headers,
            "% chg",
            "%chg",
            "% change",
            "pchg",
            "change %"
        ) is not None

        if has_price_column and has_change_column:

            if (
                best_table is None
                or len(data_rows) > len(best_rows)
            ):
                best_table = table
                best_headers = headers
                best_rows = data_rows

    if best_table is None:

        logger.warning(
            "Could not identify the BSE Top Gainers table."
        )

        return []

    # --------------------------------------------------
    # Identify Required Columns
    # --------------------------------------------------

    # IMPORTANT:
    # Do not use the generic keyword "security" here.
    # It can match Security Code instead of Security Name.

    name_index = find_column(
        best_headers,
        "security name",
        "company name",
        "scrip name"
    )

    code_index = find_column(
        best_headers,
        "security code",
        "scrip code"
    )

    ltp_index = find_column(
        best_headers,
        "ltp",
        "last traded price"
    )

    pct_index = find_column(
        best_headers,
        "% chg",
        "%chg",
        "% change",
        "pchg",
        "change %"
    )

    logger.info("Identified BSE table columns:")
    logger.info("Security Code column: %s", code_index)
    logger.info("Company Name column: %s", name_index)
    logger.info("LTP column: %s", ltp_index)
    logger.info("Percentage Change column: %s", pct_index)

    if ltp_index is None or pct_index is None:

        logger.error(
            "Required price or percentage column not found."
        )

        return []

    # --------------------------------------------------
    # Extract Market Records
    # --------------------------------------------------

    extracted_rows = []

    for row in best_rows:

        cells = row.find_all("td")

        values = [
            cell.get_text(" ", strip=True)
            for cell in cells
        ]

        # Extract Security Code.
        security_code = ""

        if code_index is not None and code_index < len(values):

            security_code = values[code_index]

        if not re.fullmatch(r"\d{6}", security_code):

            security_code = extract_security_code(row)

        # Extract Company Name.
        company_name = extract_company_name(
            row,
            security_code,
            name_index
        )

        # Extract LTP.
        if ltp_index >= len(values):
            continue

        ltp = extract_number(
            values[ltp_index]
        )

        # Extract Percentage Change.
        if pct_index >= len(values):
            continue

        percentage_change = extract_number(
            values[pct_index]
        )

        # Validate extracted data.
        if not security_code:
            logger.debug("Skipping row: security code missing.")
            continue

        if not company_name:
            logger.debug(
                "Skipping row: company name missing for %s.",
                security_code
            )
            continue

        if ltp is None or percentage_change is None:
            logger.debug(
                "Skipping row: invalid price data for %s.",
                security_code
            )
            continue

        extracted_rows.append({
            "code": security_code,
            "name": company_name,
            "ltp": ltp,
            "pct": percentage_change
        })

    # --------------------------------------------------
    # Extraction Summary
    # --------------------------------------------------

    logger.info(
        "Successfully extracted %d records.",
        len(extracted_rows)
    )

    if extracted_rows:

        logger.info(
            "Sample extracted record: %s",
            extracted_rows[0]
        )

    return extracted_rows


# --------------------------------------------------
# BSE Scraper
# --------------------------------------------------

def scrape():
    """
    Launch Chromium, navigate to BSE India,
    wait for dynamic content and extract market data.

    Returns:
        List of extracted market records.
        Empty list if scraping fails.
    """

    logger.info("Starting BSE scraper.")

    try:

        # Playwright lifecycle.
        with sync_playwright() as playwright:

            logger.info(
                "Browser mode: %s",
                "Headless" if HEADLESS else "Visible"
            )

            browser = playwright.chromium.launch(
                headless=HEADLESS
            )

            try:

                context = browser.new_context(
                    locale="en-IN",
                    viewport={
                        "width": 1440,
                        "height": 900
                    }
                )

                page = context.new_page()

                logger.info("Navigating to BSE India.")

                response = page.goto(
                    URL,
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT
                )

                # Check HTTP response.
                if response:

                    logger.info(
                        "HTTP Response: %s",
                        response.status
                    )

                    if response.status == 403:

                        logger.error(
                            "BSE access denied (HTTP 403)."
                        )

                        return []

                # Check page title.
                page_title = page.title()

                logger.info(
                    "Page Title: %s",
                    page_title
                )

                if "access denied" in page_title.lower():

                    logger.error(
                        "BSE returned Access Denied."
                    )

                    return []

                # --------------------------------------------------
                # Wait for Dynamic Table Content
                # --------------------------------------------------

                page.wait_for_function(
                    """
                    (minimumRows) => {

                        return [...document.querySelectorAll("table")]
                            .some(table => {

                                const rows = [
                                    ...table.querySelectorAll("tr")
                                ];

                                const dataRows = rows.filter(
                                    row =>
                                        row.querySelectorAll("td").length >= 4
                                );

                                return dataRows.length >= minimumRows;
                            });
                    }
                    """,
                    arg=MINIMUM_ROWS,
                    timeout=TABLE_TIMEOUT
                )

                # Check page body.
                body_text = page.locator(
                    "body"
                ).inner_text().lower()

                if "access denied" in body_text:

                    logger.error(
                        "BSE returned an access restriction page."
                    )

                    return []

                # --------------------------------------------------
                # Extract Rendered HTML
                # --------------------------------------------------

                html = page.content()

                # Parse using BeautifulSoup.
                rows = parse(html)

                if not rows:

                    logger.warning(
                        "No market records could be extracted."
                    )

                    return []

                logger.info(
                    "Scraping completed successfully. "
                    "Total records: %d",
                    len(rows)
                )

                return rows

            finally:

                # Close browser while Playwright is active.
                browser.close()

                logger.info("Browser closed.")

    except PlaywrightTimeoutError:

        logger.exception(
            "Timed out while loading BSE market data."
        )

        return []

    except Exception:

        logger.exception(
            "Unexpected error occurred during scraping."
        )

        return []