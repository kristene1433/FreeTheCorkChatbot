# scraper.py
import re
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

def scrape_experiences(url, container_selector) -> str:
    """
    Scrapes 'Experiences' from a page and returns them as a text summary.
    Args:
        url (str): The URL of the website (Experiences page).
        container_selector (str): CSS selector to capture the experiences info.
    Returns:
        str: A summarized text of upcoming experiences found on the page.
    """
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        
        # Simulate a real browser user agent
        page.set_extra_http_headers({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/91.0.4472.124 Safari/537.36")
        })

        # Navigate & wait
        try:
            page.goto(url, timeout=60000)
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
        except:
            print("Page load timed out or had an error.")
        
        # Gather text from all elements matching the selector
        elements = page.query_selector_all(container_selector)
        if not elements:
            browser.close()
            return "No experiences found."

        events_text = []
        for el in elements:
            content = el.inner_text()
            if content:
                events_text.append(content.strip())

        browser.close()

    # Join them with line breaks or bullet points
    full_text = "\n".join(events_text)
    
    # (Optional) do some light cleaning or summarizing
    full_text = re.sub(r"\s+", " ", full_text)  # remove extra whitespace
    full_text = full_text.strip()

    if not full_text:
        return "No experiences found on the page."
    return full_text
