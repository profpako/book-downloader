"""Installer check without downloads: python3 tests/test_install_mac.py."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


INSTALLER = Path(__file__).resolve().parents[1] / "install_mac.sh"
COMMAND = INSTALLER.with_name("INSTALLA_MAC.command")


def executable(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\nset -eu\n" + body)
    path.chmod(0o755)


def fake_python(path, compatible):
    status = 0 if compatible else 1
    executable(
        path,
        f'''case "${{1:-}}" in
  -c) exit {status} ;;
  --version) echo "Python {'3.12.0' if compatible else '3.9.0'}" ;;
  -m)
    if [[ "$2" == "venv" ]]; then
      target="${{!#}}"
      mkdir -p "$target/bin"
      cp "$0" "$target/bin/python"
    else
      echo "$2" >> "$CHECK_ROOT/actions"
      printf '%s|%s|%s\\n' "$0" "$2" "${{PLAYWRIGHT_BROWSERS_PATH:-}}" >> "$CHECK_ROOT/runtime-actions"
    fi
    ;;
esac
''',
    )


def fake_node(path, compatible):
    executable(
        path,
        f'''if [[ "${{1:-}}" == "--version" ]]; then
  echo v{'20' if compatible else '16'}.0.0
elif [[ "${{1:-}}" == "-e" ]]; then
  exit {0 if compatible else 1}
fi
''',
    )


def check(old_python=False, old_node=False, custom=False, missing=False, server_status=0, server_signal=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copyfile(INSTALLER, root / "install_mac.sh")
        shutil.copyfile(COMMAND, root / "INSTALLA_MAC.command")
        (root / "sidecar").mkdir()
        (root / "sidecar/requirements.txt").write_text("fastapi\n")
        (root / "app").mkdir()
        (root / "app/package-lock.json").write_text("{}\n")
        stop = f'kill -{server_signal} "$$"' if server_signal else f'exit {server_status}'
        executable(root / "start_app.sh", f'echo start >> "$CHECK_ROOT/actions"\n{stop}\n')

        bin_dir = root / "bin"
        for name in ("python3.14", "python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"):
            fake_python(bin_dir / name, not old_python)
        fake_python(root / "new-python", True)
        custom_python = root / "custom environment/bin/python"
        if custom or missing:
            if not missing:
                fake_python(custom_python, True)
            (root / ".env.local").write_text(
                f'export BOOK_DOWNLOADER_PYTHON="{custom_python}"\n'
                f'export PLAYWRIGHT_BROWSERS_PATH="{root}/custom browsers"\n'
            )
        executable(bin_dir / "uname", "echo Darwin\n")
        fake_node(bin_dir / "node", not old_node)
        fake_node(bin_dir / "node-new", True)
        executable(bin_dir / "npm", 'echo npm >> "$CHECK_ROOT/actions"\n')
        executable(
            bin_dir / "brew",
            '''case "$1" in
  list) exit 1 ;;
  install)
    echo "brew-$2" >> "$CHECK_ROOT/actions"
    mkdir -p "$CHECK_ROOT/brew/$2/bin"
    [[ "$2" != "python@3.14" ]] || cp "$CHECK_ROOT/new-python" "$CHECK_ROOT/brew/python@3.14/bin/python3.14"
    if [[ "$2" == "node@24" ]]; then
      cp "$CHECK_ROOT/bin/node-new" "$CHECK_ROOT/brew/node@24/bin/node"
      cp "$CHECK_ROOT/bin/npm" "$CHECK_ROOT/brew/node@24/bin/npm"
    fi
    ;;
  --prefix) echo "$CHECK_ROOT/brew/$2" ;;
esac
''',
        )

        env = os.environ.copy()
        for key in ("BOOK_DOWNLOADER_PYTHON", "PLAYWRIGHT_BROWSERS_PATH"):
            env.pop(key, None)
        env.update(PATH=f"{bin_dir}:/usr/bin:/bin", CHECK_ROOT=str(root))
        result = subprocess.run(
            ["/bin/bash", str(root / "INSTALLA_MAC.command")],
            env=env,
            input="\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
        if missing:
            assert result.returncode == 1, result
            assert "Python non trovato o non compatibile" in result.stderr
            assert "Installazione interrotta." in result.stderr
            assert "Server chiuso." not in result.stdout
            assert not (root / "actions").exists()
            assert not (root / ".venv").exists()
            return
        assert result.returncode == server_status, result.stderr
        assert "Server chiuso." in result.stdout
        assert "Installazione interrotta" not in result.stdout + result.stderr
        actions = (root / "actions").read_text().splitlines()
        assert actions[-4:] == ["pip", "playwright", "npm", "start"]
        assert ("brew-python@3.14" in actions) == (old_python and not custom)
        assert ("brew-node@24" in actions) == old_node
        selected = custom_python if custom else root / ".venv/bin/python"
        browsers = str(root / "custom browsers") if custom else ""
        assert (root / "runtime-actions").read_text().splitlines() == [
            f"{selected}|{module}|{browsers}" for module in ("pip", "playwright")
        ]
        assert (root / ".venv").exists() != custom


if __name__ == "__main__":
    check()
    check(old_python=True)
    check(old_node=True)
    check(old_python=True, custom=True)
    check(custom=True, old_node=True)
    check(missing=True)
    for status in (1, 130, 143):
        check(server_status=status)
    check(server_status=130, server_signal="INT")
    check(server_status=143, server_signal="TERM")
    print("macOS installer checks passed (existing, outdated Python/Node, custom, missing, shutdown).")
