from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from datetime import datetime, timedelta

WEEKDAYS = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс"
}

def main_menu(is_owner: bool = False):
    buttons = [
            [InlineKeyboardButton(
                text="📅 Записаться",
                callback_data="book:start"
            ),
            InlineKeyboardButton(
                text="💎 Услуги и цены",
                callback_data="services:root"
            )
            ],
            [InlineKeyboardButton(
                text="🔥 Акции",
                callback_data="promo"
            ),
            InlineKeyboardButton(
                text="📍 Адрес и часы работы",
                callback_data="contacts"
            )
            ],
            [InlineKeyboardButton(
                text="❓ Частые вопросы",
                callback_data="faq"
            ),
            InlineKeyboardButton(
                text="💬 Связаться",
                callback_data="contact_me"
            )
            ],
            [
            InlineKeyboardButton(
                text="📋 Мои записи",
                callback_data="my_bookings"
            )
            ],
    ]

    if is_owner:
        buttons.append(
            [InlineKeyboardButton(
                text="🛠 Админ-панель",
                callback_data="admin:panel"
            )]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def back_to_main_menu():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="⬅️ В главное меню",
                callback_data="main_menu"
            )]
        ]
    )

    return keyboard

def date_keyboard():
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

        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"date:{day.strftime('%d.%m.%Y')}"
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="📅 Другая дата", callback_data="date:custom")]
    )
    buttons.append(
        [InlineKeyboardButton(text="❌ Отменить", callback_data="book:cancel")]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Расписание",
                    callback_data="admin:schedule"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Все заявки",
                    callback_data="admin:bookings:all"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🆕 Новые",
                    callback_data="admin:bookings:new"
                ),
                InlineKeyboardButton(
                    text="✅ Подтверждённые",
                    callback_data="admin:bookings:confirmed"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏁 Завершённые",
                    callback_data="admin:bookings:completed"
                ),
                InlineKeyboardButton(
                    text="❌ Отменённые",
                    callback_data="admin:bookings:cancelled"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 По услуге",
                    callback_data="admin:filter:service"
                )
            ],
        ]
    )

def schedule_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Записи по датам",
                    callback_data="admin:schedule:bookings"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🕒 Рабочий график",
                    callback_data="admin:schedule:working_hours"
                )
            ],
            [
                InlineKeyboardButton(
                    text="☕ Перерывы",
                    callback_data="admin:schedule:breaks"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В меню",
                    callback_data="admin:panel"
                )
            ]
        ]
    )

def admin_booking_keyboard(booking_id: int, status: str):
    buttons = []

    if status == "new":
        buttons.append([
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=f"admin:confirm:{booking_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"admin:cancel:{booking_id}"
            )
        ])

    elif status == "confirmed":
        buttons.append([
            InlineKeyboardButton(
                text="✅ Завершить",
                callback_data=f"admin:complete:{booking_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"admin:cancel:{booking_id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ К списку заявок",
            callback_data="admin:bookings:all"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def breaks_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔁 Еженедельные перерывы",
                    callback_data="admin:breaks:weekly"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 Перерывы на дату",
                    callback_data="admin:breaks:date"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="admin:schedule"
                )
            ]
        ]
    )


def break_weekdays_keyboard():
    weekdays = [
        ("Понедельник", 0),
        ("Вторник", 1),
        ("Среда", 2),
        ("Четверг", 3),
        ("Пятница", 4),
        ("Суббота", 5),
        ("Воскресенье", 6),
    ]

    keyboard = []

    for name, weekday in weekdays:
        keyboard.append([
            InlineKeyboardButton(
                text=name,
                callback_data=f"admin:breaks:weekday:{weekday}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="admin:schedule:breaks"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def break_list_keyboard(breaks, break_type, return_callback):
    keyboard = []

    for item in breaks:
        title = item.get("title") or "Перерыв"

        keyboard.append([
            InlineKeyboardButton(
                text=(
                    f"🗑 {item['start_time']}–{item['end_time']} "
                    f"({title})"
                ),
                callback_data=(
                    f"admin:breaks:delete:{break_type}:{item['id']}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            text="➕ Добавить перерыв",
            callback_data=f"admin:breaks:add:{break_type}"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=return_callback
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def break_conflict_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Добавить всё равно",
                    callback_data="admin:breaks:conflicts:confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="admin:breaks:conflicts:cancel"
                )
            ]
        ]
    )