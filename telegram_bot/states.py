from aiogram.fsm.state import State, StatesGroup


class DeliveryFlow(StatesGroup):
    supplier = State()
    roll_type = State()
    quantity = State()
    date = State()
    note = State()
    confirm = State()


class PaymentFlow(StatesGroup):
    supplier = State()
    roll_type = State()
    start_date = State()
    end_date = State()
    confirm = State()
