"""HTTP API + static dashboard."""
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .router import RouterError

STATIC = Path(__file__).parent / "static"


class DevicePatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=64)
    trusted: Optional[bool] = None


class RouterLogin(BaseModel):
    url: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False


def create_app(store, scanner=None, router=None):
    app = FastAPI(title="AetherNode", version=__version__)

    def norm(mac):
        return mac.strip().lower().replace("-", ":")

    @app.get("/api/status")
    def status():
        return {"version": __version__, "counts": store.counts(),
                "scanner": dict(scanner.state) if scanner else None}

    @app.get("/api/devices")
    def devices():
        return store.devices()

    @app.patch("/api/devices/{mac}")
    def patch_device(mac: str, body: DevicePatch):
        dev = store.update(norm(mac), name=body.name, trusted=body.trusted)
        if dev is None:
            raise HTTPException(404, "Unknown device")
        return dev

    @app.delete("/api/devices/{mac}")
    def forget_device(mac: str):
        if not store.forget(norm(mac)):
            raise HTTPException(404, "Unknown device")
        return {"ok": True}

    @app.get("/api/events")
    def events(limit: int = 50):
        return store.events(min(max(limit, 1), 500))

    @app.post("/api/scan")
    def scan():
        if scanner is None:
            raise HTTPException(503, "Scanner is disabled")
        scanner.scan_now()
        return {"ok": True}

    def need_router():
        if router is None:
            raise HTTPException(503, "Router integration is disabled")
        return router

    @app.get("/api/router")
    def router_status():
        return need_router().public_state()

    @app.put("/api/router")
    def router_connect(body: RouterLogin):
        link = need_router()
        try:
            return link.connect(body.url, body.username, body.password, body.remember)
        except RouterError as e:
            raise HTTPException(400, str(e))

    @app.delete("/api/router")
    def router_disconnect():
        need_router().disconnect()
        return {"ok": True}

    @app.post("/api/router/refresh")
    def router_refresh():
        need_router().refresh()
        return {"ok": True}

    app.mount("/",StaticFiles(directory=STATIC, html=True), name="ui")
    return app
