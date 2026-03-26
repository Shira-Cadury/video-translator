import os
from dotenv import load_dotenv

load_dotenv()

MODEL_SIZE = os.getenv("MODEL_SIZE", "medium")
MAX_SUMMARY_SENTENCES = int(os.getenv("MAX_SUMMARY_SENTENCES", 10))
STORAGE_PATH = os.getenv("STORAGE_PATH", "storage")
LOG_FILE = os.getenv("LOG_FILE", "app.log")