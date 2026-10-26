from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from database.db import get_service
from keyboards.inline import back_to_main_menu

router = Router()


class BookingStates(StatesGroup):
    choosing_date = State()
    entering_custom_date = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()
    entering_note = State()
    confirming = State()


@router.callback_query(F.data.startswith("book:start:"))
async def start_booking(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    service_id = int(callback.data.split(":")[2])
    service = await get_service(service_id)

    if not service:
        await callback.message.edit_text(
            "Услуга не найдена.",
            reply_markup=back_to_main_menu()
        )
        return

    await state.update_data(
        service_id=service["id"],
        service_title=service["title"],
        service_price=service["price"],
    )
    await state.set_state(BookingStates.choosing_date)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сегодня", callback_data="date:Сегодня")],
            [InlineKeyboardButton(text="Завтра", callback_data="date:Завтра")],
            [InlineKeyboardButton(text="На этой неделе", callback_data="date:На этой неделе")],
            [InlineKeyboardButton(text="Другая дата", callback_data="date:custom")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="book:cancel")],
        ]
    )

    await callback.message.edit_text(
        f"Вы выбрали: <b>{service['title']}</b>.\n\nКогда вам удобно?",
        reply_markup=keyboard
    )

@router.callback_query(BookingStates.choosing_date, F.data.startswith("date:"))
async def choose_date(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    date_choice = callback.data.split(":", 1)[1]

    if date_choice == "custom":
        await state.set_state(BookingStates.entering_custom_date)
        await callback.message.edit_text(
            "Введите дату в формате ДД.ММ.\n\nНапример: 28.10"
        )
        return

    await state.update_data(preferred_date=date_choice)
    await ask_time_slot(callback.message, state)


@router.message(BookingStates.entering_custom_date)
async def enter_custom_date(message: Message, state: FSMContext):
    date_text = message.text.strip()

    if len(date_text) != 5 or date_text[2] != ".":
        await message.answer(
            "Введите дату в формате ДД.ММ.\n\nНапример: 28.10"
        )
        return

    await state.update_data(preferred_date=date_text)
    await ask_time_slot(message, state)