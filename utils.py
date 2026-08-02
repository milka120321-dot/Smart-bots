from typing import Optional


def progress_bar(current: float, target: float, length: int = 12) -> str:
    if not target or target <= 0:
        return "░" * length + " 0%"
    percent = min(100, max(0, (current / target) * 100))
    filled = int(length * percent / 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"{bar} {percent:.0f}%"


def status_emoji(status: str) -> str:
    return {
        "pending": "⬜",
        "in_progress": "🔄",
        "partial": "🟨",
        "completed": "✅",
        "failed": "❌",
        "postponed": "⏸",
        "active": "🟢"
    }.get(status, "▫️")


def format_task(task: dict) -> str:
    emoji = status_emoji(task["status"])
    text = f"{emoji} <b>{task['title']}</b>\n"
    
    if task.get("target_value"):
        current = task.get("current_value") or 0
        target = task["target_value"]
        unit = task.get("unit") or ""
        text += f"   {progress_bar(current, target)}  ({current:g} / {target:g} {unit})\n"
    
    if task.get("due_date"):
        text += f"   📅 до {task['due_date']}\n"
    
    if task.get("description"):
        text += f"   💬 {task['description'][:80]}\n"
    
    return text


def format_goal(goal: dict) -> str:
    if not goal:
        return "Цель ещё не поставлена."
    
    current = goal.get("current_value") or 0
    target = goal.get("target_value") or 0
    unit = goal.get("unit") or ""
    
    text = f"🎯 <b>{goal['title']}</b>\n\n"
    if goal.get("description"):
        text += f"{goal['description']}\n\n"
    
    text += f"📊 Прогресс: {progress_bar(current, target)}\n"
    text += f"💰 {current:g} / {target:g} {unit}\n"
    text += f"📅 Дедлайн: {goal.get('deadline', 'не указан')}\n"
    text += f"Статус: {status_emoji(goal.get('status', 'active'))} {goal.get('status', 'active')}"
    
    return text


def get_motivation(percent: float) -> str:
    if percent >= 100:
        return "🔥 Великолепно! Цель достигнута или перевыполнена!"
    elif percent >= 90:
        return "💪 Почти у цели! Остался финальный рывок."
    elif percent >= 70:
        return "👍 Хороший темп. Продолжай в том же духе."
    elif percent >= 50:
        return "🙂 Середина пути. Можно чуть ускориться."
    elif percent >= 30:
        return "😐 Есть прогресс, но можно лучше. Что мешает?"
    elif percent > 0:
        return "😕 Пока слабовато. Давай разберём, что пошло не так."
    else:
        return "🚀 Самое время начать. Первый шаг — самый важный."


def calc_productivity_score(stats: dict) -> float:
    """Простая формула продуктивности 0-100"""
    if stats["total_tasks"] == 0:
        return 0.0
    
    completed_weight = stats["completed"] * 1.0
    partial_weight = stats["partial"] * 0.6
    failed_weight = stats["failed"] * -0.3
    
    score = (completed_weight + partial_weight + failed_weight) / stats["total_tasks"] * 100
    # Добавляем влияние прогресса главной цели
    score = score * 0.7 + stats.get("goal_progress", 0) * 0.3
    return max(0, min(100, round(score, 1)))


def make_daily_report(stats: dict, tasks: list, unfinished: list) -> str:
    score = calc_productivity_score(stats)
    goal = stats.get("goal")
    
    text = "📊 <b>Отчёт по продуктивности</b>\n\n"
    
    if goal:
        text += format_goal(goal) + "\n\n"
        text += get_motivation(stats["goal_progress"]) + "\n\n"
    
    text += f"📈 <b>Общая статистика</b>\n"
    text += f"• Всего задач: {stats['total_tasks']}\n"
    text += f"• ✅ Выполнено: {stats['completed']}\n"
    text += f"• 🟨 Частично: {stats['partial']}\n"
    text += f"• ❌ Не выполнено: {stats['failed']}\n"
    text += f"• 🔄 В работе: {stats['active']}\n"
    text += f"• Процент закрытия: {stats['completion_rate']}%\n"
    text += f"• Индекс продуктивности: <b>{score}/100</b>\n\n"
    
    if unfinished:
        text += "⚠️ <b>Есть незакрытые задачи (долги):</b>\n"
        for t in unfinished[:5]:
            text += f"• {t['title'][:40]}\n"
        if len(unfinished) > 5:
            text += f"... и ещё {len(unfinished) - 5}\n"
        text += "\nРекомендую сначала закрыть или перенести их.\n"
    
    return text
