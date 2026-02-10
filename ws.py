#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workspace CLI tool for managing Docker Compose with Jinja2 templates.
"""

import socket
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
import yaml
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Rich Console for beautiful output
console = Console()
app = typer.Typer(
    name="ws",
    help="Workspace CLI for managing Docker Compose services",
    add_completion=False,
    # Enable prefix matching for subcommands (e.g., 'ws u' → 'up', 'ws d' → 'down')
    # This is True by default but made explicit here
)


# ============================================================================
# Pydantic Models for Configuration
# ============================================================================


class HostConfig(BaseModel):
    """Host environment configuration"""

    has_gpu: bool = Field(default=False, description="GPU availability")
    gpu_type: Optional[str] = Field(default=None, description="GPU type (nvidia, amd)")
    hostname: str = Field(default="localhost", description="Hostname")
    ip_address: Optional[str] = Field(
        default=None, description="Host IP address (non-loopback)"
    )


class ProjectConfig(BaseModel):
    """Project configuration"""

    name: str = Field(description="Project name")
    version: str = Field(description="Project version")


class NetworkConfig(BaseModel):
    """Network configuration"""

    subnet: str = Field(default="172.28.0.0/16", description="Docker network subnet")


class RayCPUConfig(BaseModel):
    """Ray CPU service configuration"""

    enabled: bool = Field(default=True, description="Enable Ray CPU service")
    image: str = Field(default="rayproject/ray:latest", description="Docker image")
    cpus: int = Field(default=4, description="CPU limit")
    memory: str = Field(default="8g", description="Memory limit")
    dashboard_port: int = Field(default=8265, description="Ray Dashboard port")
    client_port: int = Field(default=10001, description="Ray Client port")
    head_port: int = Field(default=6379, description="Head Ray process port")
    address: Optional[str] = Field(
        default=None,
        description="Ray cluster address to connect to (None = start as head node)",
    )


class RayGPUConfig(BaseModel):
    """Ray GPU service configuration"""

    enabled: bool = Field(default=True, description="Enable Ray GPU service")
    image: str = Field(default="rayproject/ray:latest-gpu", description="Docker image")
    runtime: str = Field(default="nvidia", description="Container runtime")
    cpus: int = Field(default=4, description="CPU limit")
    memory: str = Field(default="16g", description="Memory limit")
    dashboard_port: int = Field(default=8266, description="Ray Dashboard port")
    client_port: int = Field(default=10002, description="Ray Client port")
    head_port: int = Field(default=6380, description="Head Ray process port")
    address: Optional[str] = Field(
        default=None,
        description="Ray cluster address to connect to (None = start as head node)",
    )


class RayConfig(BaseModel):
    """Ray service configuration"""

    cpu: RayCPUConfig = Field(default_factory=RayCPUConfig)
    gpu: RayGPUConfig = Field(default_factory=RayGPUConfig)


class MLflowPostgresConfig(BaseModel):
    """MLflow PostgreSQL configuration"""

    enabled: bool = Field(default=True)
    image: str = Field(default="postgres:16-alpine")
    user: str = Field(default="mlflow")
    password: str = Field(default="mlflow")
    database: str = Field(default="mlflow")


class MLflowConfig(BaseModel):
    """MLflow service configuration"""

    enabled: bool = Field(default=True)
    image: str = Field(default="ghcr.io/mlflow/mlflow:latest")
    port: int = Field(default=5000)
    postgres: MLflowPostgresConfig = Field(default_factory=MLflowPostgresConfig)


class RedisConfig(BaseModel):
    """Redis service configuration"""

    enabled: bool = Field(default=True)
    image: str = Field(default="redis:7-alpine")
    port: int = Field(default=6381)


class MarimoConfig(BaseModel):
    """Marimo service configuration"""

    enabled: bool = Field(default=True)
    image: str = Field(default="marimo-labs/marimo:latest")
    port: int = Field(default=8080)


class HealthConfig(BaseModel):
    """Health check service configuration"""

    enabled: bool = Field(default=True)
    port: int = Field(default=8888)


class ServicesConfig(BaseModel):
    """Services configuration"""

    ray: RayConfig = Field(default_factory=RayConfig)
    mlflow: MLflowConfig = Field(default_factory=MLflowConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    marimo: MarimoConfig = Field(default_factory=MarimoConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)


class VolumesConfig(BaseModel):
    """Volumes configuration"""

    mlflow_data: str = Field(default="./data/mlflow")
    postgres_data: str = Field(default="./data/postgres")
    ray_data: str = Field(default="./data/ray")


class Config(BaseModel):
    """Main configuration model"""

    host: HostConfig = Field(default_factory=HostConfig)
    project: ProjectConfig
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    services: ServicesConfig = Field(default_factory=ServicesConfig)
    volumes: VolumesConfig = Field(default_factory=VolumesConfig)


# ============================================================================
# Core Workspace Manager
# ============================================================================


class WorkspaceManager:
    """Manages workspace operations"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config_path = project_root / "config.yaml"
        self.template_path = project_root / "template" / "compose.yaml.jinja2"
        self.output_path = project_root / "_build" / "compose.yaml"
        self.test_template_path = (
            project_root / "template" / "cluster-test.compose.yaml.jinja2"
        )
        self.test_output_path = project_root / "_build" / "cluster-test.compose.yaml"

    def load_config(self) -> Config:
        """Load and validate configuration from config.yaml"""
        if not self.config_path.exists():
            console.print(f"[red]Error: {self.config_path} not found[/red]")
            raise typer.Exit(1)

        with open(self.config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return Config(**data)

    def get_host_ip_address(self) -> Optional[str]:
        """Get the first non-loopback network interface IP address"""
        try:
            # Create a socket connection to a remote address to determine the local IP
            # This doesn't actually send data,
            # just determines which interface would be used
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                # Use Google's DNS server as a target (doesn't need to be reachable)
                s.connect(("8.8.8.8", 80))
                ip_address = s.getsockname()[0]
                # Verify it's not a loopback address
                if not ip_address.startswith("127."):
                    return ip_address
        except Exception:
            pass

        return None

    def detect_host_state(self, config: Config) -> Config:
        """Detect host state (GPU availability, etc.)

        Only overrides config.yaml settings if they are not explicitly set.
        Priority: config.yaml > auto-detection
        """
        # Detect IP address if not explicitly configured
        if config.host.ip_address is None:
            ip_address = self.get_host_ip_address()
            if ip_address:
                config.host.ip_address = ip_address

        # Only auto-detect GPU if not explicitly configured
        if config.host.gpu_type is None:
            has_gpu = False
            gpu_type = None

            try:
                result = subprocess.run(
                    ["nvidia-smi"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    has_gpu = True
                    gpu_type = "nvidia"
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            config.host.has_gpu = has_gpu
            if gpu_type:
                config.host.gpu_type = gpu_type

        return config

    def render_template(self, config: Config, template_name: str | None = None) -> str:
        """Render Jinja2 template with config"""
        env = Environment(
            loader=FileSystemLoader(str(self.project_root / "template")),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        if template_name is None:
            template_name = self.template_path.name
        template = env.get_template(template_name)
        return template.render(**config.model_dump())

    def generate_compose_file(self) -> Config:
        """Generate compose.yaml from template"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Loading configuration...", total=None)
            config = self.load_config()

            progress.add_task("Detecting host state...", total=None)
            config = self.detect_host_state(config)

            progress.add_task("Rendering template...", total=None)
            output = self.render_template(config)

            # Ensure output directory exists
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

            progress.add_task(f"Writing to {self.output_path}...", total=None)
            with open(self.output_path, "w", encoding="utf-8") as f:
                f.write(output)

        # Show summary
        gpu_status = "✓" if config.host.has_gpu else "✗"
        gpu_info = f"{config.host.gpu_type}" if config.host.has_gpu else "None"

        console.print(
            Panel(
                f"[green]✓[/green] compose.yaml generated successfully\n\n"
                f"GPU: {gpu_status} {gpu_info}\n"
                f"Project: {config.project.name} v{config.project.version}",
                title="[bold green]Success[/bold green]",
                border_style="green",
            )
        )

        return config

    def generate_cluster_test_file(self) -> Config:
        """Generate cluster-test.compose.yaml from template"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Loading configuration...", total=None)
            config = self.load_config()

            progress.add_task("Detecting host state...", total=None)
            config = self.detect_host_state(config)

            progress.add_task("Rendering cluster test template...", total=None)
            output = self.render_template(config, self.test_template_path.name)

            # Ensure output directory exists
            self.test_output_path.parent.mkdir(parents=True, exist_ok=True)

            progress.add_task(f"Writing to {self.test_output_path}...", total=None)
            with open(self.test_output_path, "w", encoding="utf-8") as f:
                f.write(output)

        console.print(
            Panel(
                f"[green]✓[/green] cluster-test.compose.yaml generated successfully\n\n"
                f"Host IP: {config.host.ip_address}\n"
                f"Project: {config.project.name} v{config.project.version}",
                title="[bold green]Test Environment Ready[/bold green]",
                border_style="green",
            )
        )

        return config

    def run_docker_compose(self, args: list[str]) -> int:
        """Run docker compose command"""
        self.generate_compose_file()

        cmd = ["docker", "compose", "-f", str(self.output_path)] + args
        console.print(f"\n[dim]Running: {' '.join(cmd)}[/dim]\n")

        try:
            result = subprocess.run(cmd, cwd=self.output_path.parent)
            return result.returncode
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")
            return 130


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

    project_root = Path(__file__).parent.resolve()
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

    project_root = Path(__file__).parent.resolve()
    manager = WorkspaceManager(project_root)
    sys.exit(manager.run_docker_compose(compose_args))


@app.command()
def generate():
    """Generate compose.yaml from template"""
    project_root = Path(__file__).parent.resolve()
    manager = WorkspaceManager(project_root)
    try:
        manager.generate_compose_file()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def ps():
    """Show running services"""
    project_root = Path(__file__).parent.resolve()
    manager = WorkspaceManager(project_root)
    sys.exit(manager.run_docker_compose(["ps"]))


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

    project_root = Path(__file__).parent.resolve()
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
    project_root = Path(__file__).parent.resolve()
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


if __name__ == "__main__":
    main()
