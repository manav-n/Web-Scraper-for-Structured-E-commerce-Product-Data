import queue

# Global queues for communication
output_queue = queue.Queue()  # For scraper outputs to frontend
input_queue = queue.Queue()   # For frontend inputs to scraper