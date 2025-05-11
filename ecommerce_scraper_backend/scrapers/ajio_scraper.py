from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup as bs
from datetime import datetime
import threading
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

       
        
def ajio_scrape():
    last_scrolled_position = 0  # Track the last scroll position
    product_count_ref = [0]  # Track the number of products scraped (mutable list)
    current_url = "https://www.ajio.com/"  # Initialize to homepage by default


    def initialize_driver():
        """Initialize the Selenium WebDriver with desired options."""
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--remote-debugging-port=9222")  # For debugging stability
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--remote-debugging-timeout=300000")  # Increase DevTools timeout to 5 mins

        return webdriver.Chrome(options=chrome_options)


    def reconnect_driver():
        """Reconnect the driver in case of a crash while preserving state."""
        global driver, last_scrolled_position, current_url

        try:
            driver.quit()  # Close the current session if active
        except Exception:
            pass  # Ignore errors if driver is already closed

        driver = initialize_driver()
        driver.get(current_url)  # Reconnect to the current page URL, not homepage
        time.sleep(5)

        # Scroll back to the last known position
        driver.execute_script(f"window.scrollTo(0, {last_scrolled_position});")
        time.sleep(3)

    def keep_browser_awake():
        """Simulate user activity without interfering with infinite scrolling."""
        while True:
            time.sleep(30)  # Perform action every 30 seconds
            try:
                # Perform a harmless click on the page to simulate user activity (on body or header)
                driver.execute_script("document.querySelector('body').click();")
            except WebDriverException:
                output_queue.put("Driver lost connection during keep-alive. Attempting to reconnect...")
                reconnect_driver()

    def detect_stall(product_count_ref):
        """Detect if the scraper is stuck by monitoring product count."""
        global last_scrolled_position, driver

        last_count = product_count_ref[0]

        while True:
            time.sleep(600)  # Check every 600 seconds
            if product_count_ref[0] == last_count:
                output_queue.put("Detected scraping stall. Refreshing the page...")
                driver.refresh()
                time.sleep(5)

                # Scroll gradually to load content
                new_product_count = 0
                scroll_pause_time = 2  # Wait between scrolls

                while new_product_count < last_count:
                    driver.execute_script("window.scrollBy(0, 800);")
                    time.sleep(scroll_pause_time)

                    # Parse the refreshed page and count products
                    soup = bs(driver.page_source, 'html.parser')
                    product_sections = soup.find_all("div", class_="item rilrtl-products-list__item item")
                    new_product_count = len(product_sections)
                    output_queue.put(f"Scrolled and loaded {new_product_count}/{last_count} products...")

                    if new_product_count >= last_count:
                        output_queue.put("Page recovered, continuing scraping...")
                        break

                last_scrolled_position = driver.execute_script("return window.scrollY;")
            last_count = product_count_ref[0]


    prevent_sleep()
    # Initialize the driver
    driver = initialize_driver()

    # Start background threads for keep-alive and stall detection
    threading.Thread(target=keep_browser_awake, daemon=True).start()
    threading.Thread(target=detect_stall, args=(product_count_ref,), daemon=True).start()


    try:
        # Open Ajio homepage
        driver.get("https://www.ajio.com/")
        time.sleep(5)  # Allow time for the page to load

        output_queue.put("Please type your search query directly into the Ajio search box and press Enter.")
        output_queue.put("Once the search results have loaded, type 'ok' to proceed.")
        reply = input_queue.get().strip().lower() # Wait for user confirmation
        if reply != 'ok':
            output_queue.put("Scraping canceled by the user.")
            driver.quit()
            exit()
            

        # Extract the search term from the current URL
        search_url = driver.current_url.strip()

        try:
            if "/s/" in search_url:  # Pattern 1: /s/{term}-{numbers}
                search_term = search_url.split("/s/")[1].split("?")[0]  # Isolate the part after "/s/" and before query parameters
                search_term = "-".join(search_term.split("-")[:-2]).replace("-",
                                                                            "_")  # Remove the last two numeric parts
            elif "/search/?text=" in search_url:  # Pattern 2: /search/?text={term}
                search_term = search_url.split("/search/?text=")[1].split("&")[0].replace("%20", "_")
            elif "/c/" in search_url:  # Pattern 3: /{term}/c/{number}
                search_term = search_url.split("/c/")[0].split("/")[-1].replace("-", "_")
            else:
                raise ValueError("Search term not found in URL. The URL pattern is unrecognized.")

            search_term = search_term[:30]  # Truncate search term to avoid long filenames
            output_queue.put(f"Extracted search term: {search_term}")

        except Exception as e:
            output_queue.put(f"Error extracting search term: {e}")
            search_term = None

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
            "9": "brand_name",
            "10": "product_specifications"
        }

        output_queue.put("\n")
        output_queue.put("Available fields to scrape:")
        for key, value in available_fields.items():
            output_queue.put(f"{key}. {value}")

        output_queue.put("\n")
        output_queue.put("Enter the numbers corresponding to the fields you want to scrape, separated by commas: ")
        selected_fields = input_queue.get()
        selected_fields = selected_fields.split(",")

        fields_to_scrape = [available_fields[field.strip()] for field in selected_fields if
                            field.strip() in available_fields]

        if not fields_to_scrape:
            output_queue.put("No valid fields selected. Exiting.")
            driver.quit()
            exit()

        output_queue.put(f"Fields selected for scraping: {fields_to_scrape}")

        # Extract the maximum number of items dynamically
        try:
            max_items_elem = driver.find_element(By.CSS_SELECTOR,
                                                 "div.filter-container > div.filter > div.length > strong")
            max_items_text = max_items_elem.text.strip()

            max_items = int("".join(re.findall(r'\d+', max_items_text)))  # Removes any commas and extracts digits
        except Exception as e:
            max_items = 0

        # Ask the user how many items they want to scrape
        output_queue.put("\n")
        output_queue.put(f"How many items do you want to scrape? (0-{max_items}): ")
        items_to_scrape = int(input_queue.get().strip())
        if items_to_scrape < 1 or items_to_scrape > max_items:
            output_queue.put(
                f"Ajio displays only {max_items} items for a keyword. Please provide an item number between 1 and {max_items}.")
            driver.quit()
            exit()

        output_queue.put(f"Scraping data for {items_to_scrape} items...")


        scraped_links = set()  # Store all the links

        while product_count_ref[0] < items_to_scrape:
            soup = bs(driver.page_source, 'html.parser')  # Parse the page
            # Extract product sections
            product_sections = soup.find_all("div", class_="item rilrtl-products-list__item item")

            if not product_sections:
                output_queue.put("No products found on the page. Exiting.")
                break

            # Iterate through products dynamically
            index = 0  # Reset index for each page load
            while index < len(product_sections) and product_count_ref[0] < items_to_scrape:
                product = product_sections[index]

                # Filter out unwanted sections based on 'style' attribute
                style_attr = product.get("style", "")
                if "height: 100px;" in style_attr:
                    output_queue.put("Skipped an ad banner.")
                    index += 1
                    continue  # Skip this iteration for ad banners

                # Scroll the next product into center view
                try:
                    product_elements = driver.find_elements(By.CSS_SELECTOR, "div.item.rilrtl-products-list__item.item")
                    if index >= len(product_elements):
                        output_queue.put(
                            f"Index {index} exceeds visible product count ({len(product_elements)}). Re-fetching elements...")
                        break  # Exit this loop to re-fetch elements after scrolling

                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});",
                                              product_elements[index])
                        time.sleep(2)  # Pause for lazy loading

                    except TimeoutException:
                        output_queue.put("Timeout while scrolling. Proceeding with the next product.")

                    # --- Force Populate Lazy Images ---
                    driver.execute_script("""
                        const lazyImages = document.querySelectorAll('img.rilrtl-lazy-img');
                        lazyImages.forEach(img => {
                            if (!img.src) {
                                if (img.dataset.src) img.src = img.dataset.src;  // Set from 'data-src'
                                else if (img.dataset.lazy) img.src = img.dataset.lazy;  // Set from 'data-lazy'
                                else if (img.dataset.original) img.src = img.dataset.original;  // Set from 'data-original'
                            }
                        });
                    """)
                    time.sleep(2)  # Allow time for JavaScript to execute

                except WebDriverException as e:
                    output_queue.put(f"Error scrolling to product at index {index}: {e}")
                    reconnect_driver()
                    continue

                product_details = {}

                # Extract and add other fields based on user selection
                try:
                    # Extract link internally (for navigation)
                    link = product.find("a")["href"]
                    full_link = f"https://www.ajio.com{link}"
                    if full_link in scraped_links:  # Prevent duplicates
                        continue
                    scraped_links.add(full_link)

                    driver.get(full_link)  # Navigate to product details page
                    current_url = full_link  # Update to product page URL
                    time.sleep(3)

                    # Only store link if the user selected it
                    if "link" in fields_to_scrape:
                        product_details['link'] = full_link

                    # Extract image url
                    if "image_url" in fields_to_scrape:
                        try:
                            img_element = driver.find_element(By.CSS_SELECTOR, "img.rilrtl-lazy-img")

                            image_url = (
                                    img_element.get_attribute("src") or
                                    img_element.get_attribute("data-src") or
                                    img_element.get_attribute("data-lazy") or
                                    img_element.get_attribute("data-original")
                            )
                            product_details["image_url"] = image_url if image_url else "URL not found"
                            output_queue.put(f"Found image URL: {product_details['image_url']}")
                        except Exception:
                            product_details['image_url'] = None

                    # Extract details from the product page
                    product_page = bs(driver.page_source, 'html.parser')

                    # Extract product title
                    if "title" in fields_to_scrape:
                        try:
                            title = product_page.find("h1", class_="prod-name").get_text(strip=True)
                            output_queue.put(f"Found title: {title}")
                            product_details['title'] = title
                        except Exception:
                            product_details['title'] = None

                    # Extract pricing and discount information
                    if "discounted_price" in fields_to_scrape:
                        try:
                            discounted_price_text = product_page.find("div", class_="prod-price-section").find("div",
                                                                                                          class_="prod-sp").get_text(strip=True)
                            if "MRP" in discounted_price_text:
                                discounted_price_string = discounted_price_text.replace("MRP₹", "").replace(",", "").strip()
                                discounted_price = int(discounted_price_string)
                            else:
                                discounted_price_string = discounted_price_text.replace("₹", "").replace(",", "").strip()
                                discounted_price = int(discounted_price_string)

                            output_queue.put(f"Found discounted price: {discounted_price}")
                            product_details['discounted_price'] = discounted_price
                        except Exception:
                            product_details['discounted_price'] = None

                    if "original_price" in fields_to_scrape:
                        try:
                            original_price_text = product_page.find("div", class_="prod-price-section").find("span",
                                                                                                        class_="prod-cp").get_text(strip=True)
                            if "MRP" in original_price_text:
                                original_price_string = original_price_text.replace("MRP₹", "").replace(",", "").strip()
                                original_price = int(original_price_string)
                            else:
                                original_price_string = original_price_text.replace("₹", "").replace(",", "").strip()
                                original_price = int(original_price_string)

                            output_queue.put(f"Found original price: {original_price}")
                            product_details['original_price'] = original_price
                        except Exception:
                            output_queue.put("Original Price is same as Discounted Price.")
                            if "discounted_price" in fields_to_scrape:
                                product_details['original_price'] = product_details['discounted_price']
                            else:
                                discounted_price_text = product_page.find("div", class_="prod-price-section").find(
                                    "div", class_="prod-sp").get_text(strip=True)
                                if discounted_price_text:
                                    if "MRP" in discounted_price_text:
                                        discounted_price_string = discounted_price_text.replace("MRP₹", "").replace(",", "").strip()
                                        discounted_price = int(discounted_price_string)
                                    else:
                                        discounted_price_string = discounted_price_text.replace("₹", "").replace(",", "").strip()
                                        discounted_price = int(discounted_price_string)
                                    output_queue.put(f"Found original Price: {discounted_price}")
                                    product_details['original_price'] = discounted_price
                                else:
                                    product_details['original_price'] = None

                    if "discount_percentage" in fields_to_scrape:
                        try:
                            discount_percentage_text = product_page.find("div", class_="prod-price-section").find(
                                "span", class_="prod-discnt").get_text()
                            discount_percentage_string = discount_percentage_text.split(" ")[0].replace("(", "").replace("%", "").strip()
                            discount_percentage = int(discount_percentage_string)
                            product_details['discount_percentage'] = f"{discount_percentage}%"
                            output_queue.put(f"Found discount percentage: {product_details['discount_percentage']}")
                        except Exception:
                            output_queue.put(f"Discount % is 0")
                            discount_percentage = 0
                            product_details['discount_percentage'] = f"{discount_percentage}%"

                    # Extract rating and reviews
                    if "rating" in fields_to_scrape:
                        try:
                            rating_review_div = product_page.find("div", class_="rating-popup")
                            section_div = rating_review_div.find("div", class_="_1jiCk _3iz7j")
                            rating = section_div.find("span", class_="_3c5q0").get_text(strip=True)
                            product_details['rating'] = rating
                            output_queue.put(f"Found rating: {rating}")
                        except Exception:
                            product_details['rating'] = None

                    if "reviews_count" in fields_to_scrape:
                        try:
                            review_div = product_page.find("div", class_="rating-popup")
                            section_div = review_div.find("div", class_="_1jiCk rating-label-star-count")
                            review_count_text = section_div.find("span", class_="_38RNg").get_text(strip=True)

                            # Check if the count contains 'k' (e.g., 16.2k)
                            if 'k' in review_count_text:
                                review_count_text = review_count_text.replace("Ratings", "").replace(",", "").strip()
                                # Handle decimal cases like '16.2k'
                                if '.' in review_count_text:
                                    # Split the number, convert to float, and multiply by 1000
                                    review_count = int(float(review_count_text.replace('k', '')) * 1000)
                                else:
                                    # Simple case (e.g., 4k -> 4000)
                                    review_count = int(review_count_text.replace('k', '')) * 1000
                            else:
                                # If no 'k' is present, just extract the number
                                review_count = int(review_count_text.replace("Ratings", "").replace(",", "").strip())

                            output_queue.put(f"Found reviews count: {review_count}")
                            product_details['reviews_count'] = review_count
                        except Exception:
                            product_details['reviews_count'] = None

                    # Extract brand's name
                    if "brand_name" in fields_to_scrape:
                        try:
                            brand_name = product_page.find("h2", class_="brand-name").get_text(strip=True)
                            output_queue.put(f"Found brand_name: {brand_name}")
                            product_details['brand_name'] = brand_name
                        except Exception:
                            product_details['brand_name'] = None

                    # Extract additional product specifications from the product page
                    if "product_specifications" in fields_to_scrape:
                        try:
                            # Wait for the 'more info' button to be present
                            more_info_button = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located(
                                    (By.CSS_SELECTOR,
                                     "section.prod-desc > h2 > ul.prod-list > li > div.other-info-toggle"))
                            )

                            # Scroll the button into view gradually (button is scrolled into centre of viewport)
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
                                                  more_info_button)
                            time.sleep(1)  # Allow for any animations

                            # Use JavaScript to perform the click
                            driver.execute_script("arguments[0].click();", more_info_button)
                            output_queue.put("Clicked on 'More Info' button.")
                            time.sleep(2)  # Allow time for content to load

                        except Exception as e:
                            output_queue.put(f"Error clicking 'more info' button: {e}")

                        # Re-fetch the updated page source to include dynamically loaded content
                        product_page = bs(driver.page_source, 'html.parser')

                        # Locate the prodDesc container
                        try:
                            product_info_div = product_page.find("section", class_="prod-desc")
                            if product_info_div:
                                output_queue.put("Found product info div")
                                try:
                                    prod_list = product_info_div.find("ul", class_="prod-list")
                                    list_items = prod_list.find_all("li", class_="detail-list")

                                    # Combine all the text from <li> tags with newline as separator
                                    general_specs = "\n".join(li.get_text(strip=True) for li in list_items)

                                    # Add to product_details dictionary
                                    product_details['general_specs'] = general_specs
                                    output_queue.put("Extracted general specifications.")

                                except Exception:
                                    product_details['general_specs'] = None

                                try:
                                    mandatory_list = product_page.find("ul", class_="prod-list")
                                    list_item = mandatory_list.find_all("div", class_="mandatory-list")

                                    for item in list_item:
                                        key_div = item.find("div", class_="info-label")
                                        value_div = item.find("div", class_="title")

                                        if key_div and value_div:
                                            # Extract key and value text
                                            key = key_div.get_text(strip=True).replace("\xa0", " ")
                                            value = value_div.get_text(strip=True).replace("\xa0", " ")
                                            product_details[key] = value
                                            output_queue.put(f"{key}: {value}")

                                except Exception as e:
                                    output_queue.put(f"Error adding extra specs: {e}")

                        except Exception as e:
                            output_queue.put("product specification tag not found")

                    all_product_details.append(product_details)
                    product_count_ref[0] += 1
                    output_queue.put(f"Product details of {product_count_ref[0]}/{items_to_scrape} scraped.")

                    # Break if we've scraped the required number of products
                    if product_count_ref[0] >= items_to_scrape:
                        break

                    driver.back()  # Go back to the main page
                    time.sleep(2)
                    current_url = driver.current_url  # Update to current main page URL

                except Exception as e:
                    output_queue.put(f"Error scraping product details: {e}")
                    reconnect_driver()
                    continue

                # Increment index for the next product
                index += 1

                # Incremental scrolling after every 3 products
                if product_count_ref[0] % 3 == 0:
                    product_elements = driver.find_elements(By.CSS_SELECTOR, "div.item.rilrtl-products-list__item.item")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});",
                                          product_elements[index + 1])
                    time.sleep(2)  # Pause for content to load
                    soup = bs(driver.page_source, 'html.parser')  # Update soup after scroll
                    product_sections = soup.find_all("div",
                                                     class_="item rilrtl-products-list__item item")  # Refresh the product list

            # Exit while loop if no new products are loaded
            if product_count_ref[0] >= items_to_scrape:
                break

        # Save scraped data to a file
        platform = "ajio"
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
        