#!/usr/bin/env python3
"""Docker Build Matrix Runner

build-matrix.yaml の設定を読み込んで、複数のDocker イメージを並列またはシーケンシャルにビルドします。

使用例:
    # 全ビルド実行
    uv run python tools/build_matrix.py --all

    # 特定のCUDA/Pythonバージョンのみビルド
    uv run python tools/build_matrix.py --cuda 12.8.1 --python 3.13

    # 特定のターゲットのみビルド
    uv run python tools/build_matrix.py --target marimo-runtime

    # 最小構成のテストビルド
    uv run python tools/build_matrix.py --minimal

    # ドライラン（コマンドを表示するのみ）
    uv run python tools/build_matrix.py --all --dry-run
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

console = Console()


def load_matrix(file_path: Path) -> dict[str, Any]:
    """ビルドマトリックス設定を読み込む"""
    with open(file_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_command(
    cuda_version: str,
    python_version: str,
    cuda_tag: str,
    target: str,
    tag: str,
    image_prefix: str,
    platform: str,
) -> list[str]:
    """Dockerビルドコマンドを生成"""
    return [
        "docker",
        "build",
        "--target",
        target,
        "--build-arg",
        f"CUDA_VERSION={cuda_version}",
        "--build-arg",
        f"PYTHON_VERSION={python_version}",
        "--build-arg",
        f"CUDA_TAG={cuda_tag}",
        "-t",
        f"{image_prefix}:{tag}",
        "--platform",
        platform,
        ".",
    ]


def run_build(cmd: list[str], dry_run: bool = False) -> tuple[bool, float]:
    """ビルドコマンドを実行"""
    cmd_str = " ".join(cmd)
    console.print(f"\n[bold cyan]Executing:[/bold cyan] {cmd_str}")

    if dry_run:
        console.print("[yellow]DRY RUN - コマンドは実行されませんでした[/yellow]")
        return True, 0.0

    start_time = datetime.now()
    try:
        result = subprocess.run(
            cmd, check=True, capture_output=False, text=True  # noqa: E501
        )
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        console.print(f"[green]✓ ビルド成功[/green] (所要時間: {duration:.1f}秒)")
        return True, duration
    except subprocess.CalledProcessError as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        console.print(f"[red]✗ ビルド失敗[/red] (Exit code: {e.returncode})")
        return False, duration


def filter_matrix(
    matrix_data: dict[str, Any],
    cuda_filter: str | None = None,
    python_filter: str | None = None,
    target_filter: str | None = None,
) -> list[tuple[dict[str, Any], dict[str, str]]]:
    """マトリックスをフィルタリング"""
    filtered: list[tuple[dict[str, Any], dict[str, str]]] = []

    for config in matrix_data["matrix"]:
        if cuda_filter and config["cuda_version"] != cuda_filter:
            continue
        if python_filter and config["python_version"] != python_filter:
            continue

        for target in config["targets"]:
            if target_filter and target["name"] != target_filter:
                continue
            filtered.append((config, target))

    return filtered


def main() -> int:
    parser = argparse.ArgumentParser(description="Docker Build Matrix Runner")
    parser.add_argument("--all", action="store_true", help="全てのビルド構成を実行")
    parser.add_argument(
        "--minimal", action="store_true", help="最小構成のテストビルドを実行"
    )
    parser.add_argument("--cuda", help="特定のCUDAバージョンのみビルド (例: 12.8.1)")
    parser.add_argument("--python", help="特定のPythonバージョンのみビルド (例: 3.13)")
    parser.add_argument(
        "--target", help="特定のターゲットのみビルド (例: marimo-runtime)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="コマンドを表示するのみで実行しない"
    )
    parser.add_argument(
        "--matrix-file",
        type=Path,
        default=Path("build-matrix.yaml"),
        help="ビルドマトリックス設定ファイル",
    )

    args = parser.parse_args()

    # 設定ファイルを読み込み
    if not args.matrix_file.exists():
        console.print(
            f"[red]エラー: {args.matrix_file} が見つかりません[/red]", file=sys.stderr
        )
        return 1

    matrix_data = load_matrix(args.matrix_file)
    build_options = matrix_data["build_options"]

    builds: list[tuple[dict[str, Any], dict[str, str]]] = []

    # 最小構成ビルド
    if args.minimal:
        minimal = matrix_data["minimal_build"]
        cmd = build_command(
            cuda_version=minimal["cuda_version"],
            python_version=minimal["python_version"],
            cuda_tag=minimal["cuda_tag"],
            target=minimal["target"],
            tag=minimal["tag"],
            image_prefix=build_options["image_prefix"],
            platform=build_options["platform"],
        )
        success, duration = run_build(cmd, args.dry_run)
        return 0 if success else 1

    # フィルタリング
    if args.all or args.cuda or args.python or args.target:
        builds = filter_matrix(matrix_data, args.cuda, args.python, args.target)
    else:
        console.print("[yellow]いずれかのオプションを指定してください:[/yellow]")
        console.print("  --all : 全ビルドを実行")
        console.print("  --minimal : 最小構成のテストビルド")
        console.print("  --cuda, --python, --target : フィルタリングして実行")
        parser.print_help()
        return 1

    if not builds:
        console.print("[yellow]ビルド対象が見つかりませんでした[/yellow]")
        return 0

    # ビルド一覧を表示
    table = Table(title="ビルド対象一覧")
    table.add_column("No.", style="cyan")
    table.add_column("CUDA", style="green")
    table.add_column("Python", style="green")
    table.add_column("Target", style="yellow")
    table.add_column("Tag", style="magenta")

    for idx, (config, target) in enumerate(builds, 1):
        table.add_row(
            str(idx),
            config["cuda_version"],
            config["python_version"],
            target["name"],
            target["tag"],
        )

    console.print(table)
    console.print(f"\n[bold]合計 {len(builds)} 個のビルドを実行します[/bold]\n")

    # ビルド実行
    results: list[tuple[str, bool, float]] = []
    total_start = datetime.now()

    for idx, (config, target) in enumerate(builds, 1):
        console.print(
            f"\n[bold blue]===== ビルド {idx}/{len(builds)} =====[/bold blue]"
        )
        cmd = build_command(
            cuda_version=config["cuda_version"],
            python_version=config["python_version"],
            cuda_tag=config["cuda_tag"],
            target=target["name"],
            tag=target["tag"],
            image_prefix=build_options["image_prefix"],
            platform=build_options["platform"],
        )
        success, duration = run_build(cmd, args.dry_run)
        results.append((target["tag"], success, duration))

    total_end = datetime.now()
    total_duration = (total_end - total_start).total_seconds()

    # 結果サマリー
    console.print("\n[bold cyan]===== ビルド結果サマリー =====[/bold cyan]")
    result_table = Table()
    result_table.add_column("Tag", style="magenta")
    result_table.add_column("Status", style="bold")
    result_table.add_column("Duration", style="cyan")

    success_count = 0
    for tag, success, duration in results:
        status = "[green]✓ 成功[/green]" if success else "[red]✗ 失敗[/red]"
        result_table.add_row(tag, status, f"{duration:.1f}s")
        if success:
            success_count += 1

    console.print(result_table)
    console.print(f"\n[bold]成功: {success_count}/{len(results)}[/bold]")
    console.print(f"[bold]総所要時間: {total_duration:.1f}秒[/bold]\n")

    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
