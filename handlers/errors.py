import logging

from aiogram import Router
from aiogram.types import CallbackQuery, Message
from aiogram.types.error_event import ErrorEvent

from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)

router = Router()


@router.errors()
async def handle_errors(event: ErrorEvent):
    exception = event.exception
    logger.exception("Ошибка в боте: %s", exception)

    update = event.update

    callback = update.callback_query if update else None
    message = update.message if update else None

    try:
        if callback:
            await callback.answer(
                "Произошла ошибка. Попробуйте ещё раз.",
                show_alert=True
            )
        elif message:
            await message.answer(
                "Произошла ошибка. Попробуйте ещё раз или нажмите /start."
            )
    except TelegramBadRequest:
        pass

    return True