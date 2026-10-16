# tools.py - the functions the assistant is allowed to call
import sqlite3
from datetime import datetime

DB_FILE = "assistant.db"   # SQLite stores the whole database in this one file


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row   # lets us use row["description"] instead of row[1]
    return conn


def setup_database():
    """Create the tables if they don't exist yet. Safe to run every startup."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                done        INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            )""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")


def now():
    return datetime.now().isoformat(sep=" ", timespec="minutes")


# ---------- TASKS ----------

def add_task(description):
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (description, created_at) VALUES (?, ?)",
            (description, now()),
        )
    return f"Added task #{cur.lastrowid}: {description}"


def list_tasks(include_done=False):
    with get_connection() as conn:
        if include_done:
            rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        else:
            rows = conn.execute("SELECT * FROM tasks WHERE done = 0 ORDER BY id").fetchall()
    if not rows:
        return "No tasks found."
    return "\n".join(
        f"#{r['id']} [{'x' if r['done'] else ' '}] {r['description']}" for r in rows
    )


def complete_task(task_id):
    with get_connection() as conn:
        cur = conn.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task_id,))
    if cur.rowcount == 0:
        return f"No task with id {task_id}."
    return f"Marked task #{task_id} as done."


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
        "description": "Add a new task to Lee's to-do list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What needs to be done"}
            },
            "required": ["description"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List Lee's tasks. Shows only open tasks unless include_done is true.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_done": {"type": "boolean", "description": "Also show completed tasks"}
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