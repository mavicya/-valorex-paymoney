from aiogram.fsm.state import State, StatesGroup


class TaskFlow(StatesGroup):
    waiting_proof = State()


class WithdrawFlow(StatesGroup):
    select_currency = State()
    enter_requisites = State()
    enter_amount     = State()
    confirm          = State()


class AdminBroadcastFlow(StatesGroup):
    enter_text = State()
