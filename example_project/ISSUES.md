# Example Project — Issues for LLM Demo

This project is a small Flask task management API with deliberate bugs and missing features.
Each issue below is a realistic prompt a developer would give an LLM.

---

## Issue 1 — Bug: Duplicate usernames are allowed

**File:** `models/user.py`

The `username` column is missing `unique=True`. Two users can register with the same username,
which breaks any UI that displays usernames as identifiers.

**Prompt to LLM:**
> "Users can register with duplicate usernames. The `username` field in the User model should be unique. Fix it and make sure the register route returns a proper error if the username is already taken."

---

## Issue 2 — Bug: `updated_at` is never updated on task save

**Files:** `models/task.py`, `routes/tasks.py`

`updated_at` is set to `datetime.utcnow` at creation but never updated when a task is modified.
The `update_task` route commits changes without touching `updated_at`.

**Prompt to LLM:**
> "The `updated_at` field on tasks is always the same as `created_at` even after edits. Fix the Task model and the update route so `updated_at` reflects the last modification time."

---

## Issue 3 — Security: Passwords are hashed with MD5

**File:** `routes/auth.py`

`hash_password` uses `hashlib.md5`, which is cryptographically broken and unsuitable for
password storage. Should use `werkzeug.security.generate_password_hash` (bcrypt-backed).

**Prompt to LLM:**
> "Our password hashing uses MD5 which is insecure. Replace it with `werkzeug.security.generate_password_hash` and `check_password_hash`. Make sure existing login logic still works."

---

## Issue 4 — Performance: Task list has no pagination

**Files:** `routes/tasks.py`, `utils/pagination.py`

`GET /api/tasks/` returns every task for the user with no limit. `utils/pagination.py` already
has a working `paginate_query` helper that was written but never wired up.

**Prompt to LLM:**
> "The task list endpoint returns all tasks at once with no pagination. There's already a `paginate_query` utility in `utils/pagination.py`. Wire it up in the list endpoint and the user tasks endpoint so they support `page` and `page_size` query params."

---

## Issue 5 — Security: Authorization missing on `GET /api/tasks/<id>`

**File:** `routes/tasks.py`

`get_task` checks authentication but not authorization. Any logged-in user can read any other
user's task by guessing the task ID. The `update_task` and `delete_task` routes correctly check
`task.user_id != user_id` but `get_task` does not.

**Prompt to LLM:**
> "Any authenticated user can read any task by ID, even tasks that belong to other users. The GET single task endpoint is missing an ownership check. Fix it to return 403 if the task doesn't belong to the current user."

---

## Issue 6 — Feature: Search endpoint is not implemented

**File:** `routes/tasks.py`

`GET /api/tasks/search` returns 501. It should support filtering tasks by:
- `q` — full-text search on title and description
- `status` — filter by status
- `priority` — filter by priority
- `tag` — filter by tag name
- `due_before` / `due_after` — date range filter

**Prompt to LLM:**
> "The search endpoint at `GET /api/tasks/search` just returns 501. Implement it to support filtering by `q` (searches title and description), `status`, `priority`, `tag`, `due_before`, and `due_after`. Results should be paginated."

---

## Issue 7 — Performance: N+1 query in task stats

**File:** `routes/tasks.py`

`GET /api/tasks/stats` loads all task objects into Python memory and counts them in a loop.
For a user with thousands of tasks this is slow. Should use SQL aggregation:
`db.session.query(Task.status, db.func.count()).group_by(Task.status)`.

**Prompt to LLM:**
> "The `/api/tasks/stats` endpoint loads every task into memory to compute counts. Rewrite it to use SQL aggregation queries instead so it stays fast regardless of how many tasks a user has."

---

## Issue 8 — Security: User profile endpoint has no authentication

**File:** `routes/users.py`

`GET /api/users/<id>` returns any user's profile without requiring login. Email addresses
are included in `to_dict()`, so this leaks PII to unauthenticated callers.

**Prompt to LLM:**
> "The `GET /api/users/<id>` endpoint returns user data including email addresses without requiring authentication. Add an auth check and make sure unauthenticated requests get a 401."

---

## Issue 9 — Testing: Task route tests are incomplete

**File:** `tests/test_tasks.py`

The test file has only 3 tests and a list of `# MISSING` comments. The authorization bypass
in Issue 5 has no test catching it. Create, update, and delete have no coverage.

**Prompt to LLM:**
> "The task tests are missing coverage for create, update, delete, and the authorization check on GET. Write the missing tests. Make sure one test specifically verifies that a user cannot read another user's task."

---

## Issue 10 — Feature: Add task sorting to the list endpoint

**File:** `routes/tasks.py`

`GET /api/tasks/` returns tasks in insertion order. Users should be able to sort by:
- `sort_by` — field to sort on: `created_at`, `updated_at`, `due_date`, `priority`, `title`
- `order` — `asc` or `desc` (default: `desc` for dates, `asc` for title)

**Prompt to LLM:**
> "The task list endpoint returns tasks in no particular order. Add `sort_by` and `order` query parameters so users can sort by `created_at`, `updated_at`, `due_date`, `priority`, or `title`. Default to `created_at desc`."
