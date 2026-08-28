from aiogram.fsm.state import State, StatesGroup


class PersonalPlaceCreateState(StatesGroup):
    name = State()
    category = State()
    general_location = State()
    landmark = State()
    note = State()
    confirm = State()


class PersonalPlaceEditState(StatesGroup):
    value = State()
