from os import getenv
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = getenv("BOT_TOKEN")
OWNER_TELEGRAM = getenv("OWNER_TELEGRAM")
DATABASE_PATH = getenv("DATABASE_PATH", "bot.db")