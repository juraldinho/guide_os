from aiogram.fsm.state import State, StatesGroup


class AddTourState(StatesGroup):
    company = State()
    city = State()
    date = State()
    status = State()
    income = State()
