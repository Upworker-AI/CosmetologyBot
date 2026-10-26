from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

def main_menu():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
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
            ]
        ]
    )

    return keyboard

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