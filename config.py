import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

UPI_ID = os.getenv("UPI_ID", "")
UPI_NAME = os.getenv("UPI_NAME", "Voucher Store")

SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "")

REQUIRED_CHANNELS = [
    x.strip()
    for x in os.getenv("REQUIRED_CHANNELS", "").split(",")
    if x.strip()
]

REFERRAL_REWARD = int(os.getenv("REFERRAL_REWARD", "10"))
