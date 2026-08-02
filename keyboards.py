from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="🎯 Моя цель"),
        KeyboardButton(text="📋 Задачи")
    )
    builder.row(
        KeyboardButton(text="🔄 Привычки"),
        KeyboardButton(text="✅ Отметить прогресс")
    )
    builder.row(
        KeyboardButton(text="📊 Отчёт"),
        KeyboardButton(text="➕ Добавить задачу")
    )
    builder.row(
        KeyboardButton(text="⚙️ Настройки")
    )
    return builder.as_markup(resize_keyboard=True)


def habit_done_kb(habit_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Сделал", callback_data=f"habit_done:{habit_id}"),
        InlineKeyboardButton(text="⏭ Пропустил", callback_data=f"habit_skip:{habit_id}")
    )
    return builder.as_markup()


def habits_list_kb(habits: list):
    builder = InlineKeyboardBuilder()
    for h in habits:
        streak = h.get("streak", 0)
        builder.row(
            InlineKeyboardButton(
                text=f"{'🔥' if streak > 0 else '▫️'} {h['title']} ({streak} дн.)",
                callback_data=f"habit_info:{h['id']}"
            )
        )
    builder.row(InlineKeyboardButton(text="➕ Новая привычка", callback_data="add_habit"))
    return builder.as_markup()


def goal_actions():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📈 Обновить прогресс цели", callback_data="update_goal_progress")
    )
    builder.row(
        InlineKeyboardButton(text="📅 Добавить фокус месяца", callback_data="add_monthly")
    )
    builder.row(
        InlineKeyboardButton(text="🗂 Архив / Завершить цель", callback_data="archive_goal")
    )
    return builder.as_markup()


def task_status_kb(task_id: int, has_metric: bool = False):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 В процессе", callback_data=f"status:{task_id}:in_progress"),
        InlineKeyboardButton(text="✅ Выполнено", callback_data=f"status:{task_id}:completed")
    )
    if has_metric:
        builder.row(
            InlineKeyboardButton(text="🟨 Частично (ввести число)", callback_data=f"status:{task_id}:partial")
        )
    builder.row(
        InlineKeyboardButton(text="❌ Не выполнено", callback_data=f"status:{task_id}:failed"),
        InlineKeyboardButton(text="⏸ Отложить", callback_data=f"status:{task_id}:postponed")
    )
    return builder.as_markup()


def confirm_add_task_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Всё равно добавить", callback_data="force_add_task"),
        InlineKeyboardButton(text="🔙 Сначала закрыть долги", callback_data="show_debts")
    )
    return builder.as_markup()


def tasks_list_kb(tasks: list):
    builder = InlineKeyboardBuilder()
    for t in tasks[:15]:  # ограничиваем
        status_emoji = {
            "pending": "⬜",
            "in_progress": "🔄",
            "partial": "🟨",
            "completed": "✅",
            "failed": "❌",
            "postponed": "⏸"
        }.get(t["status"], "▫️")
        
        title = t["title"][:35] + ("..." if len(t["title"]) > 35 else "")
        builder.row(
            InlineKeyboardButton(
                text=f"{status_emoji} {title}",
                callback_data=f"task:{t['id']}"
            )
        )
    return builder.as_markup()


def yes_no_kb(prefix: str):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"{prefix}:yes"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"{prefix}:no")
    )
    return builder.as_markup()


def skip_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip"))
    return builder.as_markup()
