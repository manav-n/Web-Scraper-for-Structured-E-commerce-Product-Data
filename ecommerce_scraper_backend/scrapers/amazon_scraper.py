from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup as bs
from datetime import datetime
import re
import time
import json
import matplotlib
import platform
if platform.system() == 'Windows':
    matplotlib.use('TkAgg')  # Use TkAgg on Windows
else:
    matplotlib.use('Agg')  # Use Agg for headless systems
import ctypes
import atexit
import signal
from utils.terminal import output_queue, input_queue
from utils.file_handler import save_scraped_data, convert_to_csv
from utils.visualization import generate_visualizations
import os
from pathlib import Path
import zipfile



# Store all product details
all_product_details = []


def prevent_sleep():
    """Prevent system sleep."""
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000002)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    output_queue.put("System sleep prevented.")


def allow_sleep():
    """Allow system sleep."""
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)  # ES_CONTINUOUS
    output_queue.put("System sleep allowed.")


# Ensure sleep is allowed even if the program is terminated manually
atexit.register(allow_sleep)  # Call when program exits normally
signal.signal(signal.SIGINT, lambda signum, frame: (allow_sleep(), exit(0)))  # Ctrl+C
signal.signal(signal.SIGTERM, lambda signum, frame: (allow_sleep(), exit(0)))  # Kill command



def amazon_scrape():
    # Set up the driver
    driver = webdriver.Chrome()

    try:
        prevent_sleep()
        # Open Amazon homepage
        driver.get("https://www.amazon.in/")
        time.sleep(5)  # Allow time for the page to load

        output_queue.put("Please type your search query directly into the Amazon search box and press Enter.")
        output_queue.put("Once the search results have loaded, type 'ok' to proceed.")
        reply = input_queue.get().strip().lower() # Wait for user confirmation
        if reply != 'ok':
            output_queue.put("Scraping canceled by the user.")
            driver.quit()
            exit()


        # Extract the search term from the current URL
        search_url = driver.current_url
        if "k=" not in search_url:
            raise ValueError("Search term not found in URL. Please try again.")

        search_term = search_url.split("k=")[1].split("&")[0].replace("+", "_")
        search_term = search_term[:30]  # Truncate search term to avoid long filenames


        # Confirm the scraping process with the user
        output_queue.put(
                f"Do you want to scrape data for the search term '{search_term.replace('_', ' ')}'? (yes/no): ")
        proceed = input_queue.get().strip().lower()
        if proceed != 'yes':
            output_queue.put("Scraping canceled by the user.")
            driver.quit()
            exit()


        # Ask the user what fields they want to scrape
        available_fields = {
            "1": "link",
            "2": "image_url",
            "3": "title",
            "4": "original_price",
            "5": "discounted_price",
            "6": "discount_percentage",
            "7": "rating",
            "8": "reviews_count",
            "9": "last_month_sales",
            "10": "additional_features"
        }

        output_queue.put("\n")
        output_queue.put("Available fields to scrape:")
        for key, value in available_fields.items():
            output_queue.put(f"{key}. {value}")

        output_queue.put("\n")
        output_queue.put("Enter the numbers corresponding to the fields you want to scrape, separated by commas: ")
        selected_fields = input_queue.get()
        selected_fields = selected_fields.split(",")

        fields_to_scrape = [available_fields[field.strip()] for field in selected_fields if field.strip() in available_fields]

        if not fields_to_scrape:
            output_queue.put("No valid fields selected. Exiting.")
            driver.quit()
            exit()

        output_queue.put(f"Fields selected for scraping: {fields_to_scrape}")


        def pagination(driver):
            while True:
                try:
                    # Find all pagination elements
                    pagination_elements = driver.find_elements(By.CSS_SELECTOR,
                                                               "span.s-pagination-item.s-pagination-disabled")

                    # Check if at least two elements exist
                    if len(pagination_elements) >= 2:
                        max_pages_elem = pagination_elements[-1]  # Select the last pagination element
                        max_pages = int(max_pages_elem.text.strip())
                        output_queue.put(f"Total pages: {max_pages}")
                        return max_pages
                    elif len(pagination_elements) == 1:
                        elements = driver.find_elements(By.CSS_SELECTOR,
                                                        "li.s-list-item-margin-right-adjustment")
                        max_pages_elem = elements[-2]
                        max_pages = int(max_pages_elem.text.strip())
                        output_queue.put(f"Total pages: {max_pages}")
                        return max_pages
                    else:
                        output_queue.put("Total pages: 1")
                        return 1

                except (NoSuchElementException, IndexError):
                    output_queue.put("An error occurred. Please try again.")


        # Use the function to get total pages
        max_pages = pagination(driver)

        output_queue.put("\n")
        output_queue.put(f"How many pages do you want to scrape? (1-{max_pages}): ")
        pages_to_scrape = int(input_queue.get().strip())
        if pages_to_scrape < 1 or pages_to_scrape > max_pages:
            output_queue.put(f"Amazon displays only {max_pages} pages for a keyword. Please provide a page number between 1 and {max_pages}.")
            driver.quit()
            exit()

        output_queue.put(f"Scraping data for {pages_to_scrape} pages...")


        product_count = 0
        current_page = 1  # Track the current page


        while current_page <= pages_to_scrape:
            # Wait for the main results container to appear
            elem = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR,
                     '#search > div.s-desktop-width-max.s-desktop-content.s-opposite-dir.s-wide-grid-style.sg-row > div.sg-col-20-of-24.s-matching-dir.sg-col-16-of-20.sg-col.sg-col-8-of-12.sg-col-12-of-16')
                )
            )

            current_page_url = driver.current_url  # Store the current page URL
            data = elem.get_attribute('outerHTML')
            soup = bs(data, 'html.parser')

            # Unwanted element classes to be removed
            unwanted_classes = [
                "s-result-item s-widget s-widget-spacing-large AdHolder s-flex-full-width",
                "sg-col-20-of-24 s-result-item sg-col-0-of-12 sg-col-16-of-20 s-widget sg-col s-flex-geom s-widget-spacing-small sg-col-12-of-16",
                "sg-col-20-of-24 sg-col-16-of-20 sg-col sg-col-8-of-12 sg-col-12-of-16",
                "s-widget-container s-spacing-medium s-widget-container-height-medium celwidget slot=MAIN template=FEEDBACK widgetId=feedback"
            ]

            # Target product classes
            target_classes = [
                "sg-col-20-of-24 s-result-item s-asin sg-col-0-of-12 sg-col-16-of-20 AdHolder sg-col s-widget-spacing-small sg-col-12-of-16",
                "sg-col-20-of-24 s-result-item s-asin sg-col-0-of-12 sg-col-16-of-20 sg-col s-widget-spacing-small sg-col-12-of-16",
                "sg-col-4-of-24 sg-col-4-of-12 s-result-item s-asin sg-col-4-of-16 AdHolder sg-col s-widget-spacing-small sg-col-4-of-20",
                "sg-col-4-of-24 sg-col-4-of-12 s-result-item s-asin sg-col-4-of-16 sg-col s-widget-spacing-small sg-col-4-of-20",
                "sg-col-4-of-24 sg-col-4-of-12 s-result-item sg-col-4-of-16 sg-col sg-col-4-of-20"
            ]

            # Remove unwanted elements
            for class_name in unwanted_classes:
                for tag in soup.find_all("div", class_=class_name):
                    tag.decompose()

            # Extract product information
            for class_name in target_classes:
                products = soup.find_all("div", class_=class_name)
                for product in products:
                    product_details = {}


                    # Extract link internally (for navigation)
                    try:
                        link = product.find("a", class_="a-link-normal")["href"] or product.find("a", class_="a-link-normal s-no-outline")["href"]
                        product_details['link'] = f"https://www.amazon.in{link}"
                    except Exception:
                        product_details['link'] = None

                    # --- FIXED LOGIC: Always keep the link internally for navigation ---
                    navigate_link = product_details.get('link')  # Store the link for navigation

                    # Extract and add other fields based on user selection
                    if "image_url" in fields_to_scrape:
                        try:
                            img_tag = product.find("img", class_="s-image")
                            product_details['image_url'] = img_tag['src']
                            output_queue.put(f"Image found: {img_tag['src']}")
                        except Exception:
                            product_details['image_url'] = None


                    # Visit the product link to extract additional details
                    if navigate_link:
                        driver.get(navigate_link)
                        time.sleep(3)
                        product_page = bs(driver.page_source, 'html.parser')


                        # Extract product title
                        if "title" in fields_to_scrape:
                            try:
                                title = product_page.find("h1", id="title").get_text(strip=True)
                                output_queue.put(f"Title found: {title}")
                                product_details['title'] = title
                            except Exception:
                                product_details['title'] = None


                        # Extract pricing and discount information
                        if "discounted_price" in fields_to_scrape:
                            try:
                                discounted_price_text = product_page.find("div",
                                                                     class_="a-section a-spacing-none aok-align-center aok-relative").find(
                                    "span", class_="a-price-whole").get_text(strip=True)
                                discounted_price_string = discounted_price_text.replace("₹", "").replace(",", "").strip()
                                discounted_price = int(discounted_price_string)
                                output_queue.put(f"Discounted price: {discounted_price}")
                                product_details['discounted_price'] = discounted_price
                            except Exception:
                                product_details['discounted_price'] = None

                        if "original_price" in fields_to_scrape:
                            try:
                                original_price_text = product_page.find("div",
                                                                   class_="a-section a-spacing-small aok-align-center").find(
                                    "span", class_="a-offscreen").get_text(strip=True)
                                original_price_string = original_price_text.replace("₹", "").replace(",", "").strip()
                                original_price = int(original_price_string)
                                output_queue.put(f"Original price: {original_price}")
                                product_details['original_price'] = original_price
                            except Exception:
                                output_queue.put("Original Price is same as Discounted Price.")
                                if "discounted_price" in fields_to_scrape:
                                    product_details['original_price'] = product_details['discounted_price']
                                else:
                                    discounted_price_text = product_page.find("div",
                                                                              class_="a-section a-spacing-none aok-align-center aok-relative").find(
                                        "span", class_="a-price-whole").get_text(strip=True)
                                    if discounted_price_text:
                                        discounted_price_string = discounted_price_text.replace("₹", "").replace(",", "").strip()
                                        discounted_price = int(discounted_price_string)
                                        output_queue.put(f"Original Price: {discounted_price}")
                                        product_details['original_price'] = discounted_price
                                    else:
                                        product_details['original_price'] = None

                        if "discount_percentage" in fields_to_scrape:
                            try:
                                discount_percentage_text = product_page.find("div",
                                                                        class_="a-section a-spacing-none aok-align-center aok-relative").find(
                                    "span", class_="a-size-large a-color-price savingPriceOverride aok-align-center reinventPriceSavingsPercentageMargin savingsPercentage").get_text(strip=True)
                                discount_percentage = int(discount_percentage_text.replace("%", "").replace("-", "").strip())
                                product_details['discount_percentage'] = f"{discount_percentage}%"
                                output_queue.put(f"Discount percentage: {product_details['discount_percentage']}")
                            except Exception:
                                output_queue.put(f"Discount % is 0")
                                discount_percentage = 0
                                product_details['discount_percentage'] = f"{discount_percentage}%"


                        # Extract rating and reviews and last_month_sales
                        if "rating" in fields_to_scrape:
                            try:
                                rating_div = product_page.find("div", id="averageCustomerReviews_feature_div")
                                product_details['rating'] = rating_div.find("span",
                                                                            class_="a-size-base a-color-base").get_text(
                                    strip=True)
                                output_queue.put(f"Rating: {product_details['rating']}")
                            except Exception:
                                product_details['rating'] = None

                        if "reviews_count" in fields_to_scrape:
                            try:
                                rating_div = product_page.find("div", id="averageCustomerReviews_feature_div")
                                review_count_text = rating_div.find("a", class_="a-link-normal").get_text(strip=True)
                                review_count = review_count_text.replace(",", "").replace("ratings", "").strip()
                                product_details['reviews_count'] = review_count
                                output_queue.put(f"Reviews count: {product_details['reviews_count']}")
                            except Exception:
                                product_details['reviews_count'] = None

                        if "last_month_sales" in fields_to_scrape:
                            try:
                                sales_div = product_page.find("div", id="socialProofingAsinFaceout_feature_div")
                                if sales_div:
                                    sales_tag = sales_div.find("span", class_="a-text-bold").get_text(strip=True)
                                    sales = int(sales_tag.replace("+ bought", "").replace("K", "000").strip())
                                    product_details['last_month_sales'] = f"{sales}+"
                                    output_queue.put(f"Last month sales: {product_details['last_month_sales']}")
                                else:
                                    product_details['last_month_sales'] = None
                            except Exception:
                                product_details["last_month_sales"] = None


                        # Extract additional features from the table
                        if "additional_features" in fields_to_scrape:
                            try:
                                condition1_extracted = False

                                # Check for product info section
                                product_info = product_page.find("div",
                                                                 id="productDetails_feature_div") or product_page.find(
                                    "div", id="productDetailsWithModules_feature_div")

                                if product_info:
                                    detail_sections = product_info.find("div", class_="a-row a-spacing-top-base")

                                    # Condition 1: Extract two tables
                                    if detail_sections:
                                        output_queue.put("Found detail sections.")

                                        # Extracting 1st table
                                        section_1 = detail_sections.find("div", class_="a-column a-span6")
                                        if section_1:
                                            rows = section_1.find_all("div", class_="a-row a-spacing-base")
                                            if rows:
                                                table_1 = rows[0].find("table", class_="a-keyvalue prodDetTable")
                                                if table_1:
                                                    for row in table_1.find_all("tr"):
                                                        try:
                                                            key = row.find("th").get_text(strip=True)
                                                            raw_value = row.find("td").get_text(strip=True)
                                                            # cleaning the values
                                                            value = re.sub(r'[\n\r\t\u200e\u200f]', '',
                                                                           raw_value).replace('‏','').replace('‎', '').strip(': ')

                                                            product_details[key] = value
                                                            output_queue.put(f"{key}: {value}")
                                                            condition1_extracted = True
                                                        except Exception as e:
                                                            output_queue.put(f"Error extracting key-value from row: {e}")
                                                            continue
                                                else:
                                                    output_queue.put("Table_1 not found.")

                                        # Extracting 2nd table
                                        section_2 = detail_sections.find("div", class_="a-column a-span6 a-span-last")
                                        if section_2:
                                            rows = section_2.find_all("div", class_="a-row a-spacing-base")
                                            if rows:
                                                table_2 = rows[0].find("table", class_="a-keyvalue prodDetTable")
                                                if table_2:
                                                    for row in table_2.find_all("tr"):
                                                        try:
                                                            key = row.find("th").get_text(strip=True)
                                                            raw_value = row.find("td").get_text(strip=True)
                                                            # cleaning the values
                                                            value = re.sub(r'[\n\r\t\u200e\u200f]', '',
                                                                           raw_value).replace('‏', '').replace('‎','').strip(': ')

                                                            product_details[key] = value
                                                            output_queue.put(f"{key}: {value}")
                                                            condition1_extracted = True
                                                        except Exception as e:
                                                            output_queue.put(f"Error extracting key-value from row: {e}")
                                                            continue
                                                else:
                                                    output_queue.put("Table_2 not found.")

                                # Condition 2: If no data was extracted from Condition 1
                                if not condition1_extracted:
                                    section_1 = product_page.find("div", id="productFactsDesktop_feature_div")
                                    if section_1:
                                        rows = section_1.find_all("div",
                                                                  class_="a-fixed-left-grid product-facts-detail")
                                        for row in rows:
                                            try:
                                                key = row.find("div",
                                                               class_="a-fixed-left-grid-col a-col-left").get_text(
                                                    strip=True)
                                                value = row.find("div",
                                                                 class_="a-fixed-left-grid-col a-col-right").get_text(
                                                    strip=True)
                                                product_details[key] = value
                                                output_queue.put(f"{key}: {value}")
                                            except Exception as e:
                                                output_queue.put(f"Error extracting key-value from row: {e}")
                                                continue
                                    else:
                                        output_queue.put("Table_1 not found in condition 2.")

                                    # Extracting 2nd table
                                    section_2 = product_page.find("div", id="detailBullets_feature_div")
                                    if section_2:
                                        table_2 = section_2.find("ul",
                                                                 class_="a-unordered-list a-nostyle a-vertical a-spacing-none detail-bullet-list")
                                        if table_2:
                                            for row in table_2.find_all("li"):
                                                try:
                                                    raw_key = row.find("span", class_="a-text-bold").get_text(strip=True)
                                                    # Clean unwanted Unicode characters and extra spaces
                                                    key = re.sub(r'[\n\r\t\u200e\u200f]', '', raw_key).replace('‏',
                                                                                                               '').replace('‎', '').strip(': ')

                                                    raw_value = row.find_all("span")[-1].get_text(strip=True)
                                                    value = re.sub(r'[\n\r\t\u200e\u200f]', '', raw_value).replace('‏',
                                                                                                         '').replace('‎', '').strip(': ')

                                                    product_details[key] = value
                                                    output_queue.put(f"{key}: {value}")
                                                except Exception as e:
                                                    output_queue.put(f"Error extracting key-value from row: {e}")
                                                    continue
                                        else:
                                            output_queue.put("Table_2 not found in condition 2.")

                            except Exception as e:
                                output_queue.put(f"Error processing product details: {e}")
                                pass


                        driver.get(current_page_url)  # Reload the main page
                        time.sleep(2)


                    # Add the link to the output only if the user selected it
                    if "link" not in fields_to_scrape:
                        product_details.pop('link', None)


                    all_product_details.append(product_details)
                    product_count += 1
                    output_queue.put(f"{product_count} products scraped.")


            # Move to the next page if necessary
            if current_page < pages_to_scrape:
                next_button = driver.find_elements(By.CSS_SELECTOR, 'a.s-pagination-item.s-pagination-next.s-pagination-button.s-pagination-button-accessibility.s-pagination-separator')
                if next_button:
                    next_link = next_button[0].get_attribute('href')
                    driver.get(next_link)
                    current_page += 1
                else:
                    output_queue.put("No more pages available.")
                    break
            else:
                break


        # Save scraped data to a file
        platform = "amazon"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{platform}_{search_term}_{timestamp}"
        
        # Create filenames with respective extensions
        json_filename = f"{filename}.json"
        csv_filename = f"{filename}.csv"

        # Pass filenames to file_handler functions
        save_scraped_data(all_product_details, json_filename)
        convert_to_csv(all_product_details, csv_filename)

        output_queue.put("\n")
        output_queue.put(f"Scraping completed! Data saved to '{filename}'.")
        output_queue.put(f"Total products scraped: {len(all_product_details)}")


        # Generate visuals
        visuals, zip_filename = generate_visualizations(all_product_details, search_term, timestamp)
        
        
        # Step 6: Notify frontend
        output_queue.put(json.dumps({
            "type": "scrape_complete",
            "filenames": {
                "json": json_filename,
                "csv": csv_filename,
                "visualizations": visuals,
                "zip": zip_filename
            },
            "search_term": search_term,
            "timestamp": timestamp
        }))

    except Exception as e:
        output_queue.put(f"An error occurred: {e}")

    finally:
        allow_sleep()
        driver.quit()
        
