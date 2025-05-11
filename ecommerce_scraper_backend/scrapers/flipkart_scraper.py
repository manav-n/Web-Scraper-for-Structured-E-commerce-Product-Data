from selenium import webdriver
from selenium.webdriver.common.by import By
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
    matplotlib.use('Agg')  # Use Agg for headless system
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



def flipkart_scrape():
    prevent_sleep()
    # Set up the driver
    driver = webdriver.Chrome()

    try:
        # Open Flipkart homepage
        driver.get("https://www.flipkart.com/")
        time.sleep(5)  # Allow time for the page to load

        output_queue.put("Please type your search query directly into the Flipkart search box and press Enter.")
        output_queue.put("Once the search results have loaded, type 'ok' to proceed.")
        reply = input_queue.get().strip().lower() # Wait for user confirmation
        if reply != 'ok':
            output_queue.put("Scraping canceled by the user.")
            driver.quit()
            exit()
    

        # Extract the search term from the current URL
        search_url = driver.current_url

        try:
            if "q=" in search_url:
                search_term = search_url.split("q=")[1].split("&")[0].replace("%20", "_").replace("+", "_")
            elif "/pr" in search_url:
                search_term = search_url.split("/pr")[0].split("/")[-1].replace("-", "_")
            else:
                raise ValueError("Search term not found in URL. Please try again.")

            search_term = search_term[:30]  # Truncate search term to avoid long filenames

        except Exception as e:
            output_queue.put(f"An error occurred: {e}")
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
            "8": "ratings_&_reviews_count",
            "9": "seller_name",
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

        # Extract the maximum number of pages dynamically
        try:
            max_pages_elem = driver.find_element(By.CSS_SELECTOR, "div._1G0WLw > span")
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


        product_count = 0   # Track number of products
        current_page = 1  # Track the current page


        while current_page <= pages_to_scrape:
            time.sleep(5)
            current_page_url = driver.current_url  # Store the current page URL
            data = driver.page_source  # Get the entire page source
            soup = bs(data, 'html.parser')

            # Extract product sections only if they contain <div class="_75nlfW">
            product_sections = soup.find_all("div", class_="cPHDOP col-12-12")
            for section in product_sections:
                # Find all <div class="_75nlfW"> and <div class="_75nlfW LYgYA3">
                product_containers = section.find_all("div", class_=["_75nlfW", "_75nlfW LYgYA3"])

                # Iterate through each product container
                for container in product_containers:
                    # Find all <div> tags inside the container that have the "data-id" attribute
                    product_divs = container.find_all("div", attrs={"data-id": True})

                    for product in product_divs:
                        product_details = {}

                        # Extract link internally (for navigation)
                        try:
                            link = product.find("a", target="_blank")["href"]
                            product_details['link'] = f"https://www.flipkart.com{link}"

                        except Exception:
                            product_details['link'] = None

                        # --- FIXED LOGIC: Always keep the link internally for navigation ---
                        navigate_link = product_details.get('link')  # Store the link for navigation

                        # Extract and add other fields based on user selection
                        if "image_url" in fields_to_scrape:
                            try:
                                img_tag = product.find("img", class_="_53J4C-") or product.find("img", class_="DByuf4")
                                product_details['image_url'] = img_tag['src']
                                output_queue.put(f"Image found: {product_details['image_url']}")
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
                                    title = product_page.find("div", class_="C7fEHH").find("span",
                                                                                           class_="VU-ZEz").get_text(
                                        strip=True).replace("\xa0", " ")
                                    output_queue.put(f"Title: {title}")
                                    product_details['title'] = title
                                except Exception:
                                    product_details['title'] = None

                            # Extract pricing and discount information
                            if "discounted_price" in fields_to_scrape:
                                try:
                                    price_div = product_page.find("div", class_="C7fEHH")
                                    section_div = price_div.find("div", class_="x+7QT1") or price_div.find("div",
                                                                                                           class_="x+7QT1 dB67CR")
                                    discounted_price_text = section_div.find("div", class_="Nx9bqj CxhGGd").get_text(strip=True)
                                    discounted_price_string = discounted_price_text.replace("₹", "").replace(",", "").strip()
                                    discounted_price = int(discounted_price_string)
                                    output_queue.put(f"Discounted price: {discounted_price}")
                                    product_details['discounted_price'] = discounted_price
                                except Exception:
                                    product_details['discounted_price'] = None

                            if "original_price" in fields_to_scrape:
                                try:
                                    price_div = product_page.find("div", class_="C7fEHH")
                                    section_div = price_div.find("div", class_="x+7QT1") or price_div.find("div",
                                                                                                           class_="x+7QT1 dB67CR")
                                    original_price_text = section_div.find("div", class_="yRaY8j A6+E6v").get_text(strip=True)
                                    original_price_string = original_price_text.replace("₹", "").replace(",", "").strip()
                                    original_price = int(original_price_string)
                                    output_queue.put(f"Original price: {original_price}")
                                    product_details['original_price'] = original_price
                                except Exception:
                                    output_queue.put("Original Price is same as Discounted Price.")
                                    if "discounted_price" in fields_to_scrape:
                                        product_details['original_price'] = product_details['discounted_price']
                                    else:
                                        # If discounted price isn't selected, attempt to scrape it directly
                                        price_div = product_page.find("div", class_="C7fEHH")
                                        section_div = price_div.find("div", class_="x+7QT1") or price_div.find("div", class_="x+7QT1 dB67CR")

                                        if section_div:  # Ensure section_div exists before proceeding
                                            try:
                                                discounted_price_text = section_div.find("div", class_="Nx9bqj CxhGGd").get_text(strip=True)
                                                discounted_price_string = discounted_price_text.replace("₹", "").replace(",", "").strip()
                                                discounted_price = int(discounted_price_string)
                                                output_queue.put(f"Original Price (from discount price): {discounted_price}")
                                                product_details['original_price'] = discounted_price
                                            except Exception:
                                                product_details['original_price'] = None
                                        else:
                                            product_details['original_price'] = None

                            if "discount_percentage" in fields_to_scrape:
                                try:
                                    price_div = product_page.find("div", class_="C7fEHH")
                                    section_div = price_div.find("div", class_="x+7QT1") or price_div.find("div",
                                                                                                           class_="x+7QT1 dB67CR")
                                    discount_percentage_text = (section_div.find("div", class_="UkUFwK WW8yVX dB67CR")
                                                                or section_div.find("div", class_="UkUFwK WW8yVX")).get_text(strip=True)
                                    discount_percentage = int(discount_percentage_text.replace(f"% off", "").strip())
                                    product_details['discount_percentage'] = f"{discount_percentage}%"
                                    output_queue.put(f"Discount percentage: {product_details['discount_percentage']}")
                                except Exception:
                                    output_queue.put(f"Discount % is 0")
                                    discount_percentage = 0
                                    product_details['discount_percentage'] = f"{discount_percentage}%"


                            # Extract rating and reviews
                            if "rating" in fields_to_scrape:
                                try:
                                    rating_review_div = product_page.find("div", class_="C7fEHH")
                                    section_div = rating_review_div.find("div", class_="ISksQ2")
                                    rating = (section_div.find("div", class_="XQDdHH _1Quie7")
                                              or section_div.find("div", class_="XQDdHH")).get_text(strip=True)
                                    output_queue.put(f"Rating: {rating}")
                                    product_details['rating'] = rating
                                except Exception:
                                    product_details['rating'] = None

                            if "ratings_&_reviews_count" in fields_to_scrape:
                                try:
                                    rating_review_div = product_page.find("div", class_="C7fEHH")
                                    section_div = rating_review_div.find("div", class_="ISksQ2")
                                    spans = section_div.find("span", class_="Wphh3N").get_text(strip=True)

                                    # Initialize defaults
                                    rating_count = 0
                                    review_count = 0

                                    # Attempt to split by '&' or 'and'
                                    parts = spans.split("&")
                                    if len(parts) < 2:  # If '&' split fails, try 'and'
                                        parts = spans.split("and")

                                    # Extract rating and review counts
                                    if len(parts) > 0:
                                        rating_count = parts[0].replace("ratings", "").replace("Ratings", "").replace(
                                            ",", "").strip()
                                    if len(parts) > 1:
                                        review_count = parts[1].replace("reviews", "").replace("Reviews", "").replace(
                                            ",", "").strip()

                                    # output_queue.put and store the extracted values
                                    output_queue.put(f"rating count: {rating_count}")
                                    output_queue.put(f"reviews count: {review_count}")

                                    # Store in product details
                                    product_details['rating_count'] = rating_count
                                    product_details['reviews_count'] = review_count

                                except Exception as e:
                                    output_queue.put(f"Error extracting rating/reviews count: {e}")
                                    product_details['rating_count'] = None
                                    product_details['reviews_count'] = None


                            # Extract seller's name
                            if "seller_name" in fields_to_scrape:
                                try:
                                    seller_tag = product_page.find("div", id="sellerName")
                                    seller_name = seller_tag.contents[0].find("span").text.strip()
                                    output_queue.put(f"Seller_name: {seller_name}")
                                    product_details['seller_name'] = seller_name
                                except Exception:
                                    product_details['seller_name'] = None

                            # Extract additional product specifications from the product page
                            if "product_specifications" in fields_to_scrape:
                                # Flag to check if data was extracted using Condition 1
                                condition1_extracted = False

                                try:
                                    # Condition 1: <div class="_5Pmv5S">
                                    product_info_div = product_page.find("div", class_="_5Pmv5S")
                                    if product_info_div:
                                        output_queue.put("Found product details in condition 1 format.")
                                        rows = product_info_div.find("div", class_="row _1IK+Dg").find_all("div",
                                                                                                           class_="row")
                                        for row in rows:
                                            key_div = row.find("div", class_="col col-3-12 _9NUIO9")
                                            value_div = row.find("div", class_="col col-9-12 -gXFvC")

                                            if key_div and value_div:
                                                key = key_div.get_text(strip=True).replace("\xa0", " ")
                                                value = value_div.get_text(strip=True).replace("\xa0", " ")
                                                product_details[key] = value
                                                output_queue.put(f"{key}: {value}")
                                                condition1_extracted = True  # Set the flag to True if details are extracted

                                except Exception as e:
                                    output_queue.put(f"Error in extracting details using condition 1: {e}")

                                try:
                                    # Condition 2: <div class="_3Fm-hO">
                                    if not condition1_extracted:  # Only check if condition 1 didn't yield results
                                        product_info_div = product_page.find("div", class_="_3Fm-hO")
                                        if product_info_div:
                                            output_queue.put("Found product details in condition 2 format.")
                                            sections = product_info_div.find_all("div", class_="GNDEQ-")
                                            for sect in sections:
                                                table = sect.find('table', class_="_0ZhAN9")
                                                rows = table.find_all("tr", class_="WJdYP6 row")
                                                for row in rows:
                                                    key_td = row.find("td", class_="+fFi1w col col-3-12")
                                                    value_td = row.find("td", class_="Izz52n col col-9-12")

                                                    if key_td and value_td:
                                                        key = key_td.get_text(strip=True).replace("\xa0", " ")
                                                        value = value_td.get_text(strip=True).replace("\xa0", " ")
                                                        product_details[key] = value
                                                        output_queue.put(f"{key}: {value}")

                                except Exception as e:
                                    output_queue.put(f"Error in extracting details using condition 2: {e}")

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
                try:
                    next_buttons = driver.find_elements(By.CSS_SELECTOR, 'nav.WSL9JP > a._9QVEpD')

                    if len(next_buttons) == 1:  # First page: only one button (Next button)
                        next_link = next_buttons[0].get_attribute('href')

                    elif len(next_buttons) == 2:  # From the second page onwards: take the second button
                        next_link = next_buttons[1].get_attribute('href')

                    else:
                        output_queue.put("No more pages available.")
                        break

                    driver.get(next_link)  # Navigate to the next page
                    current_page += 1
                except Exception as e:
                    output_queue.put(f"Error navigating to the next page: {e}")
                    break
            else:
                break

        # Save scraped data to a file
        platform = "flipkart"
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
