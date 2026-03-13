from aiogram.fsm.state import State, StatesGroup


class CheckDateState(StatesGroup):
    waiting_for_date = State()
