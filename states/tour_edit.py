from aiogram.fsm.state import State, StatesGroup


class EditTourState(StatesGroup):
    waiting_for_company = State()
