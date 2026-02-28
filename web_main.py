#!/usr/bin/env python3
import asyncio
import json
import os
import re
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine.roast_engine import RoastEngine, RoastState
from profiles.profile_loader import RoastProfile

BASE_DIR = Path(__file__).resolve().parent
PROFILES_DIR = BASE_DIR / "profiles"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


class StartRequest(BaseModel):
    profile_file: str


class StageRequest(BaseModel):
    stage: str


class FanRequest(BaseModel):
    percent: int


class TempOffsetRequest(BaseModel):
    delta_c: float


class ProfileContentRequest(BaseModel):
    content: str


class ProfileSaveAsRequest(BaseModel):
    file_name: str
    content: str


class WebRoastManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._engine = RoastEngine(log_file="roast_log.csv")
        self._engine.subscribe(self._on_engine_snapshot)
        self._current_log_file = BASE_DIR / "roast_log.csv"
        self._clients: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []

    def _on_engine_snapshot(self, snapshot: dict) -> None:
        with self._lock:
            clients = list(self._clients)
        for loop, queue in clients:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, snapshot)
            except Exception:
                continue

    def register_ws(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        with self._lock:
            self._clients.append((loop, queue))

    def unregister_ws(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._clients = [(lp, q) for lp, q in self._clients if q is not queue]

    def _safe_profile_path(self, profile_file: str) -> Path:
        candidate = (PROFILES_DIR / profile_file).resolve()
        if not str(candidate).startswith(str(PROFILES_DIR.resolve())):
            raise HTTPException(status_code=400, detail="Invalid profile path")
        if not candidate.exists():
            raise HTTPException(status_code=404, detail="Profile not found")
        return candidate

    def _safe_new_profile_path(self, file_name: str) -> Path:
        name = (file_name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="file_name is required")
        if not name.endswith(".json"):
            name = f"{name}.json"
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            raise HTTPException(status_code=400, detail="file_name must use only letters, numbers, dot, dash, underscore")

        candidate = (PROFILES_DIR / name).resolve()
        if not str(candidate).startswith(str(PROFILES_DIR.resolve())):
            raise HTTPException(status_code=400, detail="Invalid profile path")
        if candidate.exists():
            raise HTTPException(status_code=409, detail=f"Profile already exists: {name}")
        return candidate

    def list_profiles(self):
        profiles = []
        for path in sorted(PROFILES_DIR.glob("*.json")):
            try:
                profile = RoastProfile(str(path))
                profiles.append(
                    {
                        "file": path.name,
                        "name": profile.name,
                        "description": profile.description,
                        "has_preheat": bool(profile.preheat),
                    }
                )
            except Exception as exc:
                profiles.append(
                    {
                        "file": path.name,
                        "name": path.stem,
                        "description": f"Failed to parse: {exc}",
                        "has_preheat": False,
                    }
                )
        return profiles

    def _validate_profile_payload(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Profile must be a JSON object")

        roast_profile = payload.get("roast_profile")
        if not isinstance(roast_profile, list) or not roast_profile:
            raise HTTPException(status_code=400, detail="'roast_profile' must be a non-empty list")

        for idx, point in enumerate(roast_profile):
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise HTTPException(status_code=400, detail=f"roast_profile[{idx}] must be [elapsed_s, temp_c]")
            try:
                float(point[0])
                float(point[1])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"roast_profile[{idx}] values must be numeric")

        pid_gains = payload.get("pid_gains")
        if pid_gains is not None:
            if not isinstance(pid_gains, list) or len(pid_gains) != 3:
                raise HTTPException(status_code=400, detail="'pid_gains' must be [kp, ki, kd]")
            try:
                [float(v) for v in pid_gains]
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="'pid_gains' values must be numeric")

        pwm_period = payload.get("pwm_period")
        if pwm_period is not None:
            try:
                if float(pwm_period) <= 0:
                    raise HTTPException(status_code=400, detail="'pwm_period' must be > 0")
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="'pwm_period' must be numeric")

        preheat = payload.get("preheat")
        if preheat is not None:
            if not isinstance(preheat, dict):
                raise HTTPException(status_code=400, detail="'preheat' must be an object or null")
            if "temp_c" not in preheat:
                raise HTTPException(status_code=400, detail="'preheat.temp_c' is required when preheat is set")
            try:
                float(preheat["temp_c"])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="'preheat.temp_c' must be numeric")

    def get_profile_content(self, profile_file: str):
        profile_path = self._safe_profile_path(profile_file)
        try:
            content = profile_path.read_text(encoding="utf-8")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed reading profile: {exc}")
        return {"file": profile_path.name, "content": content}

    def save_profile_content(self, profile_file: str, content: str):
        profile_path = self._safe_profile_path(profile_file)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc.msg} (line {exc.lineno})")

        self._validate_profile_payload(payload)

        try:
            profile_path.write_text(content.rstrip() + "\n", encoding="utf-8")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed saving profile: {exc}")
        return {"ok": True, "message": f"Profile saved: {profile_path.name}"}

    def save_profile_as(self, file_name: str, content: str):
        profile_path = self._safe_new_profile_path(file_name)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc.msg} (line {exc.lineno})")

        self._validate_profile_payload(payload)

        try:
            profile_path.write_text(content.rstrip() + "\n", encoding="utf-8")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed saving profile: {exc}")
        return {"ok": True, "message": f"Profile saved as: {profile_path.name}", "file": profile_path.name}

    def start(self, profile_file: str):
        profile_path = self._safe_profile_path(profile_file)
        with self._lock:
            state = self._engine.get_snapshot().state
            if state not in (RoastState.IDLE.value, RoastState.FAULT.value):
                raise HTTPException(status_code=409, detail=f"Session is busy ({state})")

            timestamp = datetime.now().strftime("%y-%m-%d-%H%M%S")
            log_path = BASE_DIR / f"{timestamp}-roast.csv"
            self._engine = RoastEngine(log_file=str(log_path))
            self._engine.subscribe(self._on_engine_snapshot)
            self._current_log_file = log_path
            result = self._engine.start(str(profile_path))

        if not result.ok:
            raise HTTPException(status_code=400, detail=result.message)
        return {"ok": True, "message": result.message}

    def bean_drop(self):
        result = self._engine.bean_drop()
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.message)
        return {"ok": True, "message": result.message}

    def mark_stage(self, stage: str):
        result = self._engine.mark_stage(stage)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.message)
        return {"ok": True, "message": result.message}

    def set_fan(self, percent: int):
        result = self._engine.set_fan(percent)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.message)
        return {"ok": True, "message": result.message}

    def set_temp_offset(self, delta_c: float):
        result = self._engine.set_temp_offset(delta_c)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.message)
        return {"ok": True, "message": result.message}

    def stop(self):
        result = self._engine.stop()
        return {"ok": result.ok, "message": result.message}

    def emergency_stop(self):
        result = self._engine.emergency_shutdown()
        return {"ok": result.ok, "message": result.message}

    def snapshot(self):
        return asdict(self._engine.get_snapshot())

    def csv_path(self) -> Path:
        return self._current_log_file


manager = WebRoastManager()
app = FastAPI(title="ProfileRoasting Web UI")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=500, detail="UI template not found")
    return index_file.read_text(encoding="utf-8")


@app.get("/api/profiles")
def get_profiles():
    return manager.list_profiles()


@app.post("/api/profiles/save-as")
def save_profile_as(request: ProfileSaveAsRequest):
    return manager.save_profile_as(request.file_name, request.content)


@app.get("/api/profiles/{profile_file}")
def get_profile_content(profile_file: str):
    return manager.get_profile_content(profile_file)


@app.put("/api/profiles/{profile_file}")
def update_profile_content(profile_file: str, request: ProfileContentRequest):
    return manager.save_profile_content(profile_file, request.content)


@app.post("/api/session/start")
def start_session(request: StartRequest):
    return manager.start(request.profile_file)


@app.post("/api/session/bean-drop")
def bean_drop():
    return manager.bean_drop()


@app.post("/api/session/mark-stage")
def mark_stage(request: StageRequest):
    return manager.mark_stage(request.stage)


@app.post("/api/session/fan")
def set_fan(request: FanRequest):
    return manager.set_fan(request.percent)


@app.post("/api/session/temp-offset")
def set_temp_offset(request: TempOffsetRequest):
    return manager.set_temp_offset(request.delta_c)


@app.post("/api/session/stop")
def stop_session():
    return manager.stop()


@app.post("/api/session/emergency-stop")
def emergency_stop_session():
    return manager.emergency_stop()


@app.get("/api/session")
def get_session():
    return manager.snapshot()


@app.get("/api/session/csv")
def get_csv():
    csv_path = manager.csv_path()
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="No roast log available yet")
    return FileResponse(path=str(csv_path), filename=csv_path.name, media_type="text/csv")


@app.websocket("/ws/session")
async def ws_session(websocket: WebSocket):
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    loop = asyncio.get_running_loop()
    manager.register_ws(loop, queue)

    try:
        await websocket.send_json(manager.snapshot())
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                payload = manager.snapshot()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister_ws(queue)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_main:app", host="0.0.0.0", port=8000, reload=False)
