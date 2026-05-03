"""Minimal reproduction of the async view bug.

Run this script to see the bug in action:
    python test_async_bug.py

Expected: Response body is "hello"
Actual: Response body is a coroutine string like "<coroutine object index at 0x...>"
"""
import sys
sys.path.insert(0, "src")

from flask import Flask

app = Flask(__name__)

@app.route("/")
async def index():
    return "hello"

@app.route("/json")
async def json_view():
    return {"status": "ok", "message": "async works"}

with app.test_client() as client:
    # Test 1: Simple string response
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    print(f"GET / status: {resp.status_code}")
    print(f"GET / body: {body}")
    
    if "coroutine" in body:
        print("BUG: Response contains coroutine object instead of 'hello'")
        print("ERROR: Async view function was not awaited during dispatch")
    elif body == "hello":
        print("OK: Async view returned correct response")
    
    print()
    
    # Test 2: JSON response
    resp2 = client.get("/json")
    body2 = resp2.get_data(as_text=True)
    print(f"GET /json status: {resp2.status_code}")
    print(f"GET /json body: {body2}")
    
    if "coroutine" in body2:
        print("BUG: JSON response contains coroutine object")
        print("ERROR: Async view function was not awaited during dispatch")
    elif "ok" in body2:
        print("OK: Async JSON view returned correct response")
