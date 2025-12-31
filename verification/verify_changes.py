from playwright.sync_api import sync_playwright

def verify_frontend():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate to the app
        page.goto("http://localhost:5000")

        # Wait for the page to load
        page.wait_for_selector(".header")

        # Click the info button to reveal API docs
        page.click(".info-button")

        # Wait for API docs to be visible
        page.wait_for_selector("#apiDocs.show")

        # Take a screenshot
        page.screenshot(path="verification/frontend.png")

        browser.close()

if __name__ == "__main__":
    verify_frontend()
