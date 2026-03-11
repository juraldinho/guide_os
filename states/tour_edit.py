from aiogram.fsm.state import State, StatesGroup


class EditTourState(StatesGroup):
    waiting_for_company = State()
    waiting_for_city = State()
    waiting_for_income = State()
    waiting_for_note = State()
