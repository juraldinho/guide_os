from aiogram.fsm.state import State, StatesGroup


class AddTourState(StatesGroup):
    date = State()
    company = State()
    city = State()
    status = State()
    income = State()
    conflict_confirm = State()
    
