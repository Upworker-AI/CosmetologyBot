from os import getenv
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = getenv("BOT_TOKEN")
OWNER_TELEGRAM_ID= int(getenv("OWNER_TELEGRAM_ID",0))
ADMIN_TELEGRAM = getenv("ADMIN_TELEGRAM")
DATABASE_PATH = getenv("DATABASE_PATH", "bot.db")