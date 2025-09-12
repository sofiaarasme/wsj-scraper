#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import re
import sys
from datetime import datetime, timezone
import random

import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_sync

WSJ_URL = "https://www.wsj.com/market-data/quotes/fx/USDCNY/historical-prices#"
STATE_FILE = "session_state.json"

def _parse_number(txt: str):
    if txt is None: return None
    txt = re.sub(r"[^\d\.\-]", "", txt.strip())
    if not txt: return None
    try:
        return float(txt)
    except:
        return None

def _parse_wsj_date(txt: str):
    txt = txt.strip()
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})$", txt)
    if not m:
        return None
    mm, dd, yy = m.groups()
    if len(yy) == 2:
        yy = int(yy)
        year = 2000 + yy if yy <= 69 else 1900 + yy
    else:
        year = int(yy)
    try:
        d = datetime(year, int(mm), int(dd))
        return d.strftime("%Y-%m-%d")
    except:
        return None

def fetch_latest_from_wsj(timeout_ms: int = 60000, headless: bool = True):
    print(f"Launching browser (headless={headless})...")

    if not os.path.exists(STATE_FILE):
        raise FileNotFoundError(f"Session file '{STATE_FILE}' does not exist. "
                                f"Please run 'python wsj_debug.py' first to create the session.")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        context = browser.new_context(
            storage_state=STATE_FILE,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800}
        )
        
        page = context.new_page()

        print(f"Navigating to {WSJ_URL} (robust loading strategy)...")
        try:
            page.goto(WSJ_URL, wait_until="domcontentloaded", timeout=timeout_ms)

            print("Base page loaded. Waiting for the table container to appear in the HTML...")
            table_container_locator = page.locator("div#historical_data_table")
            table_container_locator.wait_for(state="attached", timeout=timeout_ms - 5000)

        except Exception as e:
            print(f"CRITICAL error during page load or initial table location: {e}")
            page.screenshot(path="wsj_load_error.png")
            raise RuntimeError("The page did not load the table container in time.")

        print("Table container located. Scrolling...")
        try:
            table_container_locator.scroll_into_view_if_needed()
            page.wait_for_timeout(2000)

            table = table_container_locator.locator("table.cr_dataTable")

            print("Waiting for data rows to load...")
            table.locator("tbody tr").first.wait_for(state="visible", timeout=15000)
            print("Success! Data loaded in the table.")

        except Exception as e:
            print(f"Error scrolling or loading table data: {e}")
            page.screenshot(path="wsj_data_load_error.png")
            raise RuntimeError("Data could not be loaded into the table.")

        print("Reading the first row of the table...")
        try:
            first_row = table.locator("tbody tr").first
            cells = first_row.locator("td")
            date_txt = cells.nth(0).inner_text().strip()
            close_txt = cells.nth(4).inner_text().strip()
        except Exception as e:
            page.screenshot(path="wsj_read_row_error.png")
            raise RuntimeError(f"Error reading row after data was loaded: {e}")

        date_iso = _parse_wsj_date(date_txt)
        close_val = _parse_number(close_txt)

        if not date_iso or close_val is None:
            raise RuntimeError(f"Could not parse Date='{date_txt}' or Close='{close_val}' from WSJ.")

        browser.close()
        return date_iso, close_val

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_gspread_client(service_account_json: str = None):
    if service_account_json and os.path.exists(service_account_json):
        creds = Credentials.from_service_account_file(service_account_json, scopes=SCOPES)
    else:
        env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not env or not os.path.exists(env):
            raise RuntimeError("JSON service account not found. Use --service-account-json or GOOGLE_APPLICATION_CREDENTIALS.")
        creds = Credentials.from_service_account_file(env, scopes=SCOPES)
    return gspread.authorize(creds)

def ensure_header(ws):
    header = ["date","close","source","retrieved_at_utc"]
    current = ws.row_values(1)
    if [c.lower() for c in current] != header:
        print("Header does not match or is empty. Setting standard header.")
        ws.clear()
        ws.append_row(header, value_input_option="RAW")
    else:
        print("Existing header matches.")

def append_if_new(ws, date_iso, close_val, source):
    rows = ws.get_all_values()
    existing = [r[0] for r in rows[1:]] if len(rows) > 1 else []
    if date_iso in existing:
        print(f"{date_iso} already exists in the spreadsheet — not inserting.")
        return False
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"Inserting new row: {date_iso}, {close_val}, {source}, {retrieved}")
    ws.append_row([date_iso, close_val, source, retrieved], value_input_option="USER_ENTERED")
    return True

def main():
    sheet_id = os.environ.get("SHEET_ID")
    service_account_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    
    if not sheet_id or not service_account_file:
        raise ValueError("Environment variables SHEET_ID and GOOGLE_APPLICATION_CREDENTIALS must be set.")

    date_iso, close_val = fetch_latest_from_wsj()
    print(f"Data obtained from WSJ: Date='{date_iso}', Value='{close_val}'")

    print("Connecting to Google Sheets...")
    client = get_gspread_client(service_account_file)
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet("USDCNY")
        print("Worksheet 'USDCNY' found.")
    except gspread.exceptions.WorksheetNotFound:
        print("Worksheet 'USDCNY' not found. Creating it...")
        ws = sh.add_worksheet(title="USDCNY", rows=1000, cols=10)
        print("Worksheet 'USDCNY' created.")

    ensure_header(ws)
    inserted = append_if_new(ws, date_iso, close_val, WSJ_URL)
    if inserted:
        print("Data inserted successfully.")
    else:
        print("No data inserted (already exists or there was a problem).")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\nERROR CRÍTICO:", e)
        sys.exit(1)