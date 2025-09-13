import json

INPUT_FILE = "cookies.json"      # The file exported from Cookie-Editor
OUTPUT_FILE = "session_state.json" # The file Playwright will use

def convert_cookies():
    """
    Converts a JSON file from the Cookie-Editor extension format to
    the format required by Playwright's context.storage_state().
    """
    try:
        with open(INPUT_FILE, 'r') as f:
            cookie_editor_json = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_FILE}' not found.")
        print("Please save the JSON you exported from Cookie-Editor as 'cookies.json' in this directory.")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{INPUT_FILE}'.")
        print("Please ensure the file contains valid JSON content.")
        return

    playwright_cookies = []
    for cookie in cookie_editor_json:
        # Create a new cookie dict in Playwright's format
        new_cookie = {
            "name": cookie.get("name"),
            "value": cookie.get("value"),
            "domain": cookie.get("domain"),
            "path": cookie.get("path"),
            "httpOnly": cookie.get("httpOnly", False),
            "secure": cookie.get("secure", False),
        }

        # Handle expirationDate -> expires
        # Playwright uses 'expires' with a Unix timestamp in seconds.
        if "expirationDate" in cookie and cookie["expirationDate"]:
            new_cookie["expires"] = cookie["expirationDate"]
        else:
            # If no expiration date, it's a session cookie. Playwright uses -1.
            new_cookie["expires"] = -1

        # Handle sameSite mapping
        same_site_value = cookie.get("sameSite", "lax").lower()
        if same_site_value == "no_restriction":
            new_cookie["sameSite"] = "None"
        elif same_site_value == "lax":
            new_cookie["sameSite"] = "Lax"
        elif same_site_value == "strict":
            new_cookie["sameSite"] = "Strict"
        else: # "unspecified" or other values
            new_cookie["sameSite"] = "Lax" # Lax is a safe and common default

        playwright_cookies.append(new_cookie)

    # Create the final storage state object that Playwright expects
    storage_state = {
        "cookies": playwright_cookies,
        "origins": [] # We don't have localStorage info from the export, so this is an empty list
    }

    # Write the new, correctly formatted JSON file
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(storage_state, f, indent=2)

    print(f"--> Successfully converted '{INPUT_FILE}' to '{OUTPUT_FILE}'.")
    print("You can now copy the content of 'session_state.json' and update your GitHub secret.")

if __name__ == "__main__":
    convert_cookies()