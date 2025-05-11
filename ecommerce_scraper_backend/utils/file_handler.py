import json
import pandas as pd
import os
from pathlib import Path

# Dynamically determine the user's Downloads directory
def get_download_path():
    return str(Path.home() / "Downloads")


DATA_DIR = get_download_path()

def save_scraped_data(data, filename):
    """
    Saves scraped data to a JSON file in the 'data' directory.
    
    :param data: Data to be saved
    :param filename: Output filename (with .json extension)
    :return: Full path of the saved JSON file
    """
    os.makedirs(DATA_DIR, exist_ok=True)  # Ensure the directory exists
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
    return filename

def convert_to_csv(data, filename):
    """
    Converts scraped data to CSV format and saves it in the 'data' directory.
    
    :param data: Data to be converted to CSV
    :param filename: Output filename (with .csv extension)
    :return: Full path of the saved CSV file
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, filename)
    pd.DataFrame(data).to_csv(filepath, index=False)
    return filename