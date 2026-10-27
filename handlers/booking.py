from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from datetime import datetime
from database.db import get_service
from keyboards.inline import back_to_main_menu, date_keyboard

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

    parts = callback.data.split(":")

    if len(parts) != 3 or not parts[2].isdigit():
        await callback.answer("Некорректная заявка")
        return

    service_id = int(parts[2])
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
    if service["category"] =="Курс":
        await state.update_data(
            preferred_date="Дата уточняется",
            preferred_time_slot="Дата уточняется",
        )

        await state.set_state(BookingStates.entering_name)
        await callback.message.answer("Как вас зовут?")
        return

    await state.set_state(BookingStates.choosing_date)
    await callback.message.edit_text(
        f"Вы выбрали: <b>{service['title']}</b>.\n\nКогда вам удобно?",
        reply_markup=date_keyboard()
    )

@router.callback_query(BookingStates.choosing_date, F.data.startswith("date:"))
async def choose_date(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    date_choice = callback.data.split(":", 1)[1]

    if date_choice == "custom":
        await state.set_state(BookingStates.entering_custom_date)
        await callback.message.answer(
            "Введите дату в формате ДД.ММ.\n\nНапример: 08.10"
        )
        return
    try:
        selected_date = datetime.strptime(date_choice, "%d.%m.%Y").date()
    except ValueError:
        await callback.message.edit_text(
            "Не удалось распознать дату. Выберите день из списка.",
            reply_markup=date_keyboard()
        )
        return

    await state.update_data(
        preferred_date=selected_date.strftime("%d.%m.%Y")
    )
    await ask_time_slot(callback.message, state)

@router.message(BookingStates.entering_custom_date)
async def enter_custom_date(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовым сообщением.")
        return
    date_text = message.text.strip()

    try:
        parsed_date = datetime.strptime(
            f"{date_text}.{datetime.now().year}",
            "%d.%m.%Y"
        )
    except ValueError:
        await message.answer(
            "Введите корректную дату в формате ДД.ММ.\n\n"
            "Например: 08.10"
        )
        return

    today = datetime.now().date()

    if parsed_date.date() < today:
        parsed_date = parsed_date.replace(year=today.year + 1)

    formatted_date = parsed_date.strftime("%d.%m.%Y")

    await state.update_data(preferred_date=formatted_date)
    await ask_time_slot(message, state)

async def ask_time_slot(message: Message, state: FSMContext):
    await state.set_state(BookingStates.choosing_time)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌅 Утро 08:00–13:00", callback_data="time:Утро 08–13:00")],
            [InlineKeyboardButton(text="☀️ День 13:00–17:00", callback_data="time:День 13:00–17:00")],
            [InlineKeyboardButton(text="🌆 Вечер 17:00–20:00", callback_data="time:Вечер 17:00–20:00")],
            [InlineKeyboardButton(text="⬅️ Изменить дату", callback_data="book:back_date")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="book:cancel")],
        ]
    )

    await message.answer(
        "Какой интервал вам подходит?",
        reply_markup=keyboard
    )


@router.callback_query(BookingStates.choosing_time, F.data.startswith("time:"))
async def choose_time(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    time_slot = callback.data.split(":", 1)[1]

    await state.update_data(preferred_time_slot=time_slot)
    await state.set_state(BookingStates.entering_name)

    await callback.message.answer("Как вас зовут?")

@router.message(BookingStates.entering_name)
async def enter_name(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовым сообщением.")
        return
    name = message.text.strip()

    if len(name) < 2:
        await message.answer("Введите имя хотя бы из двух символов.")
        return

    await state.update_data(name=name)
    await state.set_state(BookingStates.entering_phone)

    await message.answer(
        "Отправьте номер телефона.\n\nНапример: +7 800 555-35-35"
    )


@router.message(BookingStates.entering_phone)
async def enter_phone(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовым сообщением.")
        return
    phone = message.text.strip()
    digits = "".join(char for char in phone if char.isdigit())

    if len(digits) < 10:
        await message.answer(
            "Похоже, номер указан неверно.\n"
            "Отправьте номер минимум из 10 цифр."
        )
        return

    await state.update_data(phone=phone)
    await state.set_state(BookingStates.entering_note)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="note:skip")]
        ]
    )

    await message.answer(
        "Если у вас есть пожелания, аллергии или вопросы, пожалуйста, напишите об этом здесь!",
        reply_markup=keyboard
    )

@router.message(BookingStates.entering_note)
async def enter_note(message: Message, state: FSMContext):
    await state.update_data(note=message.text.strip())
    await show_confirmation(message, state)


@router.callback_query(BookingStates.entering_note, F.data == "note:skip")
async def skip_note(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(note="")
    await show_confirmation(callback.message, state)

async def show_confirmation(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(BookingStates.confirming)

    text = (
        "📋 <b>Проверьте заявку</b>\n\n"
        f"Услуга: <b>{data.get('service_title')}</b>\n"
        f"Цена: {data.get('service_price')}\n"
        f"Дата: {data.get('preferred_date')}\n"
        f"Время: {data.get('preferred_time_slot')}\n"
        f"Имя: {data.get('name')}\n"
        f"Телефон: {data.get('phone')}\n"
        f"Комментарий: {data.get('note') or 'нет'}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="book:confirm")],
            [InlineKeyboardButton(text="✏️ Изменить дату", callback_data="book:back_date")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="book:cancel")],
        ]
    )

    await message.answer(text, reply_markup=keyboard)

@router.callback_query(F.data == "book:cancel")
async def cancel_booking(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Заявка отменена")
    await state.clear()

    await callback.message.edit_text(
        "Заявка отменена. Если передумаете — нажмите «Записаться» в главном меню.",
        reply_markup=back_to_main_menu()
    )


@router.callback_query(F.data == "book:back_date")
async def back_to_date(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(BookingStates.choosing_date)

    await callback.message.edit_text(
        "Когда вам удобно?",
        reply_markup=date_keyboard()
    )

@router.callback_query(BookingStates.confirming, F.data == "book:confirm")
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    await state.clear()

    await callback.message.edit_text(
        "✅ <b>Заявка принята!</b>\n\n"
        f"Услуга: {data.get('service_title')}\n"
        f"Дата: {data.get('preferred_date')}\n"
        f"Время: {data.get('preferred_time_slot')}\n\n"
        "Мастер свяжется с вами для подтверждения."
    )