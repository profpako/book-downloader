"""Build PyInstaller sidecar (Fase 2.1). Uso: python build_sidecar.py [--no-playwright]."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
DIST = HERE / "dist"
OUT = HERE.parent / "src-tauri" / "binaries"


def triple() -> str:
    m = platform.machine().lower()
    arch = "aarch64" if m in ("arm64", "aarch64") else "x86_64"
    if sys.platform == "darwin":
        return f"{arch}-apple-darwin"
    if sys.platform == "win32":
        return "x86_64-pc-windows-msvc"
    return f"{arch}-unknown-linux-gnu"


def main() -> None:
    env = os.environ.copy()
    if "--no-playwright" not in sys.argv:
        env["PLAYWRIGHT_BROWSERS_PATH"] = "0"
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"], cwd=HERE, env=env)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--console", "--name", "api",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "keyring.backends.macOS",
        "--hidden-import", "keyring.backends.Windows",
        "--collect-submodules", "services",
        "sidecar_api.py",
    ]
    if "--no-playwright" not in sys.argv:
        cmd += ["--collect-all", "playwright"]
    subprocess.check_call(cmd, cwd=HERE, env=env)
    t = triple()
    ext = ".exe" if sys.platform == "win32" else ""
    src = DIST / f"api{ext}"
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / f"api-{t}{ext}"
    shutil.copyfile(src, dst)
    print(f"OK: {dst} (triple {t})")


if __name__ == "__main__":
    main()
