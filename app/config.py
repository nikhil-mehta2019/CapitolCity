import os
from dotenv import load_dotenv

load_dotenv()

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")
BASE_URL = os.getenv("BASE_URL")