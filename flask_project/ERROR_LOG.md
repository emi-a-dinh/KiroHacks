# Error Log

When running `test_async_bug.py`, the following errors occur:

```
[2026-05-02 22:05:19,725] ERROR in app: Exception on / [GET]
Traceback (most recent call last):
  File "flask_project/src/flask/app.py", line 1597, in wsgi_app
    response = self.full_dispatch_request(ctx)
  File "flask_project/src/flask/app.py", line 1019, in full_dispatch_request
    return self.finalize_request(ctx, rv)
  File "flask_project/src/flask/app.py", line 1039, in finalize_request
    response = self.make_response(rv)
  File "flask_project/src/flask/app.py", line 1344, in make_response
    raise TypeError(
TypeError: The view function did not return a valid response. The return type must be a string, dict, list, tuple with headers or status, Response instance, or WSGI callable, but it was a coroutine.

RuntimeWarning: coroutine 'index' was never awaited
```
