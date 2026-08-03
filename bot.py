import asyncio
import logging
from datetime import datetime, date, timedelta
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import aiosqlite
from db import (
    init_db, get_or_create_user, create_goal, get_active_goal,
    update_goal_progress, create_monthly_focus, get_current_monthly,
    create_task, get_tasks, get_overdue_or_unfinished, update_task_progress,
    get_task, add_checkin, get_stats, DB_PATH,
    create_habit, get_habits, get_habit, mark_habit_done, get_all_active_habits
)
from keyboards import (
    main_menu, goal_actions, task_status_kb, confirm_add_task_kb,
    tasks_list_kb, yes_no_kb, skip_kb, habit_done_kb, habits_list_kb
)
from states import GoalSetup, MonthlySetup, TaskAdd, ProgressUpdate, GoalProgressUpdate
from utils import (
    format_goal, format_task, progress_bar, get_motivation,
    make_daily_report, status_emoji, calc_productivity_score
)

# ================== НАСТРОЙКИ ==================
import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN") or "8720834264:AAHfoAQ_qclQAj1Hcv0JH5QmtOidUCwFjSE"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()


# ================== СТАРТ ==================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name
    )
    
    goal = await get_active_goal(message.from_user.id)
    
    text = (
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Я твой дневник продуктивности.\n"
        "Помогаю ставить цели на полгода по SMART, разбивать их на месяцы и недели, "
        "отслеживать реальный прогресс (не только галочки) и не раздувать список задач, "
        "пока старые не закрыты.\n\n"
    )
    
    if goal:
        text += format_goal(goal)
        text += "\n\nИспользуй меню ниже."
    else:
        text += (
            "🎯 <b>Сначала давай поставим главную цель на 6 месяцев.</b>\n\n"
            "Напиши /newgoal или нажми кнопку «Моя цель»."
        )
    
    await message.answer(text, reply_markup=main_menu())


# ================== НОВАЯ ЦЕЛЬ ==================
@router.message(Command("newgoal"))
@router.message(F.text == "🎯 Моя цель")
async def my_goal(message: Message, state: FSMContext):
    goal = await get_active_goal(message.from_user.id)
    
    if goal:
        text = format_goal(goal) + "\n\n" + get_motivation(
            (goal.get("current_value") or 0) / goal["target_value"] * 100 if goal.get("target_value") else 0
        )
        await message.answer(text, reply_markup=goal_actions())
    else:
        await state.set_state(GoalSetup.waiting_title)
        await message.answer(
            "🎯 <b>Ставим цель на полгода</b>\n\n"
            "Шаг 1/5 — <b>Конкретность (Specific)</b>\n\n"
            "Напиши цель максимально конкретно.\n"
            "Плохо: «Сделать бизнес успешным»\n"
            "Хорошо: «Выйти со своим продуктом на рынок Италии»\n"
            "Хорошо: «Заработать 180 000 рублей чистыми за 6 месяцев»\n\n"
            "Напиши свою цель:"
        )


@router.message(GoalSetup.waiting_title)
async def goal_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(GoalSetup.waiting_description)
    await message.answer(
        "Шаг 2/5 — Зачем тебе это? (Relevant)\n\n"
        "Коротко напиши, почему эта цель важна. Это поможет не бросить на середине."
    )


@router.message(GoalSetup.waiting_description)
async def goal_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(GoalSetup.waiting_target)
    await message.answer(
        "Шаг 3/5 — <b>Измеримость (Measurable)</b>\n\n"
        "Какое числовое значение будет означать успех?\n"
        "Примеры: 180000 (рублей), 30 (клиентов), 15 (кг), 100 (публикаций)\n\n"
        "Напиши только число:"
    )


@router.message(GoalSetup.waiting_target)
async def goal_target(message: Message, state: FSMContext):
    try:
        value = float(message.text.replace(" ", "").replace(",", "."))
        await state.update_data(target_value=value)
        await state.set_state(GoalSetup.waiting_unit)
        await message.answer(
            "Шаг 4/5 — В чём измеряем?\n\n"
            "Напиши единицу: руб, кг, клиентов, %, шт, часов и т.д.\n"
            "Или нажми «Пропустить», если просто число."
        , reply_markup=skip_kb())
    except ValueError:
        await message.answer("Нужно число. Например: 30000 или 15.5")


@router.callback_query(F.data == "skip", GoalSetup.waiting_unit)
async def goal_unit_skip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(unit="")
    await state.set_state(GoalSetup.waiting_deadline)
    await callback.message.edit_text(
        "Шаг 5/5 — <b>Срок (Time-bound)</b>\n\n"
        "До какой даты цель должна быть достигнута?\n"
        "Формат: ГГГГ-ММ-ДД\n"
        "Например: 2027-01-31"
    )
    await callback.answer()


@router.message(GoalSetup.waiting_unit)
async def goal_unit(message: Message, state: FSMContext):
    await state.update_data(unit=message.text.strip())
    await state.set_state(GoalSetup.waiting_deadline)
    await message.answer(
        "Шаг 5/5 — <b>Срок (Time-bound)</b>\n\n"
        "До какой даты цель должна быть достигнута?\n"
        "Формат: ГГГГ-ММ-ДД\n"
        "Например: 2027-01-31"
    )


@router.message(GoalSetup.waiting_deadline)
async def goal_deadline(message: Message, state: FSMContext):
    try:
        deadline = datetime.strptime(message.text.strip(), "%Y-%m-%d").date()
        if deadline <= date.today():
            await message.answer("Дата должна быть в будущем.")
            return
        
        data = await state.get_data()
        await state.update_data(deadline=deadline.isoformat())
        
        text = (
            "Проверь цель:\n\n"
            f"🎯 <b>{data['title']}</b>\n"
            f"📝 {data.get('description', '')}\n"
            f"📊 Цель: {data['target_value']:g} {data.get('unit', '')}\n"
            f"📅 До: {deadline.isoformat()}\n\n"
            "Всё верно?"
        )
        await state.set_state(GoalSetup.confirm)
        await message.answer(text, reply_markup=yes_no_kb("goal_confirm"))
    except ValueError:
        await message.answer("Неверный формат. Нужно ГГГГ-ММ-ДД, например 2027-02-01")


@router.callback_query(F.data == "goal_confirm:yes", GoalSetup.confirm)
async def goal_confirm_yes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    goal_id = await create_goal(
        callback.from_user.id,
        data["title"],
        data.get("description", ""),
        data["target_value"],
        data.get("unit", ""),
        data["deadline"]
    )
    await state.clear()
    
    await callback.message.edit_text(
        "✅ Цель сохранена!\n\n" + format_goal({
            "title": data["title"],
            "description": data.get("description"),
            "target_value": data["target_value"],
            "current_value": 0,
            "unit": data.get("unit", ""),
            "deadline": data["deadline"],
            "status": "active"
        }) + "\n\nТеперь можешь добавить фокус месяца или задачи."
    )
    await callback.message.answer("Меню:", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "goal_confirm:no", GoalSetup.confirm)
async def goal_confirm_no(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено. Начни заново через /newgoal")
    await callback.answer()


# ================== ОБНОВЛЕНИЕ ПРОГРЕССА ЦЕЛИ ==================
@router.callback_query(F.data == "update_goal_progress")
async def start_goal_progress(callback: CallbackQuery, state: FSMContext):
    goal = await get_active_goal(callback.from_user.id)
    if not goal:
        await callback.answer("Сначала поставь цель", show_alert=True)
        return
    
    await state.set_state(GoalProgressUpdate.waiting_value)
    await state.update_data(goal_id=goal["id"])
    
    current = goal.get("current_value") or 0
    target = goal["target_value"]
    unit = goal.get("unit") or ""
    
    await callback.message.answer(
        f"Текущий прогресс: {current:g} / {target:g} {unit}\n"
        f"{progress_bar(current, target)}\n\n"
        "Введи новое фактическое значение (число):"
    )
    await callback.answer()


@router.message(GoalProgressUpdate.waiting_value)
async def save_goal_progress(message: Message, state: FSMContext):
    try:
        value = float(message.text.replace(" ", "").replace(",", "."))
        data = await state.get_data()
        await update_goal_progress(data["goal_id"], value)
        await state.clear()
        
        goal = await get_active_goal(message.from_user.id)
        percent = (value / goal["target_value"] * 100) if goal["target_value"] else 0
        
        text = f"✅ Прогресс обновлён!\n\n{format_goal(goal)}\n\n{get_motivation(percent)}"
        await message.answer(text, reply_markup=main_menu())
    except ValueError:
        await message.answer("Нужно число.")


# ================== ЗАДАЧИ ==================
@router.message(F.text == "📋 Задачи")
async def list_tasks(message: Message):
    tasks = await get_tasks(message.from_user.id, only_active=True)
    unfinished = await get_overdue_or_unfinished(message.from_user.id)
    
    if not tasks and not unfinished:
        await message.answer("Активных задач нет. Добавь первую через «➕ Добавить задачу»")
        return
    
    text = "📋 <b>Твои активные задачи:</b>\n\n"
    for t in tasks:
        text += format_task(t) + "\n"
    
    if unfinished:
        text += f"\n⚠️ Незакрытых/просроченных: {len(unfinished)}"
    
    await message.answer(text, reply_markup=tasks_list_kb(tasks))


@router.callback_query(F.data.startswith("task:"))
async def show_task(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    task = await get_task(task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    
    has_metric = bool(task.get("target_value"))
    text = format_task(task)
    await callback.message.answer(text, reply_markup=task_status_kb(task_id, has_metric))
    await callback.answer()


@router.callback_query(F.data.startswith("status:"))
async def change_status(callback: CallbackQuery, state: FSMContext):
    _, task_id, new_status = callback.data.split(":")
    task_id = int(task_id)
    task = await get_task(task_id)
    
    if new_status == "partial":
        await state.set_state(ProgressUpdate.waiting_value)
        await state.update_data(task_id=task_id, action="partial")
        await callback.message.answer(
            f"Задача: {task['title']}\n"
            f"Цель: {task.get('target_value') or '—'} {task.get('unit') or ''}\n\n"
            "Введи фактическое значение, которого достиг:"
        )
        await callback.answer()
        return
    
    if new_status == "completed" and task.get("target_value"):
        # Если есть метрика — ставим current = target
        await update_task_progress(task_id, current_value=task["target_value"], status="completed")
    else:
        await update_task_progress(task_id, status=new_status)
    
    # Если выполнили — можно обновить и главную цель (если связано)
    emoji = status_emoji(new_status)
    await callback.message.edit_text(f"{emoji} Статус обновлён: <b>{new_status}</b>\n\n{format_task(await get_task(task_id))}")
    await callback.answer("Готово")


@router.message(ProgressUpdate.waiting_value)
async def save_partial(message: Message, state: FSMContext):
    try:
        value = float(message.text.replace(" ", "").replace(",", "."))
        data = await state.get_data()
        task_id = data["task_id"]
        task = await get_task(task_id)
        
        target = task.get("target_value") or 0
        if target > 0 and value >= target:
            status = "completed"
        elif value > 0:
            status = "partial"
        else:
            status = "pending"
        
        await update_task_progress(task_id, current_value=value, status=status)
        await add_checkin(message.from_user.id, task_id, value)
        
        await state.clear()
        
        updated = await get_task(task_id)
        percent = (value / target * 100) if target else 0
        
        text = (
            f"✅ Записал: {value:g} {task.get('unit') or ''}\n\n"
            f"{format_task(updated)}\n"
            f"{get_motivation(percent)}"
        )
        await message.answer(text, reply_markup=main_menu())
    except ValueError:
        await message.answer("Нужно число.")


# ================== ДОБАВЛЕНИЕ ЗАДАЧИ (с проверкой долгов) ==================
@router.message(F.text == "➕ Добавить задачу")
async def add_task_start(message: Message, state: FSMContext):
    unfinished = await get_overdue_or_unfinished(message.from_user.id)
    
    if unfinished:
        text = (
            f"⚠️ У тебя есть <b>{len(unfinished)}</b> незакрытых задач.\n\n"
            "Рекомендую сначала закрыть или перенести старые, "
            "иначе список будет раздуваться и мотивация упадёт.\n\n"
            "Что делаем?"
        )
        for t in unfinished[:5]:
            text += f"\n• {t['title'][:40]}"
        await message.answer(text, reply_markup=confirm_add_task_kb())
        return
    
    await state.set_state(TaskAdd.waiting_title)
    await message.answer(
        "➕ Новая задача\n\n"
        "Напиши название задачи (конкретно и в действии):\n"
        "Пример: «Сделать 5 холодных звонков» или «Написать 3 поста»"
    )


@router.callback_query(F.data == "force_add_task")
async def force_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TaskAdd.waiting_title)
    await callback.message.edit_text(
        "Ок, добавляем всё равно.\n\n"
        "Напиши название задачи:"
    )
    await callback.answer()


@router.callback_query(F.data == "show_debts")
async def show_debts(callback: CallbackQuery):
    unfinished = await get_overdue_or_unfinished(callback.from_user.id)
    text = "⚠️ <b>Твои долги:</b>\n\n"
    for t in unfinished:
        text += format_task(t) + "\n"
    await callback.message.edit_text(text, reply_markup=tasks_list_kb(unfinished))
    await callback.answer()


@router.message(TaskAdd.waiting_title)
async def task_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(TaskAdd.waiting_type)
    await message.answer(
        "Тип задачи:\n"
        "1 — ежедневная\n"
        "2 — на неделю\n"
        "3 — на месяц\n\n"
        "Напиши цифру 1, 2 или 3:"
    )


@router.message(TaskAdd.waiting_type)
async def task_type(message: Message, state: FSMContext):
    mapping = {"1": "daily", "2": "weekly", "3": "monthly"}
    t = mapping.get(message.text.strip())
    if not t:
        await message.answer("Напиши 1, 2 или 3")
        return
    
    await state.update_data(task_type=t)
    await state.set_state(TaskAdd.waiting_target)
    await message.answer(
        "Есть ли у задачи числовой результат?\n"
        "Если да — напиши целевое число (например 5 или 10000).\n"
        "Если нет — напиши 0 или «нет»."
    )


@router.message(TaskAdd.waiting_target)
async def task_target(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if text in ("0", "нет", "no", "-"):
        await state.update_data(target_value=None, unit="")
        await state.set_state(TaskAdd.waiting_due)
        await message.answer("До какой даты задача? (ГГГГ-ММ-ДД) или напиши «сегодня» / «неделя»")
        return
    
    try:
        value = float(text.replace(" ", "").replace(",", "."))
        await state.update_data(target_value=value)
        await state.set_state(TaskAdd.waiting_unit)
        await message.answer("Единица измерения (руб, шт, клиентов...) или «-»:")
    except ValueError:
        await message.answer("Число или «нет»")


@router.message(TaskAdd.waiting_unit)
async def task_unit(message: Message, state: FSMContext):
    unit = message.text.strip()
    if unit == "-":
        unit = ""
    await state.update_data(unit=unit)
    await state.set_state(TaskAdd.waiting_due)
    await message.answer("До какой даты? (ГГГГ-ММ-ДД) или «сегодня» / «неделя» / «месяц»")


@router.message(TaskAdd.waiting_due)
async def task_due(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    today = date.today()
    
    if text in ("сегодня", "today"):
        due = today.isoformat()
    elif text in ("неделя", "week"):
        due = (today + timedelta(days=7)).isoformat()
    elif text in ("месяц", "month"):
        due = (today + timedelta(days=30)).isoformat()
    else:
        try:
            due = datetime.strptime(text, "%Y-%m-%d").date().isoformat()
        except ValueError:
            await message.answer("Формат ГГГГ-ММ-ДД или «сегодня»/«неделя»")
            return
    
    data = await state.get_data()
    goal = await get_active_goal(message.from_user.id)
    monthly = await get_current_monthly(message.from_user.id)
    
    task_id = await create_task(
        user_id=message.from_user.id,
        title=data["title"],
        task_type=data["task_type"],
        goal_id=goal["id"] if goal else None,
        monthly_id=monthly["id"] if monthly else None,
        target_value=data.get("target_value"),
        unit=data.get("unit", ""),
        due_date=due
    )
    
    await state.clear()
    
    task = await get_task(task_id)
    await message.answer(
        f"✅ Задача добавлена!\n\n{format_task(task)}",
        reply_markup=main_menu()
    )


# ================== ОТМЕТИТЬ ПРОГРЕСС (быстрый) ==================
@router.message(F.text == "✅ Отметить прогресс")
async def quick_progress(message: Message):
    tasks = await get_tasks(message.from_user.id, only_active=True)
    if not tasks:
        await message.answer("Нет активных задач.")
        return
    
    await message.answer(
        "Выбери задачу, по которой хочешь отметить прогресс:",
        reply_markup=tasks_list_kb(tasks)
    )


# ================== ОТЧЁТ ==================
@router.message(F.text == "📊 Отчёт")
@router.message(Command("report"))
async def report(message: Message):
    stats = await get_stats(message.from_user.id)
    tasks = await get_tasks(message.from_user.id, only_active=True)
    unfinished = await get_overdue_or_unfinished(message.from_user.id)
    
    text = make_daily_report(stats, tasks, unfinished)
    await message.answer(text, reply_markup=main_menu())


# ================== НАСТРОЙКИ ==================
@router.message(F.text == "⚙️ Настройки")
async def settings(message: Message):
    await message.answer(
        "⚙️ <b>Настройки напоминаний</b>\n\n"
        "Часовой пояс: <b>Алматы (Asia/Almaty)</b>\n\n"
        "Сейчас работают:\n"
        "• Утро — 09:00\n"
        "• Вечер — 21:00\n"
        "• Воскресенье 20:00 — напоминание по главной цели\n\n"
        "Чтобы изменить время, напиши:\n"
        "<code>утро 08:30</code>\n"
        "<code>вечер 22:00</code>"
    )


@router.message(F.text.regexp(r"(?i)утро\s+(\d{1,2}:\d{2})"))
async def set_morning(message: Message):
    import re
    match = re.search(r"(\d{1,2}:\d{2})", message.text)
    if match:
        time_str = match.group(1)
        await message.answer(f"✅ Утреннее напоминание будет в <b>{time_str}</b> (Алматы)\nПока используется стандартное время. Полная настройка в следующем обновлении.")


@router.message(F.text.regexp(r"(?i)вечер\s+(\d{1,2}:\d{2})"))
async def set_evening(message: Message):
    import re
    match = re.search(r"(\d{1,2}:\d{2})", message.text)
    if match:
        time_str = match.group(1)
        await message.answer(f"✅ Вечернее напоминание будет в <b>{time_str}</b> (Алматы)\nПока используется стандартное время. Полная настройка в следующем обновлении.")


# ================== НАПОМИНАНИЯ ==================
async def send_morning_reminders(bot: Bot):
    """Утреннее напоминание"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
    
    for user in users:
        try:
            user_id = user["user_id"]
            tasks = await get_tasks(user_id, only_active=True)
            unfinished = await get_overdue_or_unfinished(user_id)
            goal = await get_active_goal(user_id)
            
            text = "☀️ <b>Доброе утро!</b>\n\n"
            
            if goal:
                current = goal.get("current_value") or 0
                target = goal.get("target_value") or 1
                text += f"Твоя цель: <b>{goal['title']}</b>\n"
                text += f"{progress_bar(current, target)}\n\n"
            
            if unfinished:
                text += f"⚠️ Незакрытых задач: {len(unfinished)}\n"
            
            if tasks:
                text += "Можно поработать над:\n"
                for t in tasks[:4]:
                    text += f"• {t['title'][:45]}\n"
            else:
                text += "Активных задач пока нет.\n"
            
            text += "\nКогда сделаешь — нажми «✅ Отметить прогресс»"
            
            await bot.send_message(user_id, text, reply_markup=main_menu())
        except Exception as e:
            logger.error(f"Ошибка утреннего напоминания {user_id}: {e}")


async def send_evening_reminders(bot: Bot):
    """Вечернее напоминание"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
    
    for user in users:
        try:
            user_id = user["user_id"]
            stats = await get_stats(user_id)
            unfinished = await get_overdue_or_unfinished(user_id)
            
            text = "🌙 <b>Вечерний чек-ин</b>\n\n"
            text += f"Прогресс по цели: <b>{stats.get('goal_progress', 0):.0f}%</b>\n"
            text += f"Активных задач: {stats.get('active', 0)}\n"
            
            if unfinished:
                text += f"\n⚠️ Незакрытых задач: {len(unfinished)}\nЛучше закрыть или перенести.\n"
            
            text += "\nКак прошёл день? Отметь, что сделал."
            
            await bot.send_message(user_id, text, reply_markup=main_menu())
        except Exception as e:
            logger.error(f"Ошибка вечернего напоминания {user_id}: {e}")


async def send_weekly_goal_reminder(bot: Bot):
    """Воскресное напоминание по главной цели"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
    
    for user in users:
        try:
            user_id = user["user_id"]
            goal = await get_active_goal(user_id)
            stats = await get_stats(user_id)
            
            if not goal:
                continue
            
            current = goal.get("current_value") or 0
            target = goal.get("target_value") or 1
            percent = min(100, (current / target) * 100)
            
            text = "📅 <b>Конец недели — проверка главной цели</b>\n\n"
            text += f"🎯 {goal['title']}\n"
            text += f"{progress_bar(current, target)}\n"
            text += f"{current:g} / {target:g} {goal.get('unit') or ''}\n\n"
            text += get_motivation(percent) + "\n\n"
            
            if percent < 30:
                text += "На этой неделе стоит сильнее сфокусироваться на цели."
            elif percent < 70:
                text += "Есть прогресс. Продолжай в том же духе на следующей неделе."
            else:
                text += "Отличный темп! Так держать."
            
            text += "\n\nМожешь обновить прогресс цели прямо сейчас."
            
            await bot.send_message(user_id, text, reply_markup=main_menu())
        except Exception as e:
            logger.error(f"Ошибка недельного напоминания {user_id}: {e}")


# ================== ЗАПУСК ==================
async def main():
    await init_db()
    
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    # Планировщик (часовой пояс Алматы)
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    
    scheduler = AsyncIOScheduler(timezone="Asia/Almaty")
    
    # Утро 09:00
    scheduler.add_job(send_morning_reminders, CronTrigger(hour=9, minute=0), args=[bot])
    # Вечер 21:00
    scheduler.add_job(send_evening_reminders, CronTrigger(hour=21, minute=0), args=[bot])
    # Воскресенье 20:00 — главная цель
    scheduler.add_job(send_weekly_goal_reminder, CronTrigger(day_of_week="sun", hour=20, minute=0), args=[bot])
    
    scheduler.start()
    logger.info("Планировщик запущен (Алматы): утро 09:00, вечер 21:00, вс 20:00 — цель")
    
    # Режим работы: webhook (для Render Web Service) или polling
    WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "").rstrip("/")
    PORT = int(os.getenv("PORT", 10000))
    
    logger.info(f"WEBHOOK_HOST = '{WEBHOOK_HOST}'")
    logger.info(f"PORT = {PORT}")
    
    if WEBHOOK_HOST:
        # --- WEBHOOK режим (для Render Free Web Service) ---
        from aiohttp import web
        
        WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
        WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
        
        async def handle_webhook(request):
            try:
                update = await request.json()
                await dp.feed_raw_update(bot, update)
                return web.Response(text="ok")
            except Exception as e:
                logger.error(f"Webhook error: {e}")
                return web.Response(status=500)
        
        async def health(request):
            return web.Response(text="Bot is alive")
        
        app = web.Application()
        app.router.add_post(WEBHOOK_PATH, handle_webhook)
        app.router.add_get("/", health)
        app.router.add_get("/health", health)
        
        # Устанавливаем webhook
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook установлен: {WEBHOOK_URL}")
        logger.info("=== БОТ ЗАПУЩЕН В РЕЖИМЕ WEBHOOK ===")
        
        # Правильный запуск внутри существующего event loop
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        
        # Держим процесс живым
        await asyncio.Event().wait()
    else:
        # --- POLLING режим ---
        logger.warning("WEBHOOK_HOST не задан! Запускаю polling.")
        logger.warning("На Render Free это приведёт к конфликтам. Обязательно добавь WEBHOOK_HOST.")
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("=== БОТ ЗАПУЩЕН В РЕЖИМЕ POLLING ===")
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
