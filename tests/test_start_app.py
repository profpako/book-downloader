"""Check launcher selection without starting servers: python3 tests/test_start_app.py."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


LAUNCHER = Path(__file__).resolve().parents[1] / "start_app.sh"


def check(mode):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copyfile(LAUNCHER, root / "start_app.sh")
        (root / "sidecar").mkdir()
        bin_dir = root / "bin"
        bin_dir.mkdir()

        def executable(path, body):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("#!/bin/bash\nset -eu\n" + body)
            path.chmod(0o755)

        executable(bin_dir / "curl", '[[ "$*" == *":8923/health"* && -f "$CHECK_ROOT/ready" ]]\n')
        executable(bin_dir / "npm", 'echo npm > "$CHECK_ROOT/frontend"\n')
        python_body = (
            'printf "%s\\n" "$0" "${PLAYWRIGHT_BROWSERS_PATH:-}" '
            '"${PYTHONDONTWRITEBYTECODE:-}" > "$CHECK_ROOT/selected"\n'
            'touch "$CHECK_ROOT/ready"\n'
        )
        executable(bin_dir / "python", python_body)
        if mode != "fallback":
            executable(root / ".venv/bin/python", python_body)
        expected = root / ".venv/bin/python"
        if mode == "fallback":
            expected = bin_dir / "python"
        elif mode in ("custom", "missing"):
            expected = root / "custom environment/bin/python"
            if mode == "custom":
                executable(expected, python_body)
            (root / ".env.local").write_text(
                f'export BOOK_DOWNLOADER_PYTHON="{expected}"\n'
                f'export PLAYWRIGHT_BROWSERS_PATH="{root}/custom browsers"\n'
            )
        env = os.environ.copy()
        for key in ("BOOK_DOWNLOADER_PYTHON", "PLAYWRIGHT_BROWSERS_PATH"):
            env.pop(key, None)
        env.update(PATH=f"{bin_dir}:/usr/bin:/bin", CHECK_ROOT=str(root))
        result = subprocess.run(["/bin/bash", str(root / "start_app.sh")],
                                env=env, capture_output=True, text=True, timeout=10)
        if mode == "missing":
            assert result.returncode == 1, result
            assert "Python non trovato:" in result.stderr, result.stderr
            assert not (root / "frontend").exists()
        else:
            assert result.returncode == 0, result.stderr
            browsers = str(root / "custom browsers") if mode == "custom" else ""
            assert (root / "selected").read_text().splitlines() == [str(expected), browsers, "1"]
            assert (root / "frontend").exists()


if __name__ == "__main__":
    for mode in ("venv", "fallback", "custom", "missing"):
        check(mode)
    print("Launcher checks passed (venv, fallback, custom, missing).")
