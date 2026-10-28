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