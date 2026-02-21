# Copyright (c) 2026 plumiume
# SPDX-License-Identifier: <<spdxid>>
# License: MIT License (https://opensource.org/licenses/MIT)
# See LICENSE.txt for details.


import importlib.util
from collections import namedtuple
from pathlib import Path


def _load_build_matrix_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "tools" / "build_matrix.py"
    spec = importlib.util.spec_from_file_location("build_matrix", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_disk_usage_path_windows_uses_system_drive(monkeypatch):
    module = _load_build_matrix_module()
    monkeypatch.setattr(module.platform, "system", lambda: "Windows")
    monkeypatch.setenv("SystemDrive", "D:")
    assert module._disk_usage_path() == "D:\\"


def test_disk_usage_path_windows_normalizes_trailing_slash(monkeypatch):
    module = _load_build_matrix_module()
    monkeypatch.setattr(module.platform, "system", lambda: "Windows")
    monkeypatch.setenv("SystemDrive", "D:\\")
    assert module._disk_usage_path() == "D:\\"


def test_disk_usage_path_non_windows_is_root(monkeypatch):
    module = _load_build_matrix_module()
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    assert module._disk_usage_path() == "/"


def test_get_disk_free_gb_uses_selected_path(monkeypatch):
    module = _load_build_matrix_module()
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")

    Usage = namedtuple("Usage", ["total", "used", "free"])
    calls = []

    def fake_disk_usage(path: str):
        calls.append(path)
        return Usage(total=0, used=0, free=10 * 1024**3)

    monkeypatch.setattr(module.shutil, "disk_usage", fake_disk_usage)
    assert module.get_disk_free_gb() == 10.0
    assert calls == ["/"]
