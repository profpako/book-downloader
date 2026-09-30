"""Installer check without downloads: python3 tests/test_install_mac.py."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


INSTALLER = Path(__file__).resolve().parents[1] / "install_mac.sh"


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


def check(old_python=False, old_node=False):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copyfile(INSTALLER, root / "install_mac.sh")
        (root / "sidecar").mkdir()
        (root / "sidecar/requirements.txt").write_text("fastapi\n")
        (root / "app").mkdir()
        (root / "app/package-lock.json").write_text("{}\n")
        executable(root / "start_app.sh", 'echo start >> "$CHECK_ROOT/actions"\n')

        bin_dir = root / "bin"
        for name in ("python3.14", "python3.13", "python3.12", "python3.11", "python3.10", "python3"):
            fake_python(bin_dir / name, not old_python)
        fake_python(root / "new-python", True)
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
        env.update(PATH=f"{bin_dir}:/usr/bin:/bin", CHECK_ROOT=str(root))
        result = subprocess.run(
            ["/bin/bash", str(root / "install_mac.sh")],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        actions = (root / "actions").read_text().splitlines()
        assert actions[-4:] == ["pip", "playwright", "npm", "start"]
        assert ("brew-python@3.14" in actions) == old_python
        assert ("brew-node@24" in actions) == old_node


if __name__ == "__main__":
    check()
    check(old_python=True)
    check(old_node=True)
    print("macOS installer checks passed (existing, outdated Python, outdated Node).")
