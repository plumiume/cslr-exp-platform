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

console = Console()
app = typer.Typer(
    name="ws",
    help="Workspace CLI for managing Docker Compose services",
    add_completion=False,
)


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
def ps():
    """Show running services"""
    project_root = Path(__file__).parent.parent.resolve()
    manager = WorkspaceManager(project_root)
    sys.exit(manager.run_docker_compose(["ps"]))


@app.command()
def status():
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

        if result.returncode != 0:
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

        if not running_services:
            console.print("[yellow]No services are currently running[/yellow]")
            console.print("Start services with: ws up -d")
            return

        # Determine host address
        host_ip = config.host.ip_address or "localhost"

        # Build service URLs
        table = Table(
            title="Running Services - URLs",
            show_header=True,
            header_style="bold magenta",
        )
        table.add_column("Service", style="cyan", no_wrap=True)
        table.add_column("Type", style="green")
        table.add_column("URL", style="yellow")

        # Health service
        if "health" in running_services and config.services.health.enabled:
            table.add_row(
                "health",
                "Health Check",
                f"http://{host_ip}:{config.services.health.port}",
            )

        # Ray CPU service
        if "ray-cpu" in running_services and config.services.ray.cpu.enabled:
            table.add_row(
                "ray-cpu",
                "Dashboard",
                f"http://{host_ip}:{config.services.ray.cpu.dashboard_port}",
            )
            table.add_row(
                "ray-cpu",
                "Client",
                f"ray://{host_ip}:{config.services.ray.cpu.client_port}",
            )

        # Ray GPU service
        if "ray-gpu" in running_services and config.services.ray.gpu.enabled:
            table.add_row(
                "ray-gpu",
                "Dashboard",
                f"http://{host_ip}:{config.services.ray.gpu.dashboard_port}",
            )
            table.add_row(
                "ray-gpu",
                "Client",
                f"ray://{host_ip}:{config.services.ray.gpu.client_port}",
            )

        # MLflow service
        if "mlflow" in running_services and config.services.mlflow.enabled:
            table.add_row(
                "mlflow", "UI", f"http://{host_ip}:{config.services.mlflow.port}"
            )

        # Redis service
        if "redis" in running_services and config.services.redis.enabled:
            table.add_row(
                "redis", "Server", f"redis://{host_ip}:{config.services.redis.port}"
            )

        # Marimo service
        if "marimo" in running_services and config.services.marimo.enabled:
            table.add_row(
                "marimo", "Notebook", f"http://{host_ip}:{config.services.marimo.port}"
            )

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
