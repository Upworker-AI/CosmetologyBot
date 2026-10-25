from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    FSInputFile
)
from forms.user import Form

router = Router()

@router.message(Command("start"))
async def start(message: Message):
    await message.answer(
        f"Привет, <b>{message.from_user.first_name}</b>! 👋\n\n"
        "Я бот студии «Название».\n\n"
        "<b>Здесь можно:</b>\n"
        "• посмотреть услуги и цены\n"
        "• оставить заявку на запись\n"
        "• найти адрес и часы работы\n\n"
        "Выберите раздел 👇",
        parse_mode="HTML"
    )