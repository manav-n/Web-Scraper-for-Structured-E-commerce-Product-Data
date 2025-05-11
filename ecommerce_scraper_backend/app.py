# app.py
from flask import Flask, jsonify, request, send_from_directory, send_file, Response
from scrapers.amazon_scraper import amazon_scrape
from scrapers.flipkart_scraper import flipkart_scrape
from scrapers.myntra_scraper import myntra_scrape
from scrapers.ajio_scraper import ajio_scrape
from utils.file_handler import save_scraped_data, convert_to_csv, DATA_DIR
from utils.visualization import generate_visualizations
from utils.terminal import output_queue, input_queue  # Import queues
import os
import threading
import datetime
import json
from pathlib import Path

app = Flask(__name__)

def stream_output():
    while True:
        output = output_queue.get()
        if output is None:
            break
        yield f"data: {output}\n\n"

# Track active scrapers to prevent duplicates
scraper_threads = {}

@app.route('/api/scrape/<platform>', methods=['POST'])
def scrape(platform):
    # Check if the scraper is already running
    if platform in scraper_threads and scraper_threads[platform].is_alive():
        return jsonify({"error": "Scraping in progress..."}), 409

    # Check request content type
    if not request.is_json:
        return jsonify({"error": "Unsupported Media Type"}), 415

    scraper_functions = {
        'amazon': amazon_scrape,
        'flipkart': flipkart_scrape,
        'myntra': myntra_scrape,
        'ajio': ajio_scrape
    }

    if platform not in scraper_functions:
        return jsonify({"error": "Invalid platform"}), 400

    # Clear queues
    with input_queue.mutex:
        input_queue.queue.clear()
    with output_queue.mutex:
        output_queue.queue.clear()

    # Start scraper in a new thread
    scraper_thread = threading.Thread(target=scraper_functions[platform], daemon=True)
    scraper_threads[platform] = scraper_thread
    scraper_thread.start()

    return jsonify({"status": "Scrape started"}), 200

@app.route('/api/input', methods=['POST'])
def handle_input():
    user_input = request.json.get('input')
    if user_input:
        input_queue.put(user_input)
        return jsonify({"status": "Input received"}), 200
    return jsonify({"error": "No input provided"}), 400

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    return send_from_directory(DATA_DIR, filename, as_attachment=True)

@app.route('/visualizations/<filename>', methods=['GET'])
def serve_visualizations(filename):
    return send_from_directory(str(Path.home() / "Downloads"), filename, as_attachment=True)

@app.route('/streamlit/<filename>', methods=['GET'])
def serve_streamlit(filename):
    return send_from_directory('streamlit', filename)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/favicon.png')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.png')

@app.route('/api/output')
def output():
    return Response(stream_output(), mimetype='text/event-stream')

# Handle file generation
@app.route('/api/generate-files', methods=['POST'])
def generate_files():
    data = request.json
    platform = data.get('platform')
    search_term = data.get('search_term')
    scraped_data = data.get('data')

    if not platform or not search_term or not scraped_data:
        return jsonify({"error": "Invalid input data"}), 400

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"{platform}_{search_term.replace(' ', '_')}_{timestamp}"

    # Generate file names
    json_filename = f"{base_filename}.json"
    csv_filename = f"{base_filename}.csv"

    save_scraped_data(scraped_data, json_filename)
    convert_to_csv(scraped_data, csv_filename)

    return jsonify({
        "jsonFileUrl": f"/download/{json_filename}",
        "csvFileUrl": f"/download/{csv_filename}"
    }), 200

# Handle visualization generation
@app.route('/api/generate-visualizations', methods=['POST'])
def generate_visualizations():
    data = request.json
    platform = data.get('platform')
    search_term = data.get('search_term')
    scraped_data = data.get('data')

    if not platform or not search_term or not scraped_data:
        return jsonify({"error": "Invalid input data"}), 400

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    visuals = generate_visualizations(scraped_data, search_term, timestamp)

    return jsonify({
        "visualizations": {
            "wordcloud": f"/visualizations/{visuals['wordcloud']}",
            "price_distribution": f"/visualizations/{visuals['price_distribution']}",
            "price_vs_ratings": f"/visualizations/{visuals['price_vs_ratings']}",
            "top_brands": f"/visualizations/{visuals['top_brands']}",
            "heatmap": f"/visualizations/{visuals['heatmap']}"
        }
    }), 200
    

# Handle Streamlit download
@app.route('/api/download-visualizations', methods=['POST'])
def download_visualizations():
    data = request.json
    search_term = data.get('search_term')
    timestamp = data.get('timestamp')

    if not search_term or not timestamp:
        return jsonify({"error": "Invalid input data"}), 400

    zip_filename = f"{search_term}_{timestamp}_visuals.zip"
    download_dir = str(Path.home() / "Downloads")
    zip_path = os.path.join(download_dir, zip_filename)
    if os.path.exists(zip_path):
        return send_file(zip_path, as_attachment=True, download_name=zip_filename)
    else:
        return jsonify({"error": "Visualizations ZIP file not found"}), 404


if __name__ == '__main__':
    app.run(debug=True)