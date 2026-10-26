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
from forms.user import BookingStates
from keyboards.inline import main_menu, back_to_main_menu
from database.db import get_categories, get_services_by_category,get_service

router = Router()

@router.message(Command("start"))
async def start(message: Message):
    await message.answer(
        f"Привет, <b>{message.from_user.first_name}</b>! 👋\n\n"
        "Я бот студии «Beauty Studio».\n\n"
        "<b>Здесь можно:</b>\n"
        "• посмотреть услуги и цены\n"
        "• оставить заявку на запись\n"
        "• найти адрес и часы работы\n\n"
        "Выберите раздел 👇",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "book:start")
async def booking(callback: CallbackQuery):
    await callback.message.edit_text(
        "📅 <b>Запись</b>\n\n"
        "Скоро появиться возможность записаться",
        reply_markup=back_to_main_menu()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("book:start:"))
async def start_booking(callback: CallbackQuery):
    await callback.answer()

    service_id = int(callback.data.split(":")[2])

    await callback.message.edit_text(
        "Отлично! Запись будет доступна в следующей версии.\n"
        f"ID выбранной услуги: <code>{service_id}</code>",
        reply_markup=back_to_main_menu()
    )

@router.callback_query(F.data == "services:root")
async def show_services(callback: CallbackQuery):
    categories = await get_categories()
    if not categories:
        await callback.message.edit_text(
            "Пока услуги не добавлены.",
            reply_markup=back_to_main_menu()
        )
        return
    buttons = [
        [InlineKeyboardButton(
            text=category["category"],
            callback_data=f"category:{category['category']}"
            )
        ]
        for category in categories
    ]

    buttons.append(
        [InlineKeyboardButton(
            text="⬅️ В главное меню",
            callback_data="main_menu"
        )]
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "💎 <b>Услуги и цены</b>\n\n",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("category:"))
async def show_category(callback: CallbackQuery):
    await callback.answer()

    category = callback.data.split(":", 1)[1]
    services = await get_services_by_category(category)

    if not services:
        await callback.message.edit_text(
            "В этой категории пока нет услуг.",
            reply_markup=back_to_main_menu()
        )
        return

    buttons = []

    for service in services:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{service['title']} — {service['price']}",
                    callback_data=f"service:{service['id']}"
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="⬅️ К категориям", callback_data="services:root")]
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    symbol = {"Уход за лицом" : "💆‍♀️", "Курс" : "💎", "Консультации" : "👩‍⚕️"}
    await callback.message.edit_text(
        f"{symbol[category]} <b>{category}</b>\n\nВыберите услугу:",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("service:"))
async def show_service(callback: CallbackQuery):
    await callback.answer()

    parts = callback.data.split(":")

    if len(parts) != 2 or not parts[1].isdigit():
        return

    service_id = int(parts[1])
    service = await get_service(service_id)

    if not service:
        await callback.message.edit_text(
            "Услуга не найдена.",
            reply_markup=back_to_main_menu()
        )
        return

    duration = service["duration_minutes"] or "уточняется"

    text = (
        f"<b>{service['title']}</b>\n\n"
        f"{service['description'] or ''}\n\n"
        f"💰 Цена: <b>{service['price']}</b>\n"
        f"⏱ Длительность: {duration} мин."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Записаться",
                    callback_data=f"book:start:{service_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К услугам",
                    callback_data=f"category:{service['category']}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 В главное меню",
                    callback_data="main_menu"
                )
            ],
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)

@router.callback_query(F.data == "promo")
async def show_promo(callback: CallbackQuery):
    await callback.message.answer(
        "🔥 <b>Актуальные предложения</b>\n\n"
        "• Скидка 15% в день рождения\n"
        "• Скидка 5% для подписчиков канала\n"
        "• Скидки на продукцию\n\n"
        "Товары ограничены."
        "Чтобы записаться, нажмите кнопку ниже",
    reply_markup=back_to_main_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "contacts")
async def show_contacts(callback: CallbackQuery):
    await callback.message.answer(
        "📍 <b>Адрес:</b>\n"
        "Нижний Новгород, Кукуево, 67\n\n"
        "⏰ Часы работы:\n"
        "Пн-Пт: 15.30 - 21.00\n"
        "Сб: 8.00 - 21.00\n"
        "Вс: выходной",
        reply_markup=back_to_main_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "faq")
async def show_faq(callback: CallbackQuery):
    await callback.message.answer(
        "❓ <b>Частые вопросы</b>\n\n"
        "Скоро здесь появятся ответы на популярные вопросы.",
    reply_markup=back_to_main_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "main_menu")
async def back_to_manu(callback: CallbackQuery):
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=main_menu()
    )
    await callback.answer()