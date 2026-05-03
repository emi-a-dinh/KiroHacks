# Flask Project — Issues for Async View Bug Benchmark

This is a Flask project with a deliberate bug: async view functions are not properly awaited
during request dispatch, causing them to return coroutine objects instead of actual responses.

---

## Issue 1 — Bug: Async route returns coroutine object instead of response

**File:** `src/flask/app.py`

When defining an async view function with `async def`, Flask should transparently handle
the coroutine by running it in an event loop. Instead, the route returns a raw coroutine
object like `<coroutine object index at 0x...>` as the response body.

**Prompt to LLM:**
> "I have a Flask app with an async route defined as `async def index(): return 'hello'`. When I hit the endpoint, instead of getting 'hello' back, I get a string representation of a coroutine object. The response body is something like `<coroutine object index at 0x7f...>`. What's going wrong and how do I fix it?"

---

## Issue 2 — Bug: `ensure_sync` is bypassed in dispatch_request

**File:** `src/flask/app.py`

The `dispatch_request` method in `Flask` (app.py) is supposed to wrap async view functions
with `ensure_sync` before calling them. This wrapper runs the coroutine in an event loop
so WSGI workers get a synchronous result. The current code calls the view function directly
without `ensure_sync`, so async views return unawaited coroutines.

**Prompt to LLM:**
> "I'm looking at Flask's `dispatch_request` method in `src/flask/app.py`. It calls `self.view_functions[rule.endpoint](**view_args)` directly. I think it should be using `self.ensure_sync()` to wrap async view functions so they get properly awaited. Can you check the dispatch_request method and fix it so async views work correctly?"

---

## Issue 3 — Fix: Add ensure_sync wrapping to dispatch_request

**File:** `src/flask/app.py`

The fix is to wrap the view function call in `dispatch_request` with `self.ensure_sync()`,
matching the pattern used for error handlers, before_request hooks, and after_request hooks
throughout the rest of `app.py`.

**Prompt to LLM:**
> "I've identified that `dispatch_request` in `src/flask/app.py` calls view functions directly without `ensure_sync`. Every other place in app.py that calls user-provided functions uses `self.ensure_sync(func)()`. Fix `dispatch_request` to use the same pattern so async view functions are properly awaited."
