import json
import secrets
import random
import string
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/portal", tags=["developer-portal"])

APPS_FILE = Path("data/apps.json")

CATEGORIES = {"supplement", "fitness", "mental-health", "nutrition", "diagnostics", "other"}


class RegisterAppRequest(BaseModel):
    name:             str
    description:      str
    category:         str
    developer_email:  str
    website:          Optional[str] = None


def _load() -> list:
    if not APPS_FILE.exists():
        return []
    return json.loads(APPS_FILE.read_text())


def _save(apps: list) -> None:
    APPS_FILE.write_text(json.dumps(apps, indent=2))


def _new_app_id() -> str:
    chars = string.ascii_lowercase + string.digits
    return "app_" + "".join(random.choices(chars, k=8))


def _new_secret() -> str:
    return "sk_live_" + secrets.token_hex(24)


@router.post("/apps", status_code=201)
async def register_app(req: RegisterAppRequest):
    if req.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {sorted(CATEGORIES)}")

    apps = _load()
    app = {
        "app_id":          _new_app_id(),
        "secret_key":      _new_secret(),
        "name":            req.name.strip(),
        "description":     req.description.strip(),
        "category":        req.category,
        "developer_email": req.developer_email.strip(),
        "website":         req.website,
        "status":          "active",
        "created_at":      datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    apps.append(app)
    _save(apps)
    return app  # includes secret_key — only returned once on creation


@router.get("/apps")
async def list_apps():
    apps = _load()
    # Never return secret_key in list view
    return [
        {k: v for k, v in a.items() if k != "secret_key"}
        for a in apps
    ]


@router.get("/apps/{app_id}")
async def get_app(app_id: str):
    app = next((a for a in _load() if a["app_id"] == app_id), None)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app  # includes secret_key for credential display


@router.delete("/apps/{app_id}", status_code=200)
async def delete_app(app_id: str):
    apps = _load()
    filtered = [a for a in apps if a["app_id"] != app_id]
    if len(filtered) == len(apps):
        raise HTTPException(status_code=404, detail="App not found")
    _save(filtered)
    return {"deleted": True, "app_id": app_id}
