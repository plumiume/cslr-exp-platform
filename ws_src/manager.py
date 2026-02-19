#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workspace manager for Docker Compose operations.
"""

import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal

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
        self.templates_dir = self.project_root / "templates"
        self.template_path = self.templates_dir / "compose.yaml.jinja2"
        self.output_path = project_root / "_build" / "compose.yaml"
        self.test_template_path = (
            self.templates_dir / "cluster-test.compose.yaml.jinja2"
        )
        self.test_output_path = project_root / "_build" / "cluster-test.compose.yaml"

    def load_config(self) -> Config:
        """Load and validate configuration from config.yaml"""
        if not self.config_path.exists():
            console.print(f"[red]Error: {self.config_path} not found[/red]")
            raise typer.Exit(1)

        legacy_nodes_path = self.project_root / "nodes.yaml"
        if legacy_nodes_path.exists():
            console.print(
                "[red]Error: legacy nodes.yaml is no longer supported. "
                "Move nodes settings into config.yaml"
                " > nodes and remove nodes.yaml.[/red]"
            )
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
        if not (self.templates_dir.exists() and self.templates_dir.is_dir()):
            console.print(
                f"[red]Error: templates directory not found: {self.templates_dir}[/red]"
            )
            raise typer.Exit(1)
        env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
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

    def generate_cluster_test_file(
        self, target: Optional[Literal["cpu", "gpu"]] = None
    ) -> Config:
        """Generate cluster-test.compose.yaml from template"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Loading configuration...", total=None)
            config = self.load_config()

            if target is not None:
                config.cluster_test.target = target

            progress.add_task("Detecting host state...", total=None)
            config = self.detect_host_state(config)

            if config.cluster_test.target == "cpu":
                if not config.services.ray.cpu.enabled:
                    raise ValueError(
                        "cluster_test.target=cpu ですが"
                        " services.ray.cpu.enabled が false です"
                    )

            if config.cluster_test.target == "gpu":
                if not config.host.has_gpu:
                    raise ValueError(
                        "cluster_test.target=gpu ですが host.has_gpu が false です"
                    )
                if not config.services.ray.gpu.enabled:
                    raise ValueError(
                        "cluster_test.target=gpu ですが"
                        " services.ray.gpu.enabled が false です"
                    )

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

    def collect_cluster_test_logs(
        self,
        duration_minutes: int = 10,
        target: Optional[Literal["cpu", "gpu"]] = None,
        env: Optional[dict[str, str]] = None,
    ) -> Path:
        """Start cluster test, wait for duration, then collect all logs.

        Collects:
        - Docker compose logs from all services
        - /tmp/ray contents (persisted via volume mounts)
        - Container inspect data
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_base = self.project_root / "_build" / "logs"
        log_dir = log_base / f"collect_{timestamp}"
        log_dir.mkdir(parents=True, exist_ok=True)

        test_cwd = self.test_output_path.parent
        compose_cmd = ["docker", "compose", "-f", str(self.test_output_path)]

        # Ensure /tmp/ray mount dirs exist (to avoid root-owned dirs)
        for svc in [
            "ray-cpu",
            "ray-gpu",
            "test-client",
            "test-worker",
            "test-worker-cpu",
        ]:
            (log_base / svc / "tmp-ray").mkdir(parents=True, exist_ok=True)

        # 1. Start containers
        console.print(
            f"\n[bold cyan]== Log Collection: {duration_minutes}min ==[/bold cyan]\n"
        )
        console.print("[bold]Phase 1:[/bold] Starting cluster test containers...")

        up_cmd = compose_cmd + ["up", "-d"]
        console.print(f"[dim]{' '.join(up_cmd)}[/dim]")
        result = subprocess.run(up_cmd, cwd=test_cwd, env=env)
        if result.returncode != 0:
            console.print("[red]Failed to start containers[/red]")
            return log_dir

        start_time = time.time()

        # 2. Stream logs in background while waiting
        console.print(
            f"\n[bold]Phase 2:[/bold] Collecting logs for {duration_minutes} minutes..."
        )
        console.print("[dim]Press Ctrl+C to stop early[/dim]\n")

        docker_logs_file = log_dir / "docker-compose.log"
        log_proc = subprocess.Popen(
            compose_cmd + ["logs", "-f", "--timestamps"],
            cwd=test_cwd,
            env=env,
            stdout=open(docker_logs_file, "w"),
            stderr=subprocess.STDOUT,
        )

        try:
            remaining = duration_minutes * 60 - (time.time() - start_time)
            while remaining > 0:
                mins_left = int(remaining / 60)
                secs_left = int(remaining % 60)
                console.print(
                    f"\r  Remaining: {mins_left:02d}:{secs_left:02d}  ", end=""
                )
                wait_step = min(10, remaining)
                time.sleep(wait_step)
                remaining = duration_minutes * 60 - (time.time() - start_time)
        except KeyboardInterrupt:
            elapsed = time.time() - start_time
            console.print(
                f"\n[yellow]Interrupted after {elapsed:.0f}s. "
                "Proceeding to log collection...[/yellow]"
            )

        # Stop log streaming
        log_proc.terminate()
        try:
            log_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            log_proc.kill()

        console.print("\n\n[bold]Phase 3:[/bold] Collecting artifacts...")

        # 3. Capture container states
        ps_file = log_dir / "container-status.txt"
        subprocess.run(
            compose_cmd + ["ps", "-a"],
            cwd=test_cwd,
            env=env,
            stdout=open(ps_file, "w"),
            stderr=subprocess.STDOUT,
        )

        # 4. Collect per-service docker logs
        services_result = subprocess.run(
            compose_cmd + ["ps", "-a", "--format", "{{.Service}}"],
            cwd=test_cwd,
            env=env,
            capture_output=True,
            text=True,
        )
        services_list = [
            s.strip() for s in services_result.stdout.strip().split("\n") if s.strip()
        ]

        for svc in services_list:
            svc_log = log_dir / f"{svc}.log"
            subprocess.run(
                compose_cmd + ["logs", "--timestamps", svc],
                cwd=test_cwd,
                env=env,
                stdout=open(svc_log, "w"),
                stderr=subprocess.STDOUT,
            )

        # 5. Collect in-container artifacts (/tmp/ray, ray status, etc.)
        containers_result = subprocess.run(
            compose_cmd + ["ps", "-a", "--format", "{{.Service}}:{{.Name}}"],
            cwd=test_cwd,
            env=env,
            capture_output=True,
            text=True,
        )

        for line in containers_result.stdout.strip().split("\n"):
            if ":" not in line:
                continue
            svc, container = line.strip().split(":", 1)
            svc_dir = log_dir / svc
            svc_dir.mkdir(parents=True, exist_ok=True)

            is_ray_service = svc.startswith("ray-") or svc.startswith("test-ray-")

            if not is_ray_service:
                (svc_dir / "ray-status.txt").write_text(
                    "N/A: non-Ray service\n", encoding="utf-8"
                )
                (svc_dir / "tmp-ray-files.txt").write_text(
                    "N/A: non-Ray service\n", encoding="utf-8"
                )
                (svc_dir / "ray-session-logs.txt").write_text(
                    "N/A: non-Ray service\n", encoding="utf-8"
                )

                subprocess.run(
                    ["docker", "inspect", container],
                    stdout=open(svc_dir / "inspect.json", "w"),
                    stderr=subprocess.STDOUT,
                    timeout=10,
                )
                continue

            # ray status
            subprocess.run(
                ["docker", "exec", container, "ray", "status"],
                stdout=open(svc_dir / "ray-status.txt", "w"),
                stderr=subprocess.STDOUT,
                timeout=10,
            )

            # /tmp/ray directory listing
            subprocess.run(
                ["docker", "exec", container, "find", "/tmp/ray", "-type", "f"],
                stdout=open(svc_dir / "tmp-ray-files.txt", "w"),
                stderr=subprocess.STDOUT,
                timeout=10,
            )

            # /tmp/ray session latest logs
            subprocess.run(
                [
                    "docker",
                    "exec",
                    container,
                    "bash",
                    "-c",
                    (
                        "for f in $(find /tmp/ray/session_latest/logs -type f"
                        " -name '*.log' -o -name '*.err' -o -name '*.out'"
                        " 2>/dev/null | head -30); do"
                        ' echo "===== $f =====";'
                        ' tail -200 "$f";'
                        " echo; done"
                    ),
                ],
                stdout=open(svc_dir / "ray-session-logs.txt", "w"),
                stderr=subprocess.STDOUT,
                timeout=30,
            )

            # docker inspect
            subprocess.run(
                ["docker", "inspect", container],
                stdout=open(svc_dir / "inspect.json", "w"),
                stderr=subprocess.STDOUT,
                timeout=10,
            )

        # 6. Copy /tmp/ray volume-mounted data (logs only, skip sockets/symlinks)
        for svc in [
            "ray-cpu",
            "ray-gpu",
            "test-client",
            "test-worker",
            "test-worker-cpu",
        ]:
            src = log_base / svc / "tmp-ray"
            dst = log_dir / svc / "tmp-ray-volume"
            if src.exists() and any(src.iterdir()):
                import shutil
                import stat

                def _ignore_sockets(directory: str, contents: list[str]) -> set[str]:
                    """Ignore Unix sockets and broken symlinks"""
                    ignored: list[str] = []
                    for name in contents:
                        p = Path(directory) / name
                        try:
                            if p.is_symlink():
                                ignored.append(name)
                            elif p.exists() and stat.S_ISSOCK(p.stat().st_mode):
                                ignored.append(name)
                        except OSError:
                            ignored.append(name)
                    return set(ignored)

                try:
                    shutil.copytree(
                        src, dst, dirs_exist_ok=True, ignore=_ignore_sockets
                    )
                except shutil.Error:
                    pass  # partial copy is acceptable

        # Summary
        total_files = sum(1 for _ in log_dir.rglob("*") if _.is_file())
        total_size = sum(f.stat().st_size for f in log_dir.rglob("*") if f.is_file())

        console.print(
            Panel(
                f"[green]✓[/green] Logs collected to: {log_dir}\n\n"
                f"Files: {total_files}\n"
                f"Size: {total_size / 1024:.1f} KB\n\n"
                f"[bold]Contents:[/bold]\n"
                f"  docker-compose.log  - All service logs (timestamped)\n"
                f"  <service>.log       - Per-service docker logs\n"
                f"  <service>/ray-status.txt       - ray status output\n"
                f"  <service>/ray-session-logs.txt  - /tmp/ray/session_latest/logs\n"
                f"  <service>/tmp-ray-volume/       - /tmp/ray persisted data\n"
                f"  <service>/inspect.json          - docker inspect\n"
                f"  container-status.txt             - docker compose ps",
                title="[bold green]Log Collection Complete[/bold green]",
                border_style="green",
            )
        )

        return log_dir
