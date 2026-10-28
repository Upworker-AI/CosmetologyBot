from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from datetime import datetime
from keyboards.inline import back_to_main_menu, date_keyboard
from config import OWNER_TELEGRAM_ID
from database.db import (
    get_service,
    get_or_create_client,
    get_client_telegram_id,
    create_booking_request,
    update_booking_status,
    get_client_by_telegram_id
)
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

    client = await get_client_by_telegram_id(callback.from_user.id)

    has_saved_contacts = (
        client is not None
        and client["full_name"] is not None
        and client["phone"] is not None
    )

    if has_saved_contacts:
        await state.update_data(
            name=client["full_name"],
            phone=client["phone"],
        )

    if service["category"] == "Курс":
        await state.update_data(
            preferred_date="Дата уточняется",
            preferred_time_slot="Дата уточняется",
        )

        if has_saved_contacts:
            await show_contact_confirmation(callback.message, state)
        else:
            await state.set_state(BookingStates.entering_name)
            await callback.message.answer("Как вас зовут?")

        return

    await state.set_state(BookingStates.choosing_date)
    await callback.message.edit_text(
        f"Вы выбрали: {service['title']}.\n\nКогда вам удобно?",
        reply_markup=date_keyboard()
    )

@router.callback_query(BookingStates.choosing_date, F.data.startswith("date:"))
async def choose_date(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    date_choice = callback.data.split(":", 1)[1]

    if date_choice == "custom":
        await state.set_state(BookingStates.entering_custom_date)
        await callback.message.edit_text(
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

    await message.edit_text(
        "Какой интервал вам подходит?",
        reply_markup=keyboard
    )


@router.callback_query(BookingStates.choosing_time, F.data.startswith("time:"))
async def choose_time(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    time_slot = callback.data.split(":", 1)[1]

    await state.update_data(preferred_time_slot=time_slot)

    data = await state.get_data()
    if data.get("name") and data.get("phone"):
        await show_contact_confirmation(callback.message, state)
    else:
        await state.set_state(BookingStates.entering_name)
        await callback.message.edit_text("Как вас зовут?")

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

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📱 Поделиться номером",
                    request_contact=True
                )
            ],
            [
                KeyboardButton(text="⌨️ Ввести номер вручную")
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(
        "Отправьте номер телефона.\n\n"
        "Нажмите кнопку ниже, чтобы поделиться номером из Telegram, "
        "или выберите «Ввести номер вручную».",
        reply_markup=keyboard
    )

@router.message(BookingStates.entering_phone, F.contact)
async def receive_contact_phone(message: Message, state: FSMContext):
    contact = message.contact

    if not contact or not contact.phone_number:
        await message.answer(
            "Не удалось получить номер. Попробуйте ещё раз "
            "или введите его вручную."
        )
        return

    phone = contact.phone_number

    await state.update_data(phone=phone)
    await state.set_state(BookingStates.entering_note)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏭ Пропустить",
                    callback_data="note:skip"
                )
            ]
        ]
    )

    sent_message = await message.answer(
        "Спасибо! Номер получен.\n\n"
        "Если у вас есть пожелания, аллергии или вопросы, напишите их здесь.",
        reply_markup=keyboard
    )
    await state.update_data(note_message_id=sent_message.message_id)

@router.message(BookingStates.entering_phone, F.text == "⌨️ Ввести номер вручную")
async def ask_manual_phone(message: Message):
    await message.answer(
        "Отправьте номер текстом.\n\nНапример: +7 800 555-35-35"
    )


@router.message(BookingStates.entering_phone, F.text)
async def enter_phone(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправьте номер телефона.")
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
            [
                InlineKeyboardButton(
                    text="⏭ Пропустить",
                    callback_data="note:skip"
                )
            ]
        ]
    )
    sent_message = await message.answer(
        "Спасибо! Номер получен.\n\n"
        "Если у вас есть пожелания, аллергии или вопросы, напишите их здесь.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.update_data(note_message_id=sent_message.message_id)
    await sent_message.edit_reply_markup(reply_markup=keyboard)

@router.message(BookingStates.entering_note)
async def enter_note(message: Message, state: FSMContext):
    note = (message.text or "").strip()
    await state.update_data(note=note)
    await show_confirmation(message, state)

@router.callback_query(BookingStates.entering_note,F.data == "note:skip")
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

    if data.get('preferred_date') == 'Дата уточняется' :
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить", callback_data="book:confirm")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data="book:cancel")],
            ]
        )
        note_message_id = data.get("note_message_id")

        if note_message_id:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=note_message_id,
                text=text,
                reply_markup=keyboard
            )
        else:
            await message.answer(text, reply_markup=keyboard)
    else:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="book:confirm")],
            [InlineKeyboardButton(text="✏️ Изменить дату", callback_data="book:back_date")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="book:cancel")],
            ]
        )
        note_message_id = data.get("note_message_id")

        if note_message_id:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=note_message_id,
                text=text,
                reply_markup=keyboard
            )
        else:
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

    client_id = await get_or_create_client(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=data.get("name"),
        phone=data.get("phone"),
    )

    booking_id = await create_booking_request(
        client_id=client_id,
        client_telegram_id=callback.from_user.id,
        service_id=data.get("service_id"),
        preferred_date=data.get("preferred_date"),
        preferred_time_slot=data.get("preferred_time_slot"),
        note=data.get("note"),
    )

    await state.clear()

    await callback.message.edit_text(
        "✅ <b>Заявка принята!</b>\n\n"
        f"Услуга: {data.get('service_title')}\n"
        f"Дата: {data.get('preferred_date')}\n"
        f"Время: {data.get('preferred_time_slot')}\n\n"
        "Мастер свяжется с вами для подтверждения."
    )
    await notify_owner(
        bot=callback.bot,
        booking_id=booking_id,
        data=data,
        callback=callback,
    )

async def notify_owner(bot, booking_id: int, data: dict, callback: CallbackQuery):
    if not OWNER_TELEGRAM_ID:
        return

    username = callback.from_user.username or "нет"
    note = data.get("note") or "нет"

    text = (
        f"🆕 <b>Новая заявка</b>\n\n"
        f"Услуга: <b>{data.get('service_title')}</b>\n"
        f"Цена: {data.get('service_price')}\n"
        f"Дата: {data.get('preferred_date')}\n"
        f"Время: {data.get('preferred_time_slot')}\n"
        f"Имя: {data.get('name')}\n"
        f"Телефон: {data.get('phone')}\n"
        f"Telegram: @{username}\n"
        f"Комментарий: {note}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"admin:confirm:{booking_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏁 Визит состоялся",
                    callback_data=f"admin:complete:{booking_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"admin:cancel:{booking_id}"
                )
            ],
        ]
    )

    try:
        await bot.send_message(
            chat_id=OWNER_TELEGRAM_ID,
            text=text,
            reply_markup=keyboard
        )
    except Exception as error:
        print(f"Не удалось отправить уведомление владельцу: {error}")

@router.callback_query(F.data.startswith("admin:confirm:"))
async def admin_confirm(callback: CallbackQuery):
    await callback.answer()

    booking_id = int(callback.data.split(":")[2])

    await update_booking_status(booking_id, "confirmed")

    await callback.message.edit_text(
        callback.message.html_text + "\n\n✅ <b>Заявка подтверждена.</b>",
        reply_markup=None
    )
    client_telegram_id = await get_client_telegram_id(booking_id)

    if client_telegram_id:
        await callback.bot.send_message(
            chat_id=client_telegram_id,
            text="✅ Ваша заявка подтверждена. Ждём вас!"
        )

@router.callback_query(F.data.startswith("admin:complete:"))
async def admin_complete(callback: CallbackQuery):
    await callback.answer()

    booking_id = int(callback.data.split(":")[2])

    await update_booking_status(booking_id, "completed")

    await callback.message.edit_text(
        callback.message.html_text + "\n\n🏁 <b>Визит состоялся.</b>",
        reply_markup=None
    )

@router.callback_query(F.data.startswith("admin:cancel:"))
async def admin_cancel(callback: CallbackQuery):
    await callback.answer()

    booking_id = int(callback.data.split(":")[2])

    await update_booking_status(booking_id, "cancelled")

    await callback.message.edit_text(
        callback.message.html_text + "\n\n❌ <b>Заявка отменена.</b>",
        reply_markup=None
    )

    client_telegram_id = await get_client_telegram_id(booking_id)

    if client_telegram_id:
        await callback.bot.send_message(
            chat_id=client_telegram_id,
            text="❌ К сожалению, ваша заявка была отменена. Свяжитесь с мастером, чтобы выбрать другое время."
        )

@router.callback_query(F.data == "admin:panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer("Доступ только для владельца.", show_alert=True)
        return

    await callback.answer()

    await callback.message.edit_text(
        "🛠 <b>Админ-панель</b>\n\n"
        "Здесь будут управление заявками, услугами и статистика.",
        reply_markup=back_to_main_menu()
    )


@router.callback_query(F.data == "contact:use_saved")
async def use_saved_contact(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    await state.set_state(BookingStates.entering_note)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏭ Пропустить",
                    callback_data="note:skip"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        "Контакты подтверждены!\n\n"
        "Если у вас есть пожелания, аллергии или вопросы, "
        "напишите их здесь.\n\n"
        "Или нажмите «Пропустить».",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "contact:enter_new")
async def enter_new_contact(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    await state.update_data(name=None, phone=None)
    await state.set_state(BookingStates.entering_name)

    await callback.message.edit_text("Как вас зовут?")

async def show_contact_confirmation(message: Message, state: FSMContext):
    data = await state.get_data()

    text = (
        "📋 <b>Ваши данные</b>\n\n"
        f"Имя: {data.get('name')}\n"
        f"Телефон: {data.get('phone')}\n\n"
        "Использовать эти данные для записи?"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, использовать",
                    callback_data="contact:use_saved"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Ввести новые",
                    callback_data="contact:enter_new"
                )
            ],
        ]
    )

    await message.edit_text(text, reply_markup=keyboard)