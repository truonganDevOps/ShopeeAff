# affiliate_automation.py

from playwright.sync_api import sync_playwright
import json
import time

# Shopee Affiliate Custom Link page
AFFILIATE_URL = "https://affiliate.shopee.vn/offer/custom_link"


# Load crawled products from products.json
def load_products(filename="products.json"):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


# Save products with affiliate links
def save_products(products, filename="aff_products.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)


# Split list into chunks (Shopee allows max 5 links each time)
def chunked(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


# Generate affiliate links automatically
def generate_affiliate_links(products):

    with sync_playwright() as p:

        # Persistent browser context
        # Keeps Shopee login session
        browser = p.chromium.launch_persistent_context(
            user_data_dir="affiliate_user_data",
            headless=False
        )

        page = browser.new_page()

        print("Opening Shopee Affiliate...")

        page.goto(AFFILIATE_URL)

        print("If not logged in, login manually then press ENTER...")
        input()

        all_results = []

        # Process products in batches of 5
        for batch in chunked(products, 5):

            links = [p["product_link"] for p in batch]

            print(f"Processing {len(links)} links...")

            # Find textarea and input product links
            # Wait textarea visible
            page.wait_for_selector("textarea", timeout=60000)

            # Re-select textarea every batch
            textarea = page.locator("textarea").first

            # Clear old content
            textarea.click()

            # Ctrl+A delete
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")

            # Fill new links
            textarea.fill("\n".join(links))

            time.sleep(2)

            # Click generate button
            generate_button = page.get_by_text("Lấy link").first

            generate_button.click()

            # Wait result
            page.wait_for_timeout(8000)

            textarea.fill("\n".join(links))

            time.sleep(1)

            # Click "Lấy link" button
            page.locator("button").filter(
                has_text="Lấy link"
            ).click()

            # Wait for Shopee to generate affiliate links
            page.wait_for_timeout(5000)

            # IMPORTANT:
            # This selector may change in future
            result_links = page.locator("a[href*='shope.ee']")

            count = result_links.count()

            affs = []

            # Extract generated affiliate links
            for i in range(count):

                try:
                    aff_link = result_links.nth(i).get_attribute("href")

                    if aff_link:
                        affs.append(aff_link)

                except:
                    continue

            # Attach affiliate links back to products
            for idx, product in enumerate(batch):

                if idx < len(affs):
                    product["affiliate_link"] = affs[idx]
                else:
                    product["affiliate_link"] = ""

                all_results.append(product)

            print(f"Generated {len(affs)} affiliate links")

            page.wait_for_timeout(2000)

        browser.close()

        return all_results


def main():

    # Load products from crawler output
    products = load_products()

    # Generate affiliate links
    results = generate_affiliate_links(products)

    # Save final result
    save_products(results)

    print("Saved to aff_products.json")


if __name__ == "__main__":
    main()