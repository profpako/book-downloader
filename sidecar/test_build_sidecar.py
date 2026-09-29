"""Packaging check: the browser must be installed before freezing Python."""
from unittest.mock import patch

import build_sidecar


def test_browser_is_bundled():
    with patch.object(build_sidecar.sys, "argv", ["build_sidecar.py"]), \
         patch.object(build_sidecar.subprocess, "check_call") as run, \
         patch.object(build_sidecar.shutil, "copyfile"), \
         patch("pathlib.Path.mkdir"):
        build_sidecar.main()

    assert len(run.call_args_list) == 2
    assert run.call_args_list[0].args[0][-2:] == ["install", "chromium"]
    assert run.call_args_list[1].args[0][2:4] == ["PyInstaller", "--onefile"]
    assert all(c.kwargs["env"]["PLAYWRIGHT_BROWSERS_PATH"] == "0" for c in run.call_args_list)
