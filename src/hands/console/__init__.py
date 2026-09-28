"""Minimal operator console for human-in-the-loop handoff of a live session.

- `app`     create_console_app: FastAPI app with intervention routes and the live websocket
- `live`    websocket protocol: frames out, lease-checked pointer/key input in
- `server`  ConsoleServer: uvicorn on 127.0.0.1 as a task on the run's own event loop
"""
