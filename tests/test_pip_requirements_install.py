"""
ray.sh の pip-requirements インストールブロックの動作検証。

pip install は stub に差し替え、シェルロジック（ファイル列挙・ログ・スキップ）のみを
ネットワーク依存・環境汚染なしに検証する。
"""

import os
import stat
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PIP_REQ_FIXTURE_DIR = REPO_ROOT / "tests" / "pip-requirements"

# ray.sh の pip-requirements インストールブロック (PIP_REQ_DIR・PYTHON_EXEC は外部から注入)
_RAY_PIP_BLOCK = """\
set -e
if [ -f "$PIP_REQ_DIR" ]; then
    echo "Checking pip requirements in $PIP_REQ_DIR..."
    echo "  Installing from: $PIP_REQ_DIR"
    "$PYTHON_EXEC" -m pip install -r "$PIP_REQ_DIR"
    echo "✓ pip requirements installation done."
elif [ -d "$PIP_REQ_DIR" ]; then
    echo "Checking pip requirements in $PIP_REQ_DIR..."
    req_files=()
    while IFS= read -r req_file; do
        req_files+=("$req_file")
    done < <(find "$PIP_REQ_DIR" -type f -name "*.txt" | sort)
    if [ "${#req_files[@]}" -eq 0 ]; then
        echo "  No pip requirement files found, skipping."
    else
        for req_file in "${req_files[@]}"; do
            echo "  Installing from: $req_file"
            "$PYTHON_EXEC" -m pip install -r "$req_file"
        done
        echo "✓ pip requirements installation done."
    fi
else
    echo "  /pip-requirements not found, skipping."
fi
"""


def _make_python_stub(tmp_dir: Path) -> Path:
    """
    ``python -m pip install -r <file>`` を受け取り、引数を stdout に出力して
    exit 0 するスタブスクリプトを作成する。
    実際の pip install は行わず、シェルロジックのみを検証できる。
    """
    stub = tmp_dir / "python"
    stub.write_text(
        "#!/bin/bash\n"
        "# stub: echo args and succeed\n"
        'echo "STUB_CALLED: $*"\n'
        "exit 0\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _run_block(pip_req_dir: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        stub = _make_python_stub(tmp_dir)
        env = {
            **os.environ,
            "PIP_REQ_DIR": pip_req_dir,
            "PYTHON_EXEC": str(stub),
        }
        return subprocess.run(
            ["bash", "-c", _RAY_PIP_BLOCK],
            env=env,
            capture_output=True,
            text=True,
        )


def test_directory_mount_detects_nested_txt_files():
    """ディレクトリマウント時に *.txt ファイルが検出され pip install が呼ばれる。"""
    result = _run_block(str(PIP_REQ_FIXTURE_DIR))

    assert result.returncode == 0, f"exit={result.returncode}\n{result.stderr}"

    output = result.stdout
    # ファイルパスがログに出ること
    assert "child/requirements.txt" in output, f"expected file log in:\n{output}"
    # スタブが呼ばれ -r で requirements.txt が渡されていること
    assert "-m pip install -r" in output, output
    # インストール完了メッセージ
    assert "✓ pip requirements installation done." in output, output


def test_directory_mount_non_txt_files_are_ignored(tmp_path: Path):
    """*.txt 以外のファイルはインストール対象にならない。"""
    (tmp_path / "extra.json").write_text("{}")
    (tmp_path / "notes.md").write_text("# notes")

    result = _run_block(str(tmp_path))

    assert result.returncode == 0, f"exit={result.returncode}\n{result.stderr}"
    assert "No pip requirement files found, skipping." in result.stdout


def test_file_mount_installs_directly(tmp_path: Path):
    """/pip-requirements がファイルの場合はそのまま pip install -r される。"""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("numpy\n")

    result = _run_block(str(req_file))

    assert result.returncode == 0, f"exit={result.returncode}\n{result.stderr}"
    assert f"Installing from: {req_file}" in result.stdout
    assert "✓ pip requirements installation done." in result.stdout


def test_missing_pip_requirements_does_not_fail():
    """/pip-requirements が存在しない場合にエラーなくスキップされる。"""
    result = _run_block("/nonexistent-pip-requirements")

    assert result.returncode == 0, f"exit={result.returncode}\n{result.stderr}"
    assert "skipping" in result.stdout, result.stdout
