import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")
BASE_URL = os.getenv("BASE_URL")