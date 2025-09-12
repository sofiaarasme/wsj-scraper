from playwright.sync_api import sync_playwright
import os

WSJ_URL = "https://www.wsj.com/market-data/quotes/fx/USDCNY/historical-prices#"
STATE_FILE = "session_state.json"

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        slow_mo=500,
        args=["--disable-blink-features=AutomationControlled"]
    )
    
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800}
    )
    
    page = context.new_page()

    print(f"Navigating to {WSJ_URL} in visible mode.")
    print("The yellow 'automation' bar should no longer appear.")
    print("Please resolve the captcha and/or accept any cookies that appear.")

    page.goto(WSJ_URL, wait_until="domcontentloaded", timeout=60000)

    print("\nYou have 30 seconds to interact with the page...")
    print("Make sure to see the price table before time runs out.")
    page.wait_for_timeout(30000)

    try:
        context.storage_state(path=STATE_FILE)
        print(f"\n>>> Success! Session has been successfully saved to '{STATE_FILE}'.")
    except Exception as e:
        print(f"\nERROR: Could not save session state: {e}")

    input("Press ENTER to close the debug browser...")
    browser.close()