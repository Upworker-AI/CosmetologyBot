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
)
from datetime import datetime, timedelta
from keyboards.inline import (
    back_to_main_menu,
    date_keyboard,
    admin_menu_keyboard,
    admin_booking_keyboard,
    schedule_menu_keyboard,
    break_list_keyboard,
    breaks_menu_keyboard,
    break_weekdays_keyboard,
    break_conflict_keyboard
)
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
    get_available_slots,
    get_working_hours,
    update_working_hours,
    get_schedule_conflicts,
    get_working_breaks,
    get_date_breaks,
    add_working_break,
    delete_working_break,
    add_date_break,
    delete_date_break,
    reschedule_booking
)
from aiogram.exceptions import TelegramBadRequest

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

class AdminBreakStates(StatesGroup):
    entering_date = State()
    entering_start_time = State()
    entering_end_time = State()
    confirming_conflicts = State()

class AdminScheduleStates(StatesGroup):
    entering_start_time = State()
    entering_end_time = State()
    confirming_change = State()

class AdminRescheduleStates(StatesGroup):
    choosing_date = State()
    entering_custom_date = State()
    choosing_time = State()
    confirming = State()

WEEKDAYS = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}

def admin_reschedule_date_keyboard(booking_id: int):
    today = datetime.now().date()
    buttons = []

    for offset in range(7):
        day = today + timedelta(days=offset)

        if offset == 0:
            label = f"Сегодня, {day.strftime('%d.%m')}"
        elif offset == 1:
            label = f"Завтра, {day.strftime('%d.%m')}"
        else:
            weekday = WEEKDAYS[day.weekday()]
            label = f"{weekday}, {day.strftime('%d.%m')}"

        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=(
                    f"admin:reschedule:date:"
                    f"{booking_id}:{day.isoformat()}"
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="📅 Другая дата",
            callback_data=f"admin:reschedule:custom:{booking_id}"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="❌ Отменить перенос",
            callback_data=f"admin:reschedule:cancel:{booking_id}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def working_hours_keyboard():
    buttons = []

    weekdays = list(WEEKDAYS.items())

    # Размещаем дни недели по два в строке
    for i in range(0, len(weekdays), 2):
        row = []

        for weekday, name in weekdays[i:i + 2]:
            row.append(
                InlineKeyboardButton(
                    text=name,
                    callback_data=f"admin:working_hours:day:{weekday}"
                )
            )

        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="admin:schedule"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def working_day_keyboard(weekday: int, is_working: int):
    buttons = []

    if is_working:
        buttons.append([
            InlineKeyboardButton(
                text="🔴 Сделать выходным",
                callback_data=f"admin:working_hours:toggle:{weekday}"
            )
        ])
    else:
        buttons.append([
            InlineKeyboardButton(
                text="🟢 Сделать рабочим",
                callback_data=f"admin:working_hours:toggle:{weekday}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="🕒 Изменить время работы",
            callback_data=f"admin:working_hours:edit:{weekday}"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ К дням недели",
            callback_data="admin:schedule:working_hours"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def schedule_conflicts_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить изменение",
                    callback_data="admin:working_hours:apply"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="admin:working_hours:cancel"
                )
            ]
        ]
    )


async def show_schedule_conflicts(
    message: Message,
    state: FSMContext,
    weekday: int,
    is_working: int,
    start_time: str,
    end_time: str,
    conflicts: list
):
    await state.update_data(
        pending_weekday=weekday,
        pending_is_working=is_working,
        pending_start_time=start_time,
        pending_end_time=end_time,
    )

    await state.set_state(AdminScheduleStates.confirming_change)

    lines = [
        "⚠️ <b>Изменение расписания затронет существующие записи!</b>\n",
        "Следующие заявки окажутся за пределами нового графика:\n"
    ]

    for booking in conflicts[:15]:
        lines.append(
            f"📋 <b>Заявка #{booking['id']}</b>\n"
            f"📅 Дата: {booking['preferred_date']}\n"
            f"🕒 Время: {booking['preferred_time_slot']}\n"
            f"✂️ Услуга: {booking['service_title'] or 'не указана'}\n"
            f"👤 Клиент: {booking['full_name'] or 'не указан'}\n"
        )

    if len(conflicts) > 15:
        lines.append(
            f"\nИ ещё {len(conflicts) - 15} заявок."
        )

    lines.append(
        "\n<b>Важно:</b> подтверждение изменит только рабочий график. "
        "Заявки не будут удалены или отменены."
    )

    await message.answer(
        "\n".join(lines),
        reply_markup=schedule_conflicts_keyboard()
    )

@router.callback_query(F.data == "admin:schedule:working_hours")
async def show_working_hours(callback: CallbackQuery):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    await callback.answer()

    lines = ["🕒 <b>Рабочий график</b>\n"]

    for weekday, name in WEEKDAYS.items():
        hours = await get_working_hours(weekday)

        if hours is None:
            lines.append(f"⚠️ {name} — настройки отсутствуют")
            continue

        if hours["is_working"]:
            lines.append(
                f"🟢 {name} — "
                f"{hours['start_time']}–{hours['end_time']}"
            )
        else:
            lines.append(f"🔴 {name} — выходной")

    await callback.message.edit_text(
        "\n".join(lines) + "\n\nВыберите день для настройки:",
        reply_markup=working_hours_keyboard()
    )

@router.callback_query(F.data.startswith("admin:working_hours:day:"))
async def show_working_day(callback: CallbackQuery):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    await callback.answer()

    weekday = int(callback.data.split(":")[-1])
    hours = await get_working_hours(weekday)

    if hours is None:
        await callback.message.edit_text(
            "Настройки этого дня не найдены.",
            reply_markup=working_hours_keyboard()
        )
        return

    name = WEEKDAYS[weekday]

    if hours["is_working"]:
        status = (
            f"🟢 Рабочий день\n"
            f"Начало: {hours['start_time']}\n"
            f"Окончание: {hours['end_time']}"
        )
    else:
        status = "🔴 Выходной"

    await callback.message.edit_text(
        f"🕒 <b>{name}</b>\n\n"
        f"{status}\n\n"
        "Выберите действие:",
        reply_markup=working_day_keyboard(
            weekday,
            hours["is_working"]
        )
    )

@router.callback_query(F.data.startswith("admin:working_hours:toggle:"))
async def toggle_working_day(
    callback: CallbackQuery,
    state: FSMContext
):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    weekday = int(callback.data.split(":")[-1])
    hours = await get_working_hours(weekday)

    if hours is None:
        await callback.answer(
            "Настройки дня не найдены.",
            show_alert=True
        )
        return

    new_status = 0 if hours["is_working"] else 1

    # Нельзя включить рабочий день без заданных часов.
    if new_status and (
        not hours["start_time"] or not hours["end_time"]
    ):
        await callback.answer(
            "Сначала установите время работы этого дня.",
            show_alert=True
        )
        return

    # Если делаем день выходным, проверяем существующие записи.
    if not new_status:
        conflicts = await get_schedule_conflicts(
            weekday=weekday,
            is_working=0,
            start_time=hours["start_time"],
            end_time=hours["end_time"],
        )

        if conflicts:
            await callback.answer()
            await show_schedule_conflicts(
                message=callback.message,
                state=state,
                weekday=weekday,
                is_working=0,
                start_time=hours["start_time"],
                end_time=hours["end_time"],
                conflicts=conflicts,
            )
            return

    await update_working_hours(
        weekday=weekday,
        is_working=new_status,
        start_time=hours["start_time"],
        end_time=hours["end_time"],
    )

    await callback.answer(
        "День стал выходным." if not new_status
        else "День стал рабочим."
    )

    name = WEEKDAYS[weekday]

    if new_status:
        status = (
            f"🟢 Рабочий день\n"
            f"Начало: {hours['start_time']}\n"
            f"Окончание: {hours['end_time']}"
        )
    else:
        status = "🔴 Выходной"

    await callback.message.edit_text(
        f"🕒 <b>{name}</b>\n\n"
        f"{status}\n\n"
        "Выберите действие:",
        reply_markup=working_day_keyboard(weekday, new_status)
    )

@router.callback_query(F.data.startswith("admin:working_hours:edit:"))
async def edit_working_hours(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    await callback.answer()

    weekday = int(callback.data.split(":")[-1])

    await state.update_data(weekday=weekday)
    await state.set_state(AdminScheduleStates.entering_start_time)

    await callback.message.edit_text(
        f"🕒 <b>{WEEKDAYS[weekday]}</b>\n\n"
        "Введите время начала работы в формате ЧЧ:ММ.\n\n"
        "Например: 09:00",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data=f"admin:working_hours:day:{weekday}"
                    )
                ]
            ]
        )
    )

@router.message(AdminScheduleStates.entering_start_time)
async def enter_working_start_time(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_TELEGRAM_ID:
        return

    try:
        start_time = datetime.strptime(message.text.strip(), "%H:%M")
    except (ValueError, AttributeError):
        await message.answer(
            "Некорректное время.\n"
            "Введите время в формате ЧЧ:ММ, например 09:00."
        )
        return

    await state.update_data(
        start_time=start_time.strftime("%H:%M")
    )

    data = await state.get_data()
    weekday = data["weekday"]

    await state.set_state(AdminScheduleStates.entering_end_time)

    await message.answer(
        f"Начало работы: {start_time.strftime('%H:%M')}\n\n"
        "Теперь введите время окончания работы.\n\n"
        "Например: 18:00"
    )

@router.message(AdminScheduleStates.entering_end_time)
async def enter_working_end_time(
    message: Message,
    state: FSMContext
):
    if message.from_user.id != OWNER_TELEGRAM_ID:
        return

    try:
        end_time = datetime.strptime(
            message.text.strip(), "%H:%M"
        )
    except (ValueError, AttributeError):
        await message.answer(
            "Некорректное время.\n"
            "Введите время в формате ЧЧ:ММ, например 18:00."
        )
        return

    data = await state.get_data()

    start_time = data["start_time"]
    weekday = data["weekday"]
    end_time_str = end_time.strftime("%H:%M")

    if end_time <= datetime.strptime(start_time, "%H:%M"):
        await message.answer(
            "Время окончания должно быть позже времени начала.\n"
            "Попробуйте ещё раз."
        )
        return

    hours = await get_working_hours(weekday)
    is_working = hours["is_working"] if hours else 1

    # Проверяем, не выйдут ли записи за новые часы работы.
    if is_working:
        conflicts = await get_schedule_conflicts(
            weekday=weekday,
            is_working=1,
            start_time=start_time,
            end_time=end_time_str,
        )

        if conflicts:
            await show_schedule_conflicts(
                message=message,
                state=state,
                weekday=weekday,
                is_working=1,
                start_time=start_time,
                end_time=end_time_str,
                conflicts=conflicts,
            )
            return

    # Конфликтов нет — сохраняем сразу.
    await update_working_hours(
        weekday=weekday,
        is_working=is_working,
        start_time=start_time,
        end_time=end_time_str,
    )

    await state.clear()

    updated_hours = await get_working_hours(weekday)

    if updated_hours["is_working"]:
        status = (
            f"🟢 Рабочий день\n"
            f"Начало: {updated_hours['start_time']}\n"
            f"Окончание: {updated_hours['end_time']}"
        )
    else:
        status = (
            "🔴 Выходной\n"
            f"Сохранённые часы: "
            f"{updated_hours['start_time']}–{updated_hours['end_time']}"
        )

    await message.answer(
        f"✅ <b>Расписание сохранено!</b>\n\n"
        f"{WEEKDAYS[weekday]}\n"
        f"{status}",
        reply_markup=working_day_keyboard(
            weekday,
            updated_hours["is_working"]
        )
    )

@router.callback_query(
    F.data == "admin:working_hours:apply",
    AdminScheduleStates.confirming_change
)
async def apply_schedule_change(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    weekday = data.get("pending_weekday")
    is_working = data.get("pending_is_working")
    start_time = data.get("pending_start_time")
    end_time = data.get("pending_end_time")

    # Проверяем, что ожидающее изменение действительно сохранено
    if weekday is None or is_working is None:
        await callback.answer(
            "Не удалось применить изменение. Попробуйте ещё раз.",
            show_alert=True
        )
        await state.clear()
        return

    # Применяем расписание, несмотря на найденные записи
    await update_working_hours(
        weekday=weekday,
        is_working=is_working,
        start_time=start_time,
        end_time=end_time
    )

    await state.clear()

    await callback.answer("Расписание успешно изменено!")

    # Обновляем существующее сообщение, а не отправляем новое
    await callback.message.edit_text(
        "Расписание успешно изменено!",
        reply_markup=admin_menu_keyboard()
    )

@router.callback_query(
    AdminScheduleStates.confirming_change,
    F.data == "admin:working_hours:cancel"
)
async def cancel_schedule_change(
    callback: CallbackQuery,
    state: FSMContext
):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    data = await state.get_data()
    weekday = data.get("pending_weekday")

    await state.clear()
    await callback.answer("Изменение отменено.")

    if weekday is None:
        await callback.message.edit_text(
            "Изменение расписания отменено.",
            reply_markup=working_hours_keyboard()
        )
        return

    hours = await get_working_hours(weekday)

    if hours is None:
        await callback.message.edit_text(
            "Настройки этого дня не найдены.",
            reply_markup=working_hours_keyboard()
        )
        return

    if hours["is_working"]:
        status = (
            f"🟢 Рабочий день\n"
            f"Начало: {hours['start_time']}\n"
            f"Окончание: {hours['end_time']}"
        )
    else:
        status = "🔴 Выходной"

    await callback.message.edit_text(
        f"🕒 <b>{WEEKDAYS[weekday]}</b>\n\n"
        f"{status}\n\n"
        "Изменение отменено. Старое расписание сохранено.",
        reply_markup=working_day_keyboard(
            weekday,
            hours["is_working"]
        )
    )

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
        try:
            await message.edit_text(
                text,
                reply_markup=keyboard
            )
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error):
                raise
    else:
        await message.answer(
            text,
            reply_markup=keyboard
        )


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

    try:
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
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            note=data.get("note"),
        )

    except ValueError as error:
        # Если другой клиент успел занять время.
        await callback.message.edit_text(
            f"⚠️ {error}\n\n"
            "Выберите другое свободное время."
        )

        await ask_time_slot(
            callback.message,
            state,
            edit_message=False
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
    username = callback.from_user.username or "нет"

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
        f"Telegram: @{username}\n"
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
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True)
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
async def show_schedule_menu(callback: CallbackQuery):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer(
            "Доступ только для владельца.",
            show_alert=True
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        "📅 <b>Расписание</b>\n\n"
        "Выберите действие:",
        reply_markup=schedule_menu_keyboard()
    )


@router.callback_query(F.data == "admin:schedule:breaks")
async def show_breaks_menu(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "☕ <b>Управление перерывами</b>\n\n"
        "Выберите тип перерывов:",
        reply_markup=breaks_menu_keyboard()
    )


@router.callback_query(F.data == "admin:breaks:weekly")
async def show_weekly_breaks(callback: CallbackQuery):
    await callback.answer()

    await callback.message.edit_text(
        "🔁 <b>Еженедельные перерывы</b>\n\n"
        "Выберите день недели:",
        reply_markup=break_weekdays_keyboard()
    )


@router.callback_query(F.data.startswith("admin:breaks:weekday:"))
async def show_weekday_breaks(callback: CallbackQuery):
    await callback.answer()

    weekday = int(callback.data.split(":")[-1])

    breaks = await get_working_breaks(weekday)

    weekday_name = WEEKDAYS[weekday]

    if breaks:
        text = (
            f"☕ <b>Перерывы: {weekday_name}</b>\n\n"
            "Нажмите на перерыв, чтобы удалить его:"
        )
    else:
        text = (
            f"☕ <b>Перерывы: {weekday_name}</b>\n\n"
            "На этот день перерывов пока нет."
        )

    await callback.message.edit_text(
        text,
        reply_markup=break_list_keyboard(
            breaks,
            f"weekly_{weekday}",
            "admin:breaks:weekly"
        )
    )


@router.callback_query(F.data == "admin:breaks:date")
async def start_date_breaks(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    await state.set_state(AdminBreakStates.entering_date)

    await callback.message.edit_text(
        "📅 <b>Перерывы на конкретную дату</b>\n\n"
        "Введите дату в формате ДД.ММ.ГГГГ.\n"
        "Например: 15.11.2026",
        reply_markup=breaks_menu_keyboard()
    )
def format_date_breaks_text(date_obj, weekly_breaks, date_breaks, prefix=None):
    date_display = date_obj.strftime("%d.%m.%Y")

    lines = []

    if prefix:
        lines.extend([prefix, ""])

    lines.extend([
        f"☕ <b>Перерывы на {date_display}</b>",
        "",
        "🔁 <b>Еженедельные перерывы:</b>"
    ])

    if weekly_breaks:
        for item in weekly_breaks:
            title = item.get("title") or "Перерыв"
            lines.append(
                f"• {item['start_time']}–{item['end_time']} — {title}"
            )
    else:
        lines.append("• Нет еженедельных перерывов")

    lines.extend([
        "",
        "📅 <b>Разовые перерывы:</b>"
    ])

    if date_breaks:
        for item in date_breaks:
            title = item.get("title") or "Перерыв"
            lines.append(
                f"• {item['start_time']}–{item['end_time']} — {title}"
            )
    else:
        lines.append("• Нет разовых перерывов")

    lines.extend([
        "",
        "Нажмите на разовый перерыв ниже, чтобы удалить его."
    ])

    return "\n".join(lines)

@router.message(AdminBreakStates.entering_date)
async def show_date_breaks(message: Message, state: FSMContext):
    try:
        selected_date = datetime.strptime(
            message.text.strip(), "%d.%m.%Y"
        ).date()

        date_iso = selected_date.strftime("%Y-%m-%d")

    except ValueError:
        await message.answer(
            "❌ Неверный формат даты.\n"
            "Введите дату в формате ДД.ММ.ГГГГ."
        )
        return

    await state.clear()

    # Получаем еженедельные перерывы для выбранного дня недели
    weekday = selected_date.weekday()
    weekly_breaks = await get_working_breaks(weekday)

    # Получаем разовые перерывы для выбранной даты
    date_breaks = await get_date_breaks(date_iso)

    text = format_date_breaks_text(
        selected_date,
        weekly_breaks,
        date_breaks
    )

    await message.answer(
        text,
        reply_markup=break_list_keyboard(
            date_breaks,
            f"date_{date_iso}",
            "admin:breaks:date"
        )
    )


@router.callback_query(F.data.startswith("admin:breaks:add:"))
async def start_adding_break(
    callback: CallbackQuery,
    state: FSMContext
):
    await callback.answer()

    # Получаем тип перерыва из callback_data
    break_type = callback.data.split(":", 3)[3]

    # Еженедельный перерыв
    if break_type.startswith("weekly_"):
        weekday = int(break_type.split("_")[1])

        await state.update_data(
            break_type="weekly",
            weekday=weekday
        )

    # Поддержка старого варианта callback_data
    elif break_type == "weekly":
        await callback.message.edit_text(
            "❌ Не удалось определить день недели. "
            "Вернитесь к выбору дня и попробуйте снова."
        )
        return

    # Перерыв на конкретную дату
    elif break_type.startswith("date_"):
        date_iso = break_type.replace("date_", "", 1)

        await state.update_data(
            break_type="date",
            date=date_iso
        )

    else:
        await callback.message.answer(
            f"Неизвестный тип перерыва: {break_type}"
        )
        return

    await state.set_state(
        AdminBreakStates.entering_start_time
    )

    await callback.message.edit_text(
        "➕ <b>Добавление перерыва</b>\n\n"
        "Введите время начала в формате ЧЧ:ММ.\n"
        "Например: 13:00"
    )

async def save_break_and_show(
    message: Message,
    state: FSMContext,
    data: dict
):
    start_time = data["start_time"]
    end_time = data["end_time"]

    if data["break_type"] == "weekly":
        weekday = data["weekday"]

        await add_working_break(
            weekday=weekday,
            start_time=start_time,
            end_time=end_time
        )

        await state.clear()

        breaks = await get_working_breaks(weekday)
        weekday_name = WEEKDAYS[weekday]

        await message.answer(
            f"✅ Перерыв добавлен!\n\n"
            f"День: {weekday_name}\n"
            f"Время: {start_time}–{end_time}",
            reply_markup=break_list_keyboard(
                breaks,
                f"weekly_{weekday}",
                "admin:breaks:weekly"
            )
        )

    else:
        date_iso = data["date"]

        await add_date_break(
            date=date_iso,
            start_time=start_time,
            end_time=end_time
        )

        await state.clear()

        date_obj = datetime.strptime(
            date_iso, "%Y-%m-%d"
        ).date()

        weekly_breaks = await get_working_breaks(
            date_obj.weekday()
        )
        date_breaks = await get_date_breaks(date_iso)

        text = format_date_breaks_text(
            date_obj,
            weekly_breaks,
            date_breaks,
            prefix=(
                f"✅ Перерыв добавлен!\n"
                f"Время: {start_time}–{end_time}"
            )
        )

        await message.answer(
            text,
            reply_markup=break_list_keyboard(
                date_breaks,
                f"date_{date_iso}",
                "admin:breaks:date"
            )
        )


@router.message(AdminBreakStates.entering_start_time)
async def enter_break_start_time(
    message: Message,
    state: FSMContext
):
    try:
        start_time = datetime.strptime(
            message.text.strip(),
            "%H:%M"
        ).strftime("%H:%M")

    except ValueError:
        await message.answer(
            "❌ Неверный формат времени.\n"
            "Введите время, например: 13:00"
        )
        return

    # Сохраняем время начала перерыва
    await state.update_data(
        start_time=start_time
    )

    # Переходим к вводу времени окончания
    await state.set_state(
        AdminBreakStates.entering_end_time
    )

    await message.answer(
        "Введите время окончания перерыва.\n"
        "Например: 14:00"
    )


@router.message(AdminBreakStates.entering_end_time)
async def enter_break_end_time(
    message: Message,
    state: FSMContext
):
    try:
        end_time = datetime.strptime(
            message.text.strip(),
            "%H:%M"
        ).strftime("%H:%M")

    except ValueError:
        await message.answer(
            "❌ Неверный формат времени.\n"
            "Введите время, например: 14:00"
        )
        return

    data = await state.get_data()

    start_time = data["start_time"]

    if end_time <= start_time:
        await message.answer(
            "❌ Время окончания должно быть позже "
            "времени начала.\n"
            "Введите время окончания ещё раз."
        )
        return

    # Сохраняем окончание перерыва в FSM
    await state.update_data(end_time=end_time)

    data = await state.get_data()

    try:

        # ==================================
        # ЕЖЕНЕДЕЛЬНЫЙ ПЕРЕРЫВ
        # ==================================

        if data["break_type"] == "weekly":

            weekday = data["weekday"]

            conflicts = await get_schedule_conflicts(
                weekday=weekday,
                is_working=1,
                check_break=True,
                break_start=start_time,
                break_end=end_time
            )

        # ==================================
        # РАЗОВЫЙ ПЕРЕРЫВ
        # ==================================

        else:

            date_iso = data["date"]

            date_obj = datetime.strptime(
                date_iso, "%Y-%m-%d"
            ).date()

            conflicts = await get_schedule_conflicts(
                weekday=date_obj.weekday(),
                is_working=1,
                check_break=True,
                break_start=start_time,
                break_end=end_time,
                target_date=date_iso
            )

        # ==================================
        # ЕСЛИ ЕСТЬ КОНФЛИКТЫ
        # ==================================

        if conflicts:

            await state.set_state(
                AdminBreakStates.confirming_conflicts
            )

            lines = [
                "⚠️ <b>Обнаружены конфликты с записями!</b>",
                "",
                f"Новый перерыв: <b>{start_time}–{end_time}</b>",
                "",
                "Найдены следующие записи:"
            ]

            for booking in conflicts:

                client_name = (
                    booking["full_name"] or "Не указано"
                )

                service_name = (
                    booking["service_title"] or "Не указана"
                )

                lines.extend([
                    "",
                    f"📅 <b>{booking['preferred_date']}</b>",
                    f"👤 Клиент: {client_name}",
                    f"💅 Услуга: {service_name}",
                    f"🕒 Время: "
                    f"{booking['start_time']}–{booking['end_time']}",
                    f"📌 Заявка №{booking['id']}"
                ])

            lines.extend([
                "",
                "Если продолжить, перерыв будет добавлен, "
                "но существующие записи останутся без изменений.",
                "",
                "<b>Добавить перерыв всё равно?</b>"
            ])

            await message.answer(
                "\n".join(lines),
                reply_markup=break_conflict_keyboard()
            )

            return

        # ==================================
        # ЕСЛИ КОНФЛИКТОВ НЕТ
        # ==================================

        await save_break_and_show(
            message,
            state,
            data
        )

    except ValueError as error:

        await message.answer(
            f"❌ Не удалось добавить перерыв: {error}\n\n"
            "Попробуйте ввести другое время начала."
        )

        await state.set_state(
            AdminBreakStates.entering_start_time
        )



@router.callback_query(
    AdminBreakStates.confirming_conflicts,
    F.data == "admin:breaks:conflicts:confirm"
)
async def confirm_break_with_conflicts(
    callback: CallbackQuery,
    state: FSMContext
):
    data = await state.get_data()

    try:
        await save_break_and_show(
            callback.message,
            state,
            data
        )

        await callback.answer("Перерыв добавлен!")

    except ValueError as error:
        await callback.answer(
            f"Не удалось добавить перерыв: {error}",
            show_alert=True
        )

@router.callback_query(
    AdminBreakStates.confirming_conflicts,
    F.data == "admin:breaks:conflicts:cancel"
)
async def cancel_break_with_conflicts(
    callback: CallbackQuery,
    state: FSMContext
):
    data = await state.get_data()

    await state.clear()

    if data["break_type"] == "weekly":

        weekday = data["weekday"]

        breaks = await get_working_breaks(weekday)

        await callback.message.edit_text(
            f"❌ Добавление перерыва отменено.\n\n"
            f"Еженедельные перерывы — {WEEKDAYS[weekday]}:",
            reply_markup=break_list_keyboard(
                breaks,
                f"weekly_{weekday}",
                "admin:breaks:weekly"
            )
        )

    else:

        date_iso = data["date"]

        date_obj = datetime.strptime(
            date_iso, "%Y-%m-%d"
        ).date()

        weekly_breaks = await get_working_breaks(
            date_obj.weekday()
        )

        date_breaks = await get_date_breaks(date_iso)

        text = format_date_breaks_text(
            date_obj,
            weekly_breaks,
            date_breaks,
            prefix="❌ Добавление перерыва отменено."
        )

        await callback.message.edit_text(
            text,
            reply_markup=break_list_keyboard(
                date_breaks,
                f"date_{date_iso}",
                "admin:breaks:date"
            )
        )

    await callback.answer("Добавление отменено.")

@router.callback_query(F.data.startswith("admin:breaks:delete:"))
async def delete_break(callback: CallbackQuery):
    await callback.answer()

    parts = callback.data.split(":")

    break_type = parts[3]
    break_id = int(parts[4])

    if break_type.startswith("weekly_"):
        weekday = int(break_type.split("_")[1])

        deleted = await delete_working_break(break_id)

        breaks = await get_working_breaks(weekday)

        weekday_name = WEEKDAYS[weekday]

        text = (
            f"☕ <b>Перерывы: {weekday_name}</b>\n\n"
            "Нажмите на перерыв, чтобы удалить его:"
            if breaks else
            f"☕ <b>Перерывы: {weekday_name}</b>\n\n"
            "На этот день перерывов пока нет."
        )

        if deleted:
            await callback.answer("Перерыв удалён", show_alert=False)

        await callback.message.edit_text(
            text,
            reply_markup=break_list_keyboard(
                breaks,
                break_type,
                "admin:breaks:weekly"
            )
        )


    elif break_type.startswith("date_"):

        date_iso = break_type.replace("date_", "", 1)

        deleted = await delete_date_break(break_id)

        date_obj = datetime.strptime(

            date_iso, "%Y-%m-%d"

        ).date()

        weekly_breaks = await get_working_breaks(date_obj.weekday())

        date_breaks = await get_date_breaks(date_iso)

        text = format_date_breaks_text(

            date_obj,

            weekly_breaks,

            date_breaks,

            prefix="✅ Разовый перерыв удалён."

            if deleted else "⚠️ Перерыв не найден."

        )

        await callback.message.edit_text(

            text,

            reply_markup=break_list_keyboard(

                date_breaks,

                f"date_{date_iso}",

                "admin:breaks:date"

            )

        )

        await callback.answer(

            "Перерыв удалён" if deleted else "Перерыв не найден",

            show_alert=not deleted

        )

@router.callback_query(F.data == "admin:schedule:bookings")
async def admin_schedule_bookings(callback: CallbackQuery):
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
    booking_buttons = []
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

        booking_buttons.append(
            InlineKeyboardButton(
                text=f"Открыть #{booking['id']}",
                callback_data=f"admin:booking:{booking['id']}"
            )
        )
    for i in range(0, len(booking_buttons), 2):
        buttons.append(booking_buttons[i:i+2])

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

@router.callback_query(F.data.regexp(r"^admin:reschedule:\d+$"))
async def admin_reschedule_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    booking_id = int(callback.data.split(":")[2])

    booking = await get_admin_booking_details(booking_id)

    if not booking:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    if booking["status"] not in ("new", "confirmed"):
        await callback.answer(
            "Эту запись нельзя перенести.",
            show_alert=True
        )
        return

    await state.clear()

    await state.update_data(
        booking_id=booking_id,
        service_id=booking["service_id"],
        old_date=booking["preferred_date"],
        old_time=booking["preferred_time_slot"],
    )

    await state.set_state(AdminRescheduleStates.choosing_date)

    await callback.message.edit_text(
        f"📅 Перенос записи №{booking_id}\n\n"
        f"Текущая дата: {booking['preferred_date']}\n"
        f"Текущее время: {booking['preferred_time_slot']}\n\n"
        f"Выберите новую дату:",
        reply_markup=admin_reschedule_date_keyboard(booking_id)
    )

    await callback.answer()

@router.callback_query(
    F.data.startswith("admin:reschedule:date:")
)
async def admin_reschedule_choose_date(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = callback.data.split(":")
    booking_id = int(parts[3])
    selected_date = parts[4]

    data = await state.get_data()

    if data.get("booking_id") != booking_id:
        await callback.answer(
            "Сессия переноса устарела. Откройте перенос заново.",
            show_alert=True
        )
        return

    try:
        date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
    except ValueError:
        await callback.answer("Некорректная дата.", show_alert=True)
        return

    if date_obj < datetime.now().date():
        await callback.answer(
            "Нельзя выбрать прошедшую дату.",
            show_alert=True
        )
        return

    service_id = data["service_id"]

    slots = await get_available_slots(
        selected_date,
        service_id,
        exclude_booking_id=booking_id
    )

    if not slots:
        await callback.answer(
            "На эту дату нет свободного времени.",
            show_alert=True
        )
        return

    await state.update_data(new_date=selected_date)
    await state.set_state(AdminRescheduleStates.choosing_time)

    buttons = []

    for slot in slots:
        buttons.append([
            InlineKeyboardButton(
                text=slot,
                callback_data=(
                    f"admin:reschedule:time:"
                    f"{booking_id}:{slot.replace(':', '-')}"
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Выбрать другую дату",
            callback_data=f"admin:reschedule:back:{booking_id}"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="❌ Отменить перенос",
            callback_data=f"admin:reschedule:cancel:{booking_id}"
        )
    ])

    await callback.message.edit_text(
        f"📅 Новая дата: {date_obj.strftime('%d.%m.%Y')}\n\n"
        f"Выберите свободное время:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

    await callback.answer()

@router.callback_query(
    F.data.startswith("admin:reschedule:custom:")
)
async def admin_reschedule_custom_date(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    booking_id = int(callback.data.split(":")[3])
    data = await state.get_data()

    if data.get("booking_id") != booking_id:
        await callback.answer("Сессия переноса устарела.", show_alert=True)
        return

    await state.set_state(AdminRescheduleStates.entering_custom_date)

    await callback.message.edit_text(
        "Введите новую дату в формате ДД.ММ.ГГГГ:"
    )

    await callback.answer()

@router.message(AdminRescheduleStates.entering_custom_date)
async def admin_reschedule_enter_date(
    message: Message,
    state: FSMContext,
):
    if message.from_user.id != OWNER_TELEGRAM_ID:
        return

    try:
        date_obj = datetime.strptime(
            message.text.strip(), "%d.%m.%Y"
        ).date()
    except (ValueError, AttributeError):
        await message.answer(
            "Неверный формат даты.\n"
            "Введите дату в формате ДД.ММ.ГГГГ."
        )
        return

    if date_obj < datetime.now().date():
        await message.answer("Нельзя выбрать прошедшую дату.")
        return

    data = await state.get_data()
    booking_id = data["booking_id"]

    selected_date = date_obj.isoformat()

    slots = await get_available_slots(
        selected_date,
        data["service_id"],
        exclude_booking_id=booking_id
    )

    if not slots:
        await message.answer(
            "На эту дату нет свободного времени. "
            "Введите другую дату."
        )
        return

    await state.update_data(new_date=selected_date)
    await state.set_state(AdminRescheduleStates.choosing_time)

    buttons = []

    for slot in slots:
        buttons.append([
            InlineKeyboardButton(
                text=slot,
                callback_data=(
                    f"admin:reschedule:time:"
                    f"{booking_id}:{slot.replace(':', '-')}"
                )
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Выбрать другую дату",
            callback_data=f"admin:reschedule:back:{booking_id}"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="❌ Отменить перенос",
            callback_data=f"admin:reschedule:cancel:{booking_id}"
        )
    ])

    await message.answer(
        f"📅 Новая дата: {date_obj.strftime('%d.%m.%Y')}\n\n"
        f"Выберите свободное время:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@router.callback_query(
    F.data.startswith("admin:reschedule:time:")
)
async def admin_reschedule_choose_time(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = callback.data.split(":")
    booking_id = int(parts[3])
    new_time = parts[4].replace("-", ":")

    data = await state.get_data()

    if (
        data.get("booking_id") != booking_id
        or await state.get_state() != AdminRescheduleStates.choosing_time.state
    ):
        await callback.answer(
            "Сессия переноса устарела. Начните заново.",
            show_alert=True
        )
        return

    new_date = data["new_date"]
    date_display = datetime.strptime(
        new_date, "%Y-%m-%d"
    ).strftime("%d.%m.%Y")

    await state.update_data(new_time=new_time)
    await state.set_state(AdminRescheduleStates.confirming)

    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Подтвердить перенос",
                callback_data=f"admin:reschedule:confirm:{booking_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"admin:reschedule:cancel:{booking_id}"
            )
        ]
    ]

    await callback.message.edit_text(
        f"📋 **Проверка переноса записи №{booking_id}**\n\n"
        f"Старая дата: {data['old_date']}\n"
        f"Старое время: {data['old_time']}\n\n"
        f"Новая дата: {date_display}\n"
        f"Новое время: {new_time}\n\n"
        f"Подтвердить перенос?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )

    await callback.answer()

@router.callback_query(
    F.data.startswith("admin:reschedule:confirm:")
)
async def admin_reschedule_confirm(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    booking_id = int(callback.data.split(":")[3])
    data = await state.get_data()

    if (
        data.get("booking_id") != booking_id
        or await state.get_state() != AdminRescheduleStates.confirming.state
    ):
        await callback.answer(
            "Сессия переноса устарела. Начните заново.",
            show_alert=True
        )
        return

    try:
        await reschedule_booking(
            booking_id=booking_id,
            new_date=data["new_date"],
            new_time_slot=data["new_time"],
        )

    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return

    booking = await get_admin_booking_details(booking_id)

    await state.clear()

    date_display = datetime.strptime(
        data["new_date"], "%Y-%m-%d"
    ).strftime("%d.%m.%Y")

    await callback.message.edit_text(
        f"✅ Запись №{booking_id} успешно перенесена!\n\n"
        f"Новая дата: {date_display}\n"
        f"Новое время: {data['new_time']}",
        reply_markup=admin_booking_keyboard(
            booking_id,
            booking["status"]
        )
    )

    # Уведомляем клиента.
    client_telegram_id = booking["client_telegram_id"]

    if client_telegram_id:
        await callback.bot.send_message(
            client_telegram_id,
            f"📅 Ваша запись №{booking_id} перенесена.\n\n"
            f"Новая дата: {date_display}\n"
            f"Новое время: {data['new_time']}\n\n"
            f"Если у вас возникли вопросы, свяжитесь с нами."
        )

    await callback.answer("Запись перенесена!")

@router.callback_query(
    F.data.startswith("admin:reschedule:cancel:")
)
async def admin_reschedule_cancel(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await state.clear()

    await callback.message.edit_text(
        "Перенос записи отменён."
    )

    await callback.answer()

@router.callback_query(
    F.data.startswith("admin:reschedule:back:")
)
async def admin_reschedule_back(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.from_user.id != OWNER_TELEGRAM_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    booking_id = int(callback.data.split(":")[3])
    data = await state.get_data()

    if data.get("booking_id") != booking_id:
        await callback.answer("Сессия переноса устарела.", show_alert=True)
        return

    await state.set_state(AdminRescheduleStates.choosing_date)

    await callback.message.edit_text(
        "📅 Выберите новую дату:",
        reply_markup=admin_reschedule_date_keyboard(booking_id)
    )

    await callback.answer()

@router.message()
async def start(message: Message):
    await message.answer(
        "Команда не распознана. Используйте:\n\n/start\n/my_bookings"
    )