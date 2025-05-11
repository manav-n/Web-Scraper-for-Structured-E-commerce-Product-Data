from selenium import webdriver
from selenium.webdriver.common.by import By
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

      

def myntra_scrape():
    prevent_sleep()
    global original_price, discounted_price
    # Set up the driver
    driver = webdriver.Chrome()

    try:
        # Open Myntra homepage
        driver.get("https://www.myntra.com/")
        time.sleep(5)  # Allow time for the page to load

        output_queue.put("Please type your search query directly into the Myntra search box and press Enter.")
        output_queue.put("Once the search results have loaded, type 'ok' to proceed.")
        reply = input_queue.get().strip().lower() # Wait for user confirmation
        if reply != 'ok':
            output_queue.put("Scraping canceled by the user.")
            driver.quit()
            exit()
            

        # Extract the search term from the current URL
        search_url = driver.current_url
        if "/" not in search_url:
            raise ValueError("Search term not found in URL. Please try again.")

        search_term = search_url.split("/")[-1].split("?")[0].replace("-", "_")
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
            "9": "brand_name",
            "10": "seller_name",
            "11": "product_details",
            "12": "specifications"
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

        # Extract the maximum number of pages dynamically
        try:
            max_pages_elem = driver.find_element(By.CSS_SELECTOR,
                                                 "ul.pagination-container > li.pagination-paginationMeta")
            max_pages_text = max_pages_elem.text.strip()
            # Use regex to extract the last number from the text, removing commas
            max_pages = int(re.findall(r'\d+', max_pages_text.replace(",", ""))[-1])
        except Exception as e:
            max_pages = 1

        # Ask the user how many pages they want to scrape
        output_queue.put("\n")
        output_queue.put(f"How many pages do you want to scrape? (1-{max_pages}): ")
        pages_to_scrape = int(input_queue.get().strip())
        if pages_to_scrape < 1 or pages_to_scrape > max_pages:
            output_queue.put(
                f"Flipkart displays only {max_pages} pages for a keyword. Please provide a page number between 1 and {max_pages}.")
            driver.quit()
            exit()

        output_queue.put(f"Scraping data for {pages_to_scrape} pages...")


        product_count = 0
        current_page = 1  # Track the current page

        while current_page <= pages_to_scrape:
            time.sleep(5)
            current_page_url = driver.current_url  # Store the current page URL
            data = driver.page_source  # Get the entire page source
            soup = bs(data, 'html.parser')

            # Extract individual products
            product_sections = soup.find("ul", class_="results-base")
            product_list = product_sections.find_all("li", attrs={"id": True})

            for product in product_list:
                product_details = {}

                # Extract link internally (for navigation)
                try:
                    link = product.find("a", target="_blank")["href"]
                    product_details['link'] = f"https://www.myntra.com/{link}"

                except Exception:
                    product_details['link'] = None

                # --- FIXED LOGIC: Always keep the link internally for navigation ---
                navigate_link = product_details.get('link')  # Store the link for navigation

                # Visit the product link to extract additional details
                if navigate_link:
                    driver.get(navigate_link)
                    time.sleep(3)
                    product_page = bs(driver.page_source, 'html.parser')

                    # Extract image url
                    if "image_url" in fields_to_scrape:
                        try:
                            # Locate the first <div class="image-grid-col50"> inside <div class="image-grid-container common-clearfix">
                            image_grid_container = product_page.find("div",
                                                                     class_="image-grid-container common-clearfix")
                            if image_grid_container:
                                first_image_div = image_grid_container.find("div", class_="image-grid-col50")
                                if first_image_div:
                                    # Extract the style attribute
                                    style_attr = first_image_div.find("div", class_="image-grid-image").get("style")
                                    if style_attr:
                                        # Use regex to extract the URL from the style attribute
                                        match = re.search(r'url\("([^"]+\.(jpg|jpeg))"\)', style_attr)
                                        if match:
                                            image_url = match.group(1)  # Extracted URL
                                            product_details['image_url'] = image_url
                                            output_queue.put(f"Found image URL: {image_url}")
                                        else:
                                            product_details['image_url'] = None
                                            output_queue.put("No URL found in style attribute.")
                                    else:
                                        product_details['image_url'] = None
                                        output_queue.put("No style attribute found.")
                                else:
                                    product_details['image_url'] = None
                                    output_queue.put("No <div class='image-grid-col50'> found.")
                            else:
                                product_details['image_url'] = None
                                output_queue.put("No <div class='image-grid-container common-clearfix'> found.")
                        except Exception as e:
                            product_details['image_url'] = None
                            output_queue.put(f"Error extracting image URL: {e}")


                    # Extract product title
                    if "title" in fields_to_scrape:
                        try:
                            title = product_page.find("h1", class_="pdp-name").get_text(strip=True).replace("\xa0", " ")
                            output_queue.put(f"Found title: {title}")
                            product_details['title'] = title
                        except Exception:
                            product_details['title'] = None

                    # Extract pricing and discount information
                    if "discounted_price" in fields_to_scrape:
                        try:
                            discounted_price_text = product_page.find("span", class_="pdp-price").get_text(strip=True)
                            discounted_price_string = discounted_price_text.split(" ")[-1].replace("₹", "").strip()
                            discounted_price = int(discounted_price_string)      # convert string to float
                            output_queue.put(f"Found discounted price: {discounted_price}")
                            product_details['discounted_price'] = discounted_price
                        except Exception:
                            product_details['discounted_price'] = None

                    if "original_price" in fields_to_scrape:
                        try:
                            original_price_text = product_page.find("span", class_="pdp-mrp").find("s").get_text(strip=True)
                            original_price_string = original_price_text.replace("₹", "").strip()
                            original_price = int(original_price_string)       # convert string to float
                            output_queue.put(f"Found original price: {original_price}")
                            product_details['original_price'] = original_price
                        except Exception:
                            output_queue.put("Original Price is same as Discounted Price.")
                            if "discounted_price" in fields_to_scrape:
                                product_details['original_price'] = product_details['discounted_price']
                            else:
                                discounted_price_text = product_page.find("span", class_="pdp-price").get_text(strip=True)
                                if discounted_price_text:
                                    discounted_price_string = discounted_price_text.split(" ")[-1].replace("₹", "").strip()
                                    discounted_price = int(discounted_price_string)
                                    output_queue.put(f"Found original Price: {discounted_price}")
                                    product_details['original_price'] = discounted_price
                                else:
                                    product_details['original_price'] = None

                    if "discount_percentage" in fields_to_scrape:
                        try:
                            discount_percentage_text = product_page.find("span", class_="pdp-discount").get_text()

                            # Condition to handle "Rs." instead of a percentage
                            if "Rs." in discount_percentage_text:
                                try:
                                    # Calculate discount percentage
                                    discount_percentage = round(((original_price - discounted_price) / original_price) * 100)

                                except Exception as e:
                                    output_queue.put(f"Error calculating discount percentage: {e}")
                                    discount_percentage = 0        # Assign 0 as integer for consistent formatting
                                    product_details['discount_percentage'] = f"{discount_percentage}%"

                            else:
                                # Extract percentage directly if available
                                discount_percentage = int(discount_percentage_text.split(" ")[0].replace("(", "").replace("%", "").strip())

                            product_details['discount_percentage'] = f"{discount_percentage}%"
                            output_queue.put(f"Final discount percentage: {product_details['discount_percentage']}")

                        except Exception:
                            output_queue.put(f"Discount % is 0")
                            discount_percentage = 0
                            product_details['discount_percentage'] = f"{discount_percentage}%"


                    # Extract rating and reviews
                    if "rating" in fields_to_scrape:
                        try:
                            rating_text = product_page.find("div", class_="index-overallRating").get_text()
                            rating = rating_text.split("|")[0].strip()
                            output_queue.put(f"Found rating: {rating}")
                            product_details['rating'] = rating
                        except Exception:
                            product_details['rating'] = None

                    if "reviews_count" in fields_to_scrape:
                        try:
                            review_count_text = product_page.find("div", class_="index-ratingsCount").get_text()
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
                            brand_name = product_page.find("h1", class_="pdp-title").get_text(strip=True)
                            output_queue.put(f"Found brand_name: {brand_name}")
                            product_details['brand_name'] = brand_name
                        except Exception:
                            product_details['brand_name'] = None

                    # Extract seller's name
                    if "seller_name" in fields_to_scrape:
                        try:
                            seller_name = product_page.find("span", class_="supplier-productSellerName").get_text(
                                strip=True)
                            output_queue.put(f"Found seller_name: {seller_name}")
                            product_details['seller_name'] = seller_name
                        except Exception:
                            product_details['seller_name'] = None

                    # Extract product_details available on the product page
                    if "product_details" in fields_to_scrape:
                        try:
                            # Find the product description paragraph
                            product_det_tag = product_page.find("p", class_="pdp-product-description-content")
                            if product_det_tag:
                                # Replace <br> tags with newline characters
                                for br in product_det_tag.find_all("br"):
                                    br.insert_after("\n")  # Insert a newline after each <br>
                                    br.decompose()  # Remove the <br> tag itself

                                # Get the text without collapsing spaces
                                product_det = product_det_tag.get_text(separator=" ").replace("\xa0", " ").strip()
                                output_queue.put("Found product_details")
                                product_details['product_details'] = product_det
                            else:
                                product_details['product_details'] = None

                            # Check for additional details in <div class="pdp-sizeFitDesc">
                            size_fit_desc_divs = product_page.find_all("div", class_="pdp-sizeFitDesc")
                            for div in size_fit_desc_divs:
                                try:
                                    # Extract key from <h4> and value from <p>
                                    key_tag = div.find("h4",
                                                       class_="pdp-sizeFitDescTitle pdp-product-description-title")
                                    value_tag = div.find("p",
                                                         class_="pdp-sizeFitDescContent pdp-product-description-content")

                                    if key_tag and value_tag:
                                        # Replace <br> tags in value with newline characters
                                        for br in value_tag.find_all("br"):
                                            br.insert_after("\n")  # Insert a newline after each <br>
                                            br.decompose()  # Remove the <br> tag itself

                                        key = key_tag.get_text(strip=True)
                                        value = value_tag.get_text(separator=" ").replace("\xa0", " ").strip()

                                        # Add key-value pair directly to product_details dictionary
                                        product_details[key] = value
                                        output_queue.put(f"{key}: {value}")
                                except Exception as e:
                                    output_queue.put(f"Error processing additional detail div: {e}")
                                    continue  # Skip this div if there's an issue

                        except Exception as e:
                            output_queue.put(f"Error extracting product details: {e}")
                            product_details['product_details'] = None

                    # Extract additional product specifications from the product page
                    if "specifications" in fields_to_scrape:
                        try:
                            # Locate and click the "show more" button, if available
                            show_more_button = product_page.find("div", class_="index-showMoreText")
                            if show_more_button:
                                try:
                                    # Use Selenium to click on the button
                                    button_element = driver.find_element(By.CSS_SELECTOR, "div.index-showMoreText")
                                    driver.execute_script("arguments[0].click();",
                                                          button_element)  # Ensure the click happens
                                    time.sleep(2)  # Allow time for the second table to load

                                    # Wait explicitly for the second table to appear
                                    WebDriverWait(driver, 10).until(
                                        EC.presence_of_element_located(
                                            (By.CSS_SELECTOR, "div.index-sizeFitDesc > div > div.index-tableContainer"))
                                    )
                                except Exception as e:
                                    output_queue.put(f"Error clicking 'show more' button: {e}")

                            # Re-fetch the updated page source to include dynamically loaded content
                            product_page = bs(driver.page_source, 'html.parser')

                            # Locate the sizeFitDesc container
                            product_info_div = product_page.find("div", class_="index-sizeFitDesc")
                            if product_info_div:
                                # Find all table containers (before and after clicking "show more")
                                tables = product_info_div.find_all("div", class_="index-tableContainer")
                                for table in tables:
                                    # Extract rows from each table
                                    rows = table.find_all("div", class_="index-row")
                                    for row in rows:
                                        key_div = row.find("div", class_="index-rowKey")
                                        value_div = row.find("div", class_="index-rowValue")

                                        if key_div and value_div:
                                            # Extract key and value text
                                            key = key_div.get_text(strip=True).replace("\xa0", " ")
                                            value = value_div.get_text(strip=True).replace("\xa0", " ")
                                            product_details[key] = value
                                            output_queue.put(f"{key}: {value}")

                        except Exception as e:
                            output_queue.put(f"Error in extracting specifications: {e}")

                    # driver.get(current_page_url)    # This reloading of main page after every product is removed in our code because on myntra each page's url is exactly same and thus is causing problem in extraction and traversal.
                    time.sleep(2)

                # Add the link to the output only if the user selected it
                if "link" not in fields_to_scrape:
                    product_details.pop('link', None)


                all_product_details.append(product_details)
                product_count += 1
                output_queue.put(f"{product_count} products scraped.")


            # Move to the next page if necessary
            if current_page < pages_to_scrape:
                try:
                    # We are heading back to the current page url after extracting all products of that page is because all the pages url are same and going back after each product extraction will take us to the 1st page instead of current page.
                    # Reload the main page after processing product details
                    driver.get(current_page_url)
                    time.sleep(3)  # Allow sufficient time for the page to reload

                    current_page += 1

                    # Handle pagination by comparing current page to pagination meta text
                    while True:
                        try:
                            # Locate the pagination text to compare with the current page
                            pagination_meta = driver.find_element(By.CSS_SELECTOR,
                                                                  "ul.pagination-container > li.pagination-paginationMeta").text.strip()
                            output_queue.put(f"Pagination Meta: {pagination_meta}")

                            # Extract current page number from the text (e.g., Page 3 of 40)
                            current_page_text = int(re.findall(r'Page (\d+) of', pagination_meta)[0])

                            # If the current page matches the expected page, break the loop and scrape
                            if current_page_text == current_page:
                                output_queue.put(f"Scraping Page {current_page}...")
                                break
                            else:
                                # Click the "Next" button if the current page doesn't match
                                next_button = WebDriverWait(driver, 10).until(
                                    EC.element_to_be_clickable(
                                        (By.CSS_SELECTOR, "ul.pagination-container > li.pagination-next"))
                                )
                                next_button.click()
                                time.sleep(3)  # Allow the next page to load

                        except Exception as e:
                            output_queue.put(f"Error during pagination handling: {e}")
                            break

                except Exception as e:
                    output_queue.put(f"Error clicking next button: {e}")
                    break

            else:
                break

        # Save scraped data to a file
        platform = "myntra"
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
