#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI commands for workspace management.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from .manager import WorkspaceManager
from .schema_utils import generate_config_schema

console = Console()
app = typer.Typer(
    name="ws",
    help="Workspace CLI for managing Docker Compose services",
    add_completion=False,
)
schema_app = typer.Typer(help="Schema utilities")
app.add_typer(schema_app, name="schema")


# ============================================================================
# CLI Commands
# ============================================================================


@app.command()
def up(
    detach: Annotated[
        bool, typer.Option("-d", "--detach", help="Detached mode")
    ] = False,
    build: Annotated[
        bool, typer.Option("--build", help="Build images before starting")
    ] = False,
    remove_orphans: Annotated[
        bool, typer.Option("--remove-orphans", help="Remove orphan containers")
    ] = False,
    services: Annotated[
        Optional[list[str]], typer.Argument(help="Services to start")
    ] = None,
):
    """Start services with docker compose up"""
    compose_args = ["up"]

    if detach:
        compose_args.append("-d")
    if build:
        compose_args.append("--build")
    if remove_orphans:
        compose_args.append("--remove-orphans")

    if services:
        compose_args.extend(services)

    project_root = Path(__file__).parent.parent.resolve()
    manager = WorkspaceManager(project_root)
    sys.exit(manager.run_docker_compose(compose_args))


@app.command()
def down(
    volumes: Annotated[
        bool, typer.Option("-v", "--volumes", help="Remove volumes")
    ] = False,
    remove_orphans: Annotated[
        bool, typer.Option("--remove-orphans", help="Remove orphan containers")
    ] = False,
):
    """Stop and remove services"""
    compose_args = ["down"]

    if volumes:
        compose_args.append("-v")
    if remove_orphans:
        compose_args.append("--remove-orphans")

    project_root = Path(__file__).parent.parent.resolve()
    manager = WorkspaceManager(project_root)
    sys.exit(manager.run_docker_compose(compose_args))


@app.command()
def generate():
    """Generate compose.yaml from template"""
    project_root = Path(__file__).parent.parent.resolve()
    manager = WorkspaceManager(project_root)
    try:
        manager.generate_compose_file()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def init(
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite config.yaml if it already exists",
        ),
    ] = False,
):
    """Initialize config.yaml and generate editor schema"""
    project_root = Path(__file__).parent.parent.resolve()
    config_example_path = project_root / "config.example.yaml"
    config_path = project_root / "config.yaml"

    if not config_example_path.exists():
        console.print(f"[red]Error: {config_example_path} not found[/red]")
        raise typer.Exit(1)

    if not config_path.exists() or force:
        config_path.write_text(config_example_path.read_text(encoding="utf-8"))
        console.print(f"[green]✓[/green] Created {config_path}")
    else:
        console.print(
            "[yellow]config.yaml already exists. Use --force to overwrite.[/yellow]"
        )

    schema_path = generate_config_schema(project_root)
    console.print(f"[green]✓[/green] Generated {schema_path}")


@schema_app.command("generate")
def schema_generate():
    """Generate editor schema from Pydantic models"""
    project_root = Path(__file__).parent.parent.resolve()
    try:
        schema_path = generate_config_schema(project_root)
        console.print(f"[green]✓[/green] Generated {schema_path}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def ps():
    """Show running services"""
    project_root = Path(__file__).parent.parent.resolve()
    manager = WorkspaceManager(project_root)
    sys.exit(manager.run_docker_compose(["ps"]))


@app.command()
def status(
    all: Annotated[
        bool,
        typer.Option(
            "-a", "--all", help="Show all enabled services including stopped ones"
        ),
    ] = False,
):
    """Show running services with dashboard and endpoint URLs"""
    project_root = Path(__file__).parent.parent.resolve()
    manager = WorkspaceManager(project_root)

    try:
        # Load configuration
        config = manager.load_config()
        config = manager.detect_host_state(config)

        # Get running services
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(manager.output_path),
                "ps",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            cwd=manager.output_path.parent,
        )

        if result.returncode != 0 and not all:
            console.print(
                "[yellow]No services are running or compose file not found[/yellow]"
            )
            console.print("Run 'ws generate' first to create the compose file")
            return

        # Parse running services
        running_services = set[str]()
        if result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                if line:
                    service_info = json.loads(line)
                    if service_info.get("State") == "running":
                        running_services.add(service_info.get("Service", ""))

        if not running_services and not all:
            console.print("[yellow]No services are currently running[/yellow]")
            console.print("Start services with: ws up -d")
            return

        # Determine host address
        host_ip = config.host.ip_address or "localhost"

        # Build service URLs
        title = "All Services - URLs" if all else "Running Services - URLs"
        table = Table(
            title=title,
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Service", style="cyan", no_wrap=True)
        if all:
            table.add_column("Status", style="magenta")
        table.add_column("Type", style="green")
        table.add_column("URL", style="yellow")

        # Health service
        if config.services.health.enabled:
            is_running = "health" in running_services
            if all or is_running:
                row_data = ["health"]
                if all:
                    row_data.append(
                        "[green]Running[/green]" if is_running else "[dim]Stopped[/dim]"
                    )
                row_data.extend(
                    [
                        "🏥 Health Check",
                        f"http://{host_ip}:{config.services.health.port}",
                    ]
                )
                table.add_row(*row_data)

        # Ray CPU service
        if config.services.ray.cpu.enabled:
            is_running = "ray-cpu" in running_services
            if all or is_running:
                # Dashboard
                row_data = ["ray-cpu"]
                if all:
                    row_data.append(
                        "[green]Running[/green]" if is_running else "[dim]Stopped[/dim]"
                    )
                row_data.extend(
                    [
                        "📊 Dashboard",
                        f"http://{host_ip}:{config.services.ray.cpu.dashboard_port}",
                    ]
                )
                table.add_row(*row_data)
                # Client
                row_data = ["ray-cpu"]
                if all:
                    row_data.append(
                        "[green]Running[/green]" if is_running else "[dim]Stopped[/dim]"
                    )
                row_data.extend(
                    [
                        "🔌 Client",
                        f"ray://{host_ip}:{config.services.ray.cpu.client_port}",
                    ]
                )
                table.add_row(*row_data)

        # Ray GPU service
        if config.services.ray.gpu.enabled:
            is_running = "ray-gpu" in running_services
            if all or is_running:
                # Dashboard
                row_data = ["ray-gpu"]
                if all:
                    row_data.append(
                        "[green]Running[/green]" if is_running else "[dim]Stopped[/dim]"
                    )
                row_data.extend(
                    [
                        "📊 Dashboard",
                        f"http://{host_ip}:{config.services.ray.gpu.dashboard_port}",
                    ]
                )
                table.add_row(*row_data)
                # Client
                row_data = ["ray-gpu"]
                if all:
                    row_data.append(
                        "[green]Running[/green]" if is_running else "[dim]Stopped[/dim]"
                    )
                row_data.extend(
                    [
                        "🔌 Client",
                        f"ray://{host_ip}:{config.services.ray.gpu.client_port}",
                    ]
                )
                table.add_row(*row_data)

        # MLflow service
        if config.services.mlflow.enabled:
            is_running = "mlflow" in running_services
            if all or is_running:
                row_data = ["mlflow"]
                if all:
                    row_data.append(
                        "[green]Running[/green]" if is_running else "[dim]Stopped[/dim]"
                    )
                row_data.extend(
                    ["🖥️ UI", f"http://{host_ip}:{config.services.mlflow.port}"]
                )
                table.add_row(*row_data)

        # Redis service
        if config.services.redis.enabled:
            is_running = "ray-redis" in running_services
            if all or is_running:
                row_data = ["ray-redis"]
                if all:
                    row_data.append(
                        "[green]Running[/green]" if is_running else "[dim]Stopped[/dim]"
                    )
                row_data.extend(
                    ["🗄️ Server", f"redis://{host_ip}:{config.services.redis.port}"]
                )
                table.add_row(*row_data)

        # Marimo service
        if config.services.marimo.enabled:
            is_running = "marimo" in running_services
            if all or is_running:
                row_data = ["marimo"]
                if all:
                    row_data.append(
                        "[green]Running[/green]" if is_running else "[dim]Stopped[/dim]"
                    )
                row_data.extend(
                    ["📓 Notebook", f"http://{host_ip}:{config.services.marimo.port}"]
                )
                table.add_row(*row_data)

        console.print()
        console.print(table)
        console.print()
        console.print(f"[dim]Host IP: {host_ip}[/dim]")
        console.print(
            f"[dim]Running services: {', '.join(sorted(running_services))}[/dim]"
        )

    except FileNotFoundError:
        console.print("[red]Error: docker or docker compose not found[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def logs(
    follow: Annotated[
        bool, typer.Option("-f", "--follow", help="Follow log output")
    ] = False,
    tail: Annotated[
        Optional[int], typer.Option("--tail", help="Number of lines to show")
    ] = None,
    services: Annotated[
        Optional[list[str]], typer.Argument(help="Services to show logs for")
    ] = None,
):
    """Show logs"""
    compose_args = ["logs"]

    if follow:
        compose_args.append("-f")
    if tail:
        compose_args.extend(["--tail", str(tail)])

    if services:
        compose_args.extend(services)

    project_root = Path(__file__).parent.parent.resolve()
    manager = WorkspaceManager(project_root)
    sys.exit(manager.run_docker_compose(compose_args))


@app.command()
def test(
    up: Annotated[bool, typer.Option("--up", help="Start test containers")] = False,
    down: Annotated[bool, typer.Option("--down", help="Stop test containers")] = False,
    logs: Annotated[
        bool, typer.Option("--logs", help="Show test container logs")
    ] = False,
    head: Annotated[
        Optional[str],
        typer.Option(
            "--head", help="Explicit head address (host:port) for worker nodes"
        ),
    ] = None,
):
    """Run cluster connectivity tests with isolated test containers"""
    project_root = Path(__file__).parent.parent.resolve()
    manager = WorkspaceManager(project_root)

    try:
        # Generate test compose file
        manager.generate_cluster_test_file()

        # Build environment with optional HEAD_ADDRESS
        env = None
        if head:
            import os

            env = os.environ.copy()
            env["HEAD_ADDRESS"] = head

        test_cwd = manager.test_output_path.parent

        if down:
            cmd = [
                "docker",
                "compose",
                "-f",
                str(manager.test_output_path),
                "down",
                "-v",
            ]
            console.print(f"\n[dim]Running: {' '.join(cmd)}[/dim]\n")
            result = subprocess.run(cmd, cwd=test_cwd, env=env)
            sys.exit(result.returncode)

        if up:
            cmd = ["docker", "compose", "-f", str(manager.test_output_path), "up", "-d"]
            console.print(f"\n[dim]Running: {' '.join(cmd)}[/dim]\n")
            result = subprocess.run(cmd, cwd=test_cwd, env=env)

            if result.returncode == 0:
                console.print("\n[green]✓[/green] Test containers started\n")
                console.print("View logs:")
                console.print("  ws test --logs\n")
                console.print("Stop test containers:")
                console.print("  ws test --down")

            sys.exit(result.returncode)

        if logs:
            cmd = [
                "docker",
                "compose",
                "-f",
                str(manager.test_output_path),
                "logs",
                "-f",
            ]
            console.print(f"\n[dim]Running: {' '.join(cmd)}[/dim]\n")
            result = subprocess.run(cmd, cwd=test_cwd, env=env)
            sys.exit(result.returncode)

        # Default: generate only
        console.print(
            "\n[yellow]Test compose file generated. Use options to control test containers:[/yellow]"  # noqa: E501
        )
        console.print("  --up      Start test containers")
        console.print("  --down    Stop test containers")
        console.print("  --logs    Show test container logs")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


def main():
    """Main entry point"""
    app()
