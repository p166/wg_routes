import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
env_file = Path(__file__).parent / ".env"
load_dotenv(env_file)

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# SSH
SSH_HOST = os.getenv("SSH_HOST")
SSH_PORT = int(os.getenv("SSH_PORT", 22))
SSH_USER = os.getenv("SSH_USER")
SSH_KEY_PATH = os.path.expanduser(os.getenv("SSH_KEY_PATH"))

# S1 paths
S1_WG_DESTINATIONS_PATH = os.getenv("S1_WG_DESTINATIONS_PATH", "wg_destinations.txt")
S1_WG_V6_ROUTES_PATH = os.getenv("S1_WG_V6_ROUTES_PATH", "wg_v6_routes.txt")
S1_UPDATE_SCRIPT_PATH = os.getenv("S1_UPDATE_SCRIPT_PATH")

# DNS
DNS_TIMEOUT = int(os.getenv("DNS_TIMEOUT", 5))
DNS_SERVER = os.getenv("DNS_SERVER", "8.8.8.8")

# Admin
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
if ADMIN_USER_ID:
    ADMIN_USER_ID = int(ADMIN_USER_ID)

# Validation
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env file")
if not all([SSH_HOST, SSH_USER, SSH_KEY_PATH]):
    raise ValueError("SSH configuration is incomplete in .env file")
