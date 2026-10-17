# tools.py - the functions the assistant is allowed to call
import sqlite3
from datetime import datetime

DB_FILE = "assistant.db"   # SQLite stores the whole database in this one file


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row   # lets us use row["description"] instead of row[1]
    return conn


def setup_database():
    """Create the tables if needed, and upgrade older databases."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                done        INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL,
                due_date    TEXT
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")

        # MIGRATION: older databases were created before due_date existed
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(tasks)")]
        if "due_date" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN due_date TEXT")


def now():
    return datetime.now().isoformat(sep=" ", timespec="minutes")

def validate_date(value):
    """Make sure a date looks like 2026-10-17. Returns None for blank dates."""
    if not value:
        return None
    datetime.strptime(value, "%Y-%m-%d")   # raises an error if the format is wrong
    return value


# ---------- TASKS ----------

def add_task(description, due_date=None):
    due_date = validate_date(due_date)
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (description, created_at, due_date) VALUES (?, ?, ?)",
            (description, now(), due_date),
        )
    due_text = f" (due {due_date})" if due_date else ""
    return f"Added task #{cur.lastrowid}: {description}{due_text}"


def list_tasks(include_done=False, due_on=None):
    query = "SELECT * FROM tasks WHERE 1=1"
    params = []
    if not include_done:
        query += " AND done = 0"
    if due_on:
        query += " AND due_date = ?"
        params.append(validate_date(due_on))
    query += " ORDER BY due_date IS NULL, due_date, id"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    if not rows:
        return "No tasks found."
    lines = []
    for r in rows:
        check = "x" if r["done"] else " "
        due = f" (due {r['due_date']})" if r["due_date"] else ""
        lines.append(f"#{r['id']} [{check}] {r['description']}{due}") 
    return "\n".join(lines)


def complete_task(task_id):
    with get_connection() as conn:
        cur = conn.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task_id,))
    if cur.rowcount == 0:
        return f"No task with id {task_id}."
    return f"Marked task #{task_id} as done."


def set_due_date(task_id, due_date):
    due_date = validate_date(due_date)
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE tasks SET due_date = ? WHERE id = ?",
            (due_date, task_id),
        )
    if cur.rowcount == 0:
        return f"No task with id {task_id}."
    return f"Set due date for task #{task_id} to {due_date}."


# ---------- NOTES ----------

def save_note(content):
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO notes (content, created_at) VALUES (?, ?)",
            (content, now()),
        )
    return f"Saved note #{cur.lastrowid}."


def search_notes(keyword=""):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM notes WHERE content LIKE ? ORDER BY id DESC LIMIT 20",
            (f"%{keyword}%",),
        ).fetchall()
    if not rows:
        return "No notes found."
    return "\n".join(f"#{r['id']} ({r['created_at']}): {r['content']}" for r in rows)



def delete_note(note_id):
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    if cur.rowcount == 0:
        return f"No note with id {note_id}."
    return f"Deleted note #{note_id}."


# ---------- TOOL MENU FOR CLAUDE ----------
# Claude never sees the Python code above. It only sees these descriptions,
# so write them clearly. They're how Claude decides which tool to use.

TOOL_DEFINITIONS = [
    {
        "name": "add_task",
        "description": "Add a new task to Lee's to-do list, with an optional due date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What needs to be done"},
                "due_date": {
                    "type": "string",
                    "description": "Due date in YYYY-MM-DD format. Convert words like 'tomorrow' or 'Friday' using today's date. Omit if there is no deadline.",
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List Lee's tasks, soonest due first. Shows only open tasks unless include_done is true.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_done": {"type": "boolean", "description": "Also show completed tasks"},
                "due_on": {"type": "string", "description": "Only show tasks due on this date (YYYY-MM-DD)"},
            },
        },
    },
    {
        "name": "complete_task",
        "description": "Mark a task as done using its ID number. List tasks first if the ID is unknown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "The task's ID number"}
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "set_due_date",
        "description": "Set or update a task's due date using its ID number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "The task's ID number"},
                "due_date": {"type": "string", "description": "Due date in YYYY-MM-DD format"},
            },
            "required": ["task_id", "due_date"],
        },
    },
    {
        "name": "save_note",
        "description": "Save a note for Lee to look up later.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The full text of the note"}
            },
            "required": ["content"],
        },
    },
    {
        "name": "search_notes",
        "description": "Search Lee's saved notes by keyword. Leave keyword empty to list recent notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Word or phrase to search for"}
            },
        },
    },
    {
        "name": "delete_note",
        "description": "Delete a saved note using its ID number. Search notes first if the ID is unknown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "integer", "description": "The note's ID number"}
            },
            "required": ["note_id"],
        },
    },
]

# Maps each tool name to the real Python function that does the work
TOOL_FUNCTIONS = {
    "add_task": add_task,
    "list_tasks": list_tasks,
    "complete_task": complete_task,
    "set_due_date": set_due_date,
    "save_note": save_note,
    "search_notes": search_notes,
    "delete_note": delete_note,
}


def run_tool(name, tool_input):
    """Run the tool Claude asked for and return the result as text."""
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return f"Error: unknown tool '{name}'"
    try:
        return func(**tool_input)   # ** unpacks {"task_id": 3} into task_id=3
    except Exception as e:
        return f"Error running {name}: {e}"