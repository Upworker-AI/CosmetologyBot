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
from datetime import datetime, timedelta
from keyboards.inline import back_to_main_menu, date_keyboard, admin_menu_keyboard, admin_booking_keyboard
from config import OWNER_TELEGRAM_ID
from database.db import (
    get_service,
    get_or_create_client,
    get_client_telegram_id,
    create_booking_request,
    update_booking_status,
    get_client_by_telegram_id,
    get_admin_bookings,
    get_admin_booking_details,
    get_admin_services,
    get_available_slots
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

class AdminFilterStates(StatesGroup):
    entering_date = State()

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
    await ask_time_slot(
    callback.message,
    state,
    edit_message=True
)

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


async def ask_time_slot(
    message: Message,
    state: FSMContext,
    edit_message: bool = False
):
    data = await state.get_data()

    selected_date = data.get("preferred_date")
    service_id = data.get("service_id")

    slots = await get_available_slots(
        selected_date=selected_date,
        service_id=service_id
    )

    if not slots:
        await state.set_state(BookingStates.choosing_date)

        text = (
            f"На {selected_date} свободного времени нет.\n\n"
            "Выберите другую дату."
        )

        if edit_message:
            await message.edit_text(
                text,
                reply_markup=date_keyboard()
            )
        else:
            await message.answer(
                text,
                reply_markup=date_keyboard()
            )
        return

    await state.set_state(BookingStates.choosing_time)

    buttons = []

    for i in range(0, len(slots), 2):
        row = [
            InlineKeyboardButton(
                text=slot,
                callback_data=f"time:{slot}"
            )
            for slot in slots[i:i + 2]
        ]
        buttons.append(row)

    buttons.extend([
        [
            InlineKeyboardButton(
                text="⬅️ Изменить дату",
                callback_data="book:back_date"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data="book:cancel"
            )
        ]
    ])

    text = (
        f"📅 Дата: {selected_date}\n\n"
        "Выберите свободное время:"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    if edit_message:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)



@router.callback_query(
    BookingStates.choosing_time,
    F.data.startswith("time:")
)
async def choose_time(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    start_time = callback.data.split(":", 1)[1]
    data = await state.get_data()

    # Повторно проверяем, что выбранное время ещё свободно.
    slots = await get_available_slots(
        selected_date=data.get("preferred_date"),
        service_id=data.get("service_id")
    )

    if start_time not in slots:
        await callback.message.edit_text(
            "Это время уже недоступно. Выберите другое.",
        )
        await ask_time_slot(callback.message, state, edit_message=True)
        return

    service = await get_service(data.get("service_id"))

    if not service:
        await callback.message.edit_text("Услуга не найдена.")
        await state.clear()
        return

    start_dt = datetime.strptime(start_time, "%H:%M")
    end_dt = start_dt + timedelta(
        minutes=service["duration_minutes"]
    )

    end_time = end_dt.strftime("%H:%M")

    await state.update_data(
        start_time=start_time,
        end_time=end_time,
        preferred_time_slot=f"{start_time}–{end_time}"
    )

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
        "Если у вас есть пожелания, аллергии или вопросы, напишите их здесь.",
        reply_markup=keyboard
    )
    await state.update_data(note_message_id=sent_message.message_id)

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

    try:
        booking_id = await create_booking_request(
            client_id=client_id,
            client_telegram_id=callback.from_user.id,
            service_id=data.get("service_id"),
            preferred_date=data.get("preferred_date"),
            preferred_time_slot=data.get("preferred_time_slot"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            note=data.get("note"),
        )

    except ValueError as error:
        if "Это время уже занято" in str(error):
            # Слот заняли до подтверждения заявки.
            await state.update_data(
                start_time=None,
                end_time=None,
                preferred_time_slot=None,
            )

            await ask_time_slot(
                callback.message,
                state,
                edit_message=True,
            )
        else:
            await callback.message.edit_text(
                f"Не удалось оформить запись: {error}"
            )

        return

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
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    booking_id = int(callback.data.split(":")[2])
    booking = await get_admin_booking_details(booking_id)

    if not booking:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    if booking["status"] != "new":
        await callback.answer("Заявка уже обработана.", show_alert=True)
        return

    await update_booking_status(booking_id, "confirmed")
    await callback.answer("Заявка подтверждена!")

    booking = await get_admin_booking_details(booking_id)

    text = (
        f"📋 <b>Заявка #{booking['id']}</b>\n\n"
        f"Статус: <b>{booking['status']}</b>\n"
        f"Услуга: {booking['service_title']}\n"
        f"Категория: {booking['service_category']}\n"
        f"Цена: {booking['service_price']}\n"
        f"Длительность: {booking['duration_minutes']} мин.\n\n"
        f"📅 Дата: {booking['preferred_date']}\n"
        f"🕒 Интервал: {booking['preferred_time_slot']}\n\n"
        f"👤 Клиент: {booking['full_name'] or 'не указано'}\n"
        f"📞 Телефон: {booking['phone'] or 'не указан'}\n"
        f"💬 Комментарий: {booking['note'] or 'нет'}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_booking_keyboard(
            booking_id=booking_id,
            status=booking["status"]
        )
    )

    client_telegram_id = await get_client_telegram_id(booking_id)

    if client_telegram_id:
        await callback.bot.send_message(
            chat_id=client_telegram_id,
            text="✅ Ваша заявка подтверждена. Ждём вас!"
        )


@router.callback_query(F.data.startswith("admin:complete:"))
async def admin_complete(callback: CallbackQuery):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    await callback.answer()

    booking_id = int(callback.data.split(":")[2])

    await update_booking_status(booking_id, "completed")

    await callback.message.edit_text(
        callback.message.html_text + "\n\n🏁 <b>Визит состоялся.</b>",
        reply_markup=None
    )


@router.callback_query(F.data.startswith("admin:cancel:"))
async def admin_cancel(callback: CallbackQuery):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    booking_id = int(callback.data.split(":")[2])
    booking = await get_admin_booking_details(booking_id)

    if not booking:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    if booking["status"] in ("cancelled", "completed"):
        await callback.answer(
            "Эта заявка уже обработана.",
            show_alert=True
        )
        return

    await update_booking_status(booking_id, "cancelled")
    await callback.answer("Заявка отменена!")

    booking = await get_admin_booking_details(booking_id)

    text = (
        f"📋 <b>Заявка #{booking['id']}</b>\n\n"
        f"Статус: <b>{booking['status']}</b>\n"
        f"Услуга: {booking['service_title']}\n"
        f"📅 Дата: {booking['preferred_date']}\n"
        f"🕒 Интервал: {booking['preferred_time_slot']}\n"
        f"👤 Клиент: {booking['full_name'] or 'не указано'}\n"
        f"📞 Телефон: {booking['phone'] or 'не указан'}\n"
        f"💬 Комментарий: {booking['note'] or 'нет'}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_booking_keyboard(
            booking_id=booking_id,
            status=booking["status"]
        )
    )

    client_telegram_id = await get_client_telegram_id(booking_id)

    if client_telegram_id:
        await callback.bot.send_message(
            chat_id=client_telegram_id,
            text=(
                "❌ К сожалению, ваша заявка была отменена. "
                "Свяжитесь с мастером, чтобы выбрать другое время."
            )
        )


@router.callback_query(F.data == "admin:panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer("Доступ только для владельца.", show_alert=True)
        return

    await callback.answer()

    await callback.message.edit_text(
        "🛠 <b>Админ-панель</b>\n\n"
        "Выберите раздел:",
        reply_markup=admin_menu_keyboard()
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


@router.callback_query(F.data.startswith("admin:bookings:"))
async def admin_bookings_list(callback: CallbackQuery):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    await callback.answer()

    status = callback.data.split(":")[2]
    if status == "all":
        status = None

    bookings = await get_admin_bookings(status=status)

    status_names = {
        "new": "Новые",
        "confirmed": "Подтверждённые",
        "completed": "Завершённые",
        "cancelled": "Отменённые",
    }
    heading = (
        "Все заявки"
        if status is None
        else status_names.get(status, status)
    )

    if not bookings:
        await callback.message.edit_text(
            f"📋 <b>{heading}</b>\n\nЗаявок пока нет.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ В меню",
                            callback_data="admin:panel"
                        )
                    ]
                ]
            )
        )
        return

    lines = [f"📋 <b>{heading}</b>\n"]

    for booking in bookings[:20]:
        lines.append(
            f"#{booking['id']} — "
            f"{booking['preferred_date']}\n"
            f"🕒 {booking['preferred_time_slot']}\n"
            f"✂️ {booking['service_title']}\n"
            f"Статус: {booking['status']}"
        )

    buttons = []

    for i in range(0, min(len(bookings), 20), 2):
        row = []

        for booking in bookings[i:i + 2]:
            row.append(
                InlineKeyboardButton(
                    text=f"#{booking['id']} | {booking['preferred_date']}",
                    callback_data=f"admin:booking:{booking['id']}"
                )
            )

        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ В меню",
            callback_data="admin:panel"
        )
    ])

    await callback.message.edit_text(
        "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )



@router.callback_query(F.data.startswith("admin:booking:"))
async def admin_booking_card(callback: CallbackQuery):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    await callback.answer()

    booking_id = int(callback.data.split(":")[2])
    booking = await get_admin_booking_details(booking_id)

    if not booking:
        await callback.message.edit_text("Заявка не найдена.")
        return

    username = booking["username"]
    telegram_name = f"@{username}" if username else "не указан"

    text = (
        f"📋 <b>Заявка #{booking['id']}</b>\n\n"
        f"Статус: <b>{booking['status']}</b>\n"
        f"Услуга: {booking['service_title']}\n"
        f"Категория: {booking['service_category']}\n"
        f"Цена: {booking['service_price']}\n"
        f"Длительность: {booking['duration_minutes']} мин.\n\n"
        f"📅 Дата: {booking['preferred_date']}\n"
        f"🕒 Интервал: {booking['preferred_time_slot']}\n\n"
        f"👤 Клиент: {booking['full_name'] or 'не указано'}\n"
        f"📞 Телефон: {booking['phone'] or 'не указан'}\n"
        f"Telegram: {telegram_name}\n\n"
        f"💬 Комментарий: {booking['note'] or 'нет'}\n"
        f"Создана: {booking['created_at']}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_booking_keyboard(
            booking_id=booking["id"],
            status=booking["status"]
        )
    )


@router.callback_query(F.data == "admin:schedule")
async def admin_schedule(callback: CallbackQuery):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    await callback.answer()

    bookings = await get_admin_bookings()

    active_bookings = [
        booking for booking in bookings
        if booking["status"] in ("new", "confirmed")
        and booking["preferred_date"] != "Дата уточняется"
    ]

    if not active_bookings:
        await callback.message.edit_text(
            "📅 <b>Расписание</b>\n\n"
            "Активных записей пока нет.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ В меню",
                            callback_data="admin:panel"
                        )
                    ]
                ]
            )
        )
        return

    lines = ["📅 <b>Расписание</b>\n"]
    buttons = []
    current_date = None

    for booking in active_bookings:
        booking_date = booking["preferred_date"]

        if booking_date != current_date:
            current_date = booking_date
            lines.append(f"\n<b>📆 {current_date}</b>")

        lines.append(
            f"• {booking['preferred_time_slot']} — "
            f"{booking['service_title']}\n"
            f"  {booking['full_name'] or 'Клиент'} "
            f"(заявка #{booking['id']}, {booking['status']})"
        )

        buttons.append([
            InlineKeyboardButton(
                text=f"Открыть #{booking['id']}",
                callback_data=f"admin:booking:{booking['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ В меню",
            callback_data="admin:panel"
        )
    ])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data == "admin:filter:service")
async def admin_service_filter(callback: CallbackQuery):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    await callback.answer()
    services = await get_admin_services()

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{service['title']} ({service['category']})",
                callback_data=f"admin:service_bookings:{service['id']}"
            )
        ]
        for service in services
    ]

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ В меню",
            callback_data="admin:panel"
        )
    ])

    await callback.message.edit_text(
        "🔍 <b>Фильтр по услуге</b>\n\nВыберите услугу:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("admin:service_bookings:"))
async def admin_bookings_by_service(callback: CallbackQuery):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    await callback.answer()
    service_id = int(callback.data.split(":")[2])
    bookings = await get_admin_bookings(service_id=service_id)

    if not bookings:
        await callback.message.edit_text(
            "По этой услуге заявок пока нет.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="⬅️ К услугам",
                        callback_data="admin:filter:service"
                    )
                ]]
            )
        )
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"#{booking['id']} — {booking['preferred_date']}",
                callback_data=f"admin:booking:{booking['id']}"
            )
        ]
        for booking in bookings[:30]
    ]
    buttons.append([
        InlineKeyboardButton(
            text="⬅️ К услугам",
            callback_data="admin:filter:service"
        )
    ])

    await callback.message.edit_text(
        "🔍 <b>Заявки по выбранной услуге</b>\n\n"
        f"Найдено: {len(bookings)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data == "admin:filter:date")
async def admin_date_filter_start(
    callback: CallbackQuery,
    state: FSMContext
):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    await callback.answer()
    await state.set_state(AdminFilterStates.entering_date)

    await callback.message.edit_text(
        "📆 <b>Фильтр по дате</b>\n\n"
        "Введите дату в формате ДД.ММ.ГГГГ.\n"
        "Например: 08.11.2026",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="admin:panel"
                )
            ]]
        )
    )


@router.message(AdminFilterStates.entering_date)
async def admin_date_filter_apply(
    message: Message,
    state: FSMContext
):
    if message.from_user.id != OWNER_TELEGRAM_ID:
        await state.clear()
        return

    try:
        selected_date = datetime.strptime(
            message.text.strip(),
            "%d.%m.%Y"
        ).strftime("%d.%m.%Y")
    except (ValueError, AttributeError):
        await message.answer(
            "Не удалось распознать дату. "
            "Введите её как ДД.ММ.ГГГГ."
        )
        return

    await state.clear()
    bookings = await get_admin_bookings()

    filtered = [
        booking for booking in bookings
        if booking["preferred_date"] == selected_date
    ]

    if not filtered:
        await message.answer(
            f"На {selected_date} заявок не найдено.",
            reply_markup=admin_menu_keyboard()
        )
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"#{booking['id']} — {booking['service_title']}",
                callback_data=f"admin:booking:{booking['id']}"
            )
        ]
        for booking in filtered
    ]
    buttons.append([
        InlineKeyboardButton(
            text="⬅️ В меню",
            callback_data="admin:panel"
        )
    ])

    await message.answer(
        f"📆 <b>Заявки на {selected_date}</b>\n\n"
        f"Найдено: {len(filtered)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@router.message()
async def start(message: Message):
    await message.answer(
        "Команда не распознана. Используйте:\n\n/start\n/my_bookings"
    )