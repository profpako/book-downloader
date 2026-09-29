"""Vault credenziali/token per-servizio (Fase 1.4). keyring OS + fallback file locale."""
from __future__ import annotations

import json
from pathlib import Path

SERVICE = "book-downloader"

try:
    import keyring  # macOS Keychain / Windows Credential Manager
except ImportError:  # pragma: no cover
    keyring = None  # type: ignore

_fallback = Path.home() / ".book-downloader" / "vault.json"


def _read_fallback() -> dict:
    if _fallback.exists():
        try:
            return json.loads(_fallback.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def _write_fallback(data: dict) -> None:
    _fallback.parent.mkdir(parents=True, exist_ok=True)
    _fallback.write_text(json.dumps(data), encoding="utf-8")


def _set(key: str, value: str) -> None:
    if keyring is not None:
        try:
            keyring.set_password(SERVICE, key, value)
            return
        except Exception:
            pass
    data = _read_fallback()
    data[key] = value
    _write_fallback(data)


def _get(key: str) -> str | None:
    if keyring is not None:
        try:
            v = keyring.get_password(SERVICE, key)
            if v:
                return v
        except Exception:
            pass
    return _read_fallback().get(key)


def _delete(key: str) -> None:
    if keyring is not None:
        try:
            keyring.delete_password(SERVICE, key)
        except Exception:
            pass
    data = _read_fallback()
    data.pop(key, None)
    _write_fallback(data)


def save_token(service_id: str, token: str) -> None:
    _set(f"token:{service_id}", token)


def load_token(service_id: str) -> str | None:
    return _get(f"token:{service_id}")


def save_user(service_id: str, username: str) -> None:
    _set(f"user:{service_id}", username)


def load_user(service_id: str) -> str | None:
    return _get(f"user:{service_id}")


def save_password(service_id: str, password: str) -> None:
    _set(f"pwd:{service_id}", password)


def load_password(service_id: str) -> str | None:
    return _get(f"pwd:{service_id}")


def save_last_service(service_id: str) -> None:
    _set("last-service", service_id)


def load_last_service() -> str | None:
    return _get("last-service")


def save_setting(name: str, value: str) -> None:
    data = _read_fallback()
    data[f"setting:{name}"] = value
    _write_fallback(data)


def load_setting(name: str) -> str | None:
    return _read_fallback().get(f"setting:{name}")


def save_cookies(service_id: str, cookies: dict) -> None:
    import json as _json
    _set(f"cookies:{service_id}", _json.dumps(cookies))


def load_cookies(service_id: str) -> dict:
    import json as _json
    raw = _get(f"cookies:{service_id}")
    try:
        return _json.loads(raw) if raw else {}
    except ValueError:
        return {}


def clear_service(service_id: str) -> None:
    for prefix in ("token:", "user:", "pwd:", "cookies:"):
        _delete(f"{prefix}{service_id}")
