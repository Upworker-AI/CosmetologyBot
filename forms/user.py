from aiogram.fsm.state import State, StatesGroup

class BookingStates(StatesGroup):
    choosing_service = State()
    choosing_date = State()
    entering_custom_date = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()
    entering_note = State()
    confirming = State()