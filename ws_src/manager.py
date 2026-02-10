#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workspace manager for Docker Compose operations.
"""

import socket
import subprocess
from pathlib import Path
from typing import Optional

import typer
import yaml
from jinja2 import Environment, FileSystemLoader
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .models import Config

# Rich Console for beautiful output
console = Console()


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
