import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from config import BOT_TOKEN, OWNER_TELEGRAM_ID
from handlers.routes import router as main_router
from handlers.booking import router as booking_router
from handlers.errors import router as errors_router
from database.db import init_db

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()

async def set_commands(bot):
    default_commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="my_bookings", description="Мои записи"),
    ]

    owner_commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="my_bookings", description="Мои записи"),
        BotCommand(command="admin", description="Админ-панель"),
    ]

    await bot.set_my_commands(
        default_commands,
        scope=BotCommandScopeDefault()
    )

    await bot.set_my_commands(
        owner_commands,
        scope=BotCommandScopeChat(chat_id=OWNER_TELEGRAM_ID)
    )

async def main():
    logger.info("Инициализация базы данных...")
    await init_db()

    dp.include_router(main_router)
    dp.include_router(booking_router)
    dp.include_router(errors_router)
    logging.info("Запуск бота...")
    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())