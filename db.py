import aiosqlite
from datetime import datetime, date
from typing import Optional, List, Dict, Any
import json
import os

DB_PATH = os.getenv("DB_PATH", "smart_bot.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                timezone TEXT DEFAULT 'Europe/Moscow',
                notify_morning TEXT DEFAULT '09:00',
                notify_evening TEXT DEFAULT '21:00',
                created_at TEXT
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                target_value REAL,
                current_value REAL DEFAULT 0,
                unit TEXT DEFAULT '',
                deadline TEXT,
                status TEXT DEFAULT 'active',  -- active, completed, failed, archived
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monthly_focus (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_id INTEGER,
                user_id INTEGER,
                month INTEGER,  -- 1-6 relative to goal start
                year INTEGER,
                title TEXT NOT NULL,
                target_value REAL,
                current_value REAL DEFAULT 0,
                unit TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                created_at TEXT,
                FOREIGN KEY (goal_id) REFERENCES goals(id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                goal_id INTEGER,
                monthly_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                task_type TEXT DEFAULT 'weekly',  -- daily, weekly, monthly
                target_value REAL,
                current_value REAL DEFAULT 0,
                unit TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',  -- pending, in_progress, partial, completed, failed, postponed
                due_date TEXT,
                completed_at TEXT,
                created_at TEXT,
                priority INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (goal_id) REFERENCES goals(id),
                FOREIGN KEY (monthly_id) REFERENCES monthly_focus(id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS checkins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task_id INTEGER,
                date TEXT,
                value REAL,
                note TEXT,
                mood INTEGER,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                period_type TEXT,  -- daily, weekly, monthly
                period_key TEXT,
                content TEXT,
                productivity_score REAL,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        await db.commit()


async def get_or_create_user(user_id: int, username: str = None, full_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
        if user:
            return dict(user)
        
        # Пытаемся вставить, игнорируя если уже существует (защита от гонок)
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, full_name, datetime.now().isoformat())
        )
        await db.commit()
        
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
        return dict(user) if user else {"user_id": user_id, "username": username, "full_name": full_name}


async def create_goal(user_id: int, title: str, description: str, target_value: float, 
                      unit: str, deadline: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO goals (user_id, title, description, target_value, unit, deadline, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, title, description, target_value, unit, deadline, datetime.now().isoformat())
        )
        await db.commit()
        return cursor.lastrowid


async def get_active_goal(user_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM goals WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_goal_progress(goal_id: int, current_value: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE goals SET current_value = ? WHERE id = ?",
            (current_value, goal_id)
        )
        await db.commit()


async def create_monthly_focus(goal_id: int, user_id: int, month: int, year: int, 
                                title: str, target_value: float = None, unit: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO monthly_focus (goal_id, user_id, month, year, title, target_value, unit, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (goal_id, user_id, month, year, title, target_value, unit, datetime.now().isoformat())
        )
        await db.commit()
        return cursor.lastrowid


async def get_current_monthly(user_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM monthly_focus 
               WHERE user_id = ? AND status = 'active' 
               ORDER BY year DESC, month DESC LIMIT 1""",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_task(user_id: int, title: str, task_type: str = "weekly",
                      goal_id: int = None, monthly_id: int = None,
                      target_value: float = None, unit: str = "",
                      due_date: str = None, priority: int = 1,
                      description: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO tasks 
               (user_id, goal_id, monthly_id, title, description, task_type, 
                target_value, unit, due_date, priority, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, goal_id, monthly_id, title, description, task_type,
             target_value, unit, due_date, priority, datetime.now().isoformat())
        )
        await db.commit()
        return cursor.lastrowid


async def get_tasks(user_id: int, status: str = None, task_type: str = None, 
                    only_active: bool = True) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM tasks WHERE user_id = ?"
        params = [user_id]
        
        if only_active:
            query += " AND status NOT IN ('completed', 'failed', 'postponed')"
        if status:
            query += " AND status = ?"
            params.append(status)
        if task_type:
            query += " AND task_type = ?"
            params.append(task_type)
            
        query += " ORDER BY priority DESC, due_date ASC, id ASC"
        
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_overdue_or_unfinished(user_id: int) -> List[Dict]:
    """Задачи, которые должны были быть сделаны, но не закрыты"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        today = date.today().isoformat()
        async with db.execute(
            """SELECT * FROM tasks 
               WHERE user_id = ? 
               AND status IN ('pending', 'in_progress', 'partial')
               AND (due_date IS NULL OR due_date <= ?)
               ORDER BY due_date ASC""",
            (user_id, today)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def update_task_progress(task_id: int, current_value: float = None, 
                                status: str = None, note: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if current_value is not None and status is not None:
            completed_at = datetime.now().isoformat() if status in ('completed', 'failed') else None
            await db.execute(
                """UPDATE tasks SET current_value = ?, status = ?, completed_at = ? 
                   WHERE id = ?""",
                (current_value, status, completed_at, task_id)
            )
        elif current_value is not None:
            await db.execute(
                "UPDATE tasks SET current_value = ? WHERE id = ?",
                (current_value, task_id)
            )
        elif status is not None:
            completed_at = datetime.now().isoformat() if status in ('completed', 'failed') else None
            await db.execute(
                "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
                (status, completed_at, task_id)
            )
        await db.commit()


async def get_task(task_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def add_checkin(user_id: int, task_id: int, value: float, note: str = "", mood: int = 3):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO checkins (user_id, task_id, date, value, note, mood, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, task_id, date.today().isoformat(), value, note, mood, datetime.now().isoformat())
        )
        await db.commit()


async def get_stats(user_id: int) -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Всего задач
        async with db.execute(
            "SELECT COUNT(*) as total FROM tasks WHERE user_id = ?", (user_id,)
        ) as c:
            total = (await c.fetchone())["total"]
        
        async with db.execute(
            "SELECT COUNT(*) as done FROM tasks WHERE user_id = ? AND status = 'completed'", (user_id,)
        ) as c:
            done = (await c.fetchone())["done"]
            
        async with db.execute(
            "SELECT COUNT(*) as partial FROM tasks WHERE user_id = ? AND status = 'partial'", (user_id,)
        ) as c:
            partial = (await c.fetchone())["partial"]
            
        async with db.execute(
            "SELECT COUNT(*) as failed FROM tasks WHERE user_id = ? AND status = 'failed'", (user_id,)
        ) as c:
            failed = (await c.fetchone())["failed"]
            
        async with db.execute(
            "SELECT COUNT(*) as active FROM tasks WHERE user_id = ? AND status IN ('pending','in_progress','partial')", (user_id,)
        ) as c:
            active = (await c.fetchone())["active"]
        
        goal = await get_active_goal(user_id)
        goal_progress = 0
        if goal and goal.get("target_value"):
            goal_progress = min(100, (goal.get("current_value", 0) / goal["target_value"]) * 100)
        
        return {
            "total_tasks": total,
            "completed": done,
            "partial": partial,
            "failed": failed,
            "active": active,
            "completion_rate": round((done / total * 100) if total > 0 else 0, 1),
            "goal_progress": round(goal_progress, 1),
            "goal": goal
        }
