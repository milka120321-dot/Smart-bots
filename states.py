from aiogram.fsm.state import State, StatesGroup


class GoalSetup(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_target = State()
    waiting_unit = State()
    waiting_deadline = State()
    confirm = State()


class MonthlySetup(StatesGroup):
    waiting_title = State()
    waiting_target = State()
    waiting_unit = State()


class TaskAdd(StatesGroup):
    waiting_title = State()
    waiting_type = State()
    waiting_target = State()
    waiting_unit = State()
    waiting_due = State()
    confirm = State()


class ProgressUpdate(StatesGroup):
    waiting_value = State()
    waiting_note = State()


class GoalProgressUpdate(StatesGroup):
    waiting_value = State()
