# Flask Project — Issues for Async View Bug Benchmark

This is a Flask project with a deliberate bug: async view functions are not properly awaited
during request dispatch, causing them to return coroutine objects instead of actual responses.
Each issue below targets diagnosing and fixing this bug from different angles.

---

## Issue 1 — Bug: Async route returns coroutine object instead of response

**File:** `src/flask/app.py`

When defining an async view function with `async def`, Flask should transparently handle
the coroutine by running it in an event loop. Instead, the route returns a raw coroutine
object like `<coroutine object index at 0x...>` as the response body.

**Prompt to LLM:**
> "I have a Flask app with an async route defined as `async def index(): return 'hello'`. When I hit the endpoint, instead of getting 'hello' back, I get a string representation of a coroutine object. The response body is something like `<coroutine object index at 0x7f...>`. What's going wrong and how do I fix it?"

---

## Issue 2 — Bug: TypeError when async view returns a dict for JSON response

**Files:** `src/flask/app.py`, `src/flask/sansio/app.py`

Flask's `make_response` expects a string, dict, or Response object. When an async view
returns a dict (for automatic JSON serialization), the coroutine object is passed to
`make_response` instead, causing a TypeError because coroutine is not a valid response type.

**Prompt to LLM:**
> "My async Flask route returns a dictionary like `return {'status': 'ok'}` which should be auto-serialized to JSON. But I'm getting a TypeError about the return type not being valid. It seems like the async function's return value isn't being properly resolved. Where in Flask's request handling does async view resolution happen, and what's broken?"

---

## Issue 3 — Bug: `ensure_sync` is bypassed in dispatch_request

**File:** `src/flask/app.py`

The `dispatch_request` method in `Flask` (app.py) is supposed to wrap async view functions
with `ensure_sync` before calling them. This wrapper runs the coroutine in an event loop
so WSGI workers get a synchronous result. The current code calls the view function directly
without `ensure_sync`, so async views return unawaited coroutines.

**Prompt to LLM:**
> "I'm looking at Flask's `dispatch_request` method in `src/flask/app.py`. It calls `self.view_functions[rule.endpoint](**view_args)` directly. I think it should be using `self.ensure_sync()` to wrap async view functions so they get properly awaited. Can you check the dispatch_request method and fix it so async views work correctly?"

---

## Issue 4 — Bug: Before/after request hooks work but async views don't

**Files:** `src/flask/app.py`, `src/flask/sansio/app.py`

Async `before_request` and `after_request` hooks work correctly because they are wrapped
with `ensure_sync` in `preprocess_request` and `process_response`. But the actual view
function dispatch is missing the same wrapping, creating an inconsistency where hooks
are async-safe but views are not.

**Prompt to LLM:**
> "I noticed that my async `before_request` hooks work fine, but my async view functions return coroutine objects instead of actual responses. Looking at the code, hooks use `self.ensure_sync(func)()` but the view dispatch seems different. Can you trace through the request lifecycle in `app.py` and find where the async view handling diverges from the hook handling?"

---

## Issue 5 — Bug: Async error handlers work but async views don't

**Files:** `src/flask/app.py`, `src/flask/sansio/app.py`

Error handlers registered with `@app.errorhandler` are wrapped with `ensure_sync` in
`handle_user_exception` and `handle_http_exception`. But the main view dispatch path
is missing this wrapping. This means async error handlers work but async views don't.

**Prompt to LLM:**
> "My async error handlers work perfectly — `@app.errorhandler(404)` with an `async def` handler returns the right response. But my regular async view functions return coroutine objects. Can you compare how error handlers and view functions are dispatched in `app.py` and find the discrepancy?"

---

## Issue 6 — Bug: Async views work in development but fail in production WSGI

**Files:** `src/flask/app.py`, `src/flask/sansio/app.py`

The `ensure_sync` method is designed to bridge async functions to synchronous WSGI workers.
Without it, async views might appear to work in some test setups but fail under production
WSGI servers like Gunicorn (sync workers) because the coroutine is never awaited.

**Prompt to LLM:**
> "My Flask app's async views seem to work sometimes in testing but return coroutine objects in production with Gunicorn sync workers. I think the issue is in how Flask bridges async views to sync WSGI. Can you look at the `dispatch_request` method and the `ensure_sync` method in `app.py` and tell me if the view functions are being properly wrapped for sync execution?"

---

## Issue 7 — Bug: Response status code is 200 but body is a coroutine string

**File:** `src/flask/app.py`

When an async view returns a string, Flask's `make_response` doesn't raise an error because
Python's `str()` on a coroutine produces a valid string like `<coroutine object ...>`. The
response has status 200 but the body is garbage. This is a silent failure that's hard to debug.

**Prompt to LLM:**
> "My Flask endpoint returns HTTP 200 but the response body is `<coroutine object hello at 0x...>` instead of the actual content. There's no error in the logs. The view function is `async def hello(): return 'Hello World'`. Why is Flask treating the coroutine as a valid string response instead of awaiting it?"

---

## Issue 8 — Fix: Add ensure_sync wrapping to dispatch_request

**File:** `src/flask/app.py`

The fix is to wrap the view function call in `dispatch_request` with `self.ensure_sync()`,
matching the pattern used for error handlers, before_request hooks, and after_request hooks
throughout the rest of `app.py`.

**Prompt to LLM:**
> "I've identified that `dispatch_request` in `src/flask/app.py` calls view functions directly without `ensure_sync`. Every other place in app.py that calls user-provided functions uses `self.ensure_sync(func)()`. Fix `dispatch_request` to use the same pattern so async view functions are properly awaited."

---

## Issue 9 — Testing: Write a test that catches the async view regression

**Files:** `src/flask/app.py`, `tests/test_async.py`

Write a regression test that creates a Flask app with an async view, makes a request,
and asserts the response body is the actual return value (not a coroutine string).
This test should fail with the current bug and pass after the fix.

**Prompt to LLM:**
> "Write a test for Flask that verifies async view functions return proper responses. Create a test app with `async def index(): return 'hello'`, make a GET request with the test client, and assert the response data is `b'hello'` not a coroutine string. Put it in a format consistent with Flask's existing test suite."

---

## Issue 10 — Investigation: Audit all ensure_sync call sites for consistency

**File:** `src/flask/app.py`

Audit every place in `app.py` where user-provided callables are invoked. Verify that each
one uses `self.ensure_sync()` wrapping. The dispatch_request bug suggests there may be
other call sites that are also missing the wrapping.

**Prompt to LLM:**
> "Audit `src/flask/app.py` for every place where user-provided functions are called (view functions, error handlers, before/after request hooks, teardown functions, template context processors). List each call site and whether it uses `self.ensure_sync()`. Identify any that are missing the wrapping and could have the same async bug."
