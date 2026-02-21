#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 plumiume
# SPDX-License-Identifier: MIT
# License: MIT License (https://opensource.org/licenses/MIT)
# See LICENSE.txt for details.

"""
Configuration models for workspace management.
"""

import ipaddress
import re
from typing import Literal, Optional, Tuple, Type
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    PydanticBaseSettingsSource,
)

# ============================================================================
# Pydantic Models for Configuration
# ============================================================================


class HostConfig(BaseModel):
    """Host environment configuration"""

    has_gpu: bool = Field(default=False, description="GPU availability")
    gpu_type: Optional[str] = Field(default=None, description="GPU type (nvidia, amd)")
    hostname: str = Field(
        default="localhost",
        description="Hostname (future/reserved for host-name based access)",
    )
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

    @field_validator("subnet")
    @classmethod
    def validate_subnet(cls, v: str) -> str:
        """Validate CIDR notation"""
        try:
            ipaddress.ip_network(v)
        except ValueError as e:
            raise ValueError(f"Invalid subnet CIDR: {e}")
        return v


class BuildConfig(BaseModel):
    """Docker build configuration"""

    enabled: bool = Field(default=False, description="Enable building from Dockerfile")
    dockerfile: str = Field(default="Dockerfile", description="Path to Dockerfile")
    target: str = Field(default="", description="Build target stage")
    context: str = Field(default=".", description="Build context path")


class RayNodeConfig(BaseModel):
    """Base Ray node configuration"""

    enabled: bool = Field(default=True, description="Enable Ray service")
    image: Optional[str] = Field(default=None, description="Docker image")
    build: Optional[BuildConfig] = Field(
        default=None, description="Docker build configuration"
    )
    cpus: Optional[float] = Field(default=None, gt=0, description="CPU limit")
    memory: Optional[str] = Field(
        default=None, description="Memory limit (e.g., '8g', '512m')"
    )
    dashboard_port: int = Field(ge=1024, le=65535, description="Ray Dashboard port")
    client_port: int = Field(ge=1024, le=65535, description="Ray Client port")
    head_port: int = Field(ge=1024, le=65535, description="Head Ray process port")
    node_ip_address: Optional[str] = Field(
        default=None,
        description=(
            "Advertised node IP address for Ray internal communication "
            "(required in isolated/NAT environments)"
        ),
    )
    node_manager_port: Optional[int] = Field(
        default=None,
        ge=1024,
        le=65535,
        description="Fixed NodeManager port",
    )
    object_manager_port: Optional[int] = Field(
        default=None,
        ge=1024,
        le=65535,
        description="Fixed ObjectManager port",
    )
    min_worker_port: Optional[int] = Field(
        default=None,
        ge=1024,
        le=65535,
        description="Minimum worker process port",
    )
    max_worker_port: Optional[int] = Field(
        default=None,
        ge=1024,
        le=65535,
        description="Maximum worker process port",
    )
    address: Optional[str] = Field(
        default=None,
        description=(
            "Ray cluster address to connect to "
            "(future/reserved for test-time compatibility)"
        ),
    )

    @field_validator("memory")
    @classmethod
    def validate_memory(cls, v: Optional[str]) -> Optional[str]:
        """Validate memory format (e.g., '8g', '16G', '512m')"""
        if v is None:
            return v
        if not re.match(r"^\d+[gmGM]$", v):
            raise ValueError("Memory must be format like '8g' or '512m'")

        # Extract numeric value and check if it's greater than 0
        value = int(v[:-1])
        if value <= 0:
            raise ValueError("Memory value must be greater than 0")

        return v.lower()

    @model_validator(mode="after")
    def validate_worker_port_range(self) -> "RayNodeConfig":
        """Validate worker port range consistency"""
        min_port = self.min_worker_port
        max_port = self.max_worker_port

        if (min_port is None) != (max_port is None):
            raise ValueError(
                "Both min_worker_port and max_worker_port must be set together"
            )
        if min_port is not None and max_port is not None and min_port > max_port:
            raise ValueError(
                "min_worker_port must be less than or equal to max_worker_port"
            )

        return self


class RayCPUConfig(RayNodeConfig):
    """Ray CPU service configuration"""

    image: Optional[str] = Field(default=None, description="Docker image")
    dashboard_port: int = Field(
        default=8265, ge=1024, le=65535, description="Ray Dashboard port"
    )
    client_port: int = Field(
        default=10001, ge=1024, le=65535, description="Ray Client port"
    )
    head_port: int = Field(
        default=6379, ge=1024, le=65535, description="Head Ray process port"
    )


class RayGPUConfig(RayNodeConfig):
    """Ray GPU service configuration"""

    image: Optional[str] = Field(default=None, description="Docker image")
    dashboard_port: int = Field(
        default=8266, ge=1024, le=65535, description="Ray Dashboard port"
    )
    client_port: int = Field(
        default=10002, ge=1024, le=65535, description="Ray Client port"
    )
    head_port: int = Field(
        default=6380, ge=1024, le=65535, description="Head Ray process port"
    )


class RayConfig(BaseModel):
    """Ray service configuration"""

    image: Optional[str] = Field(default=None, description="Default Docker image")
    build: Optional[BuildConfig] = Field(
        default=None, description="Default Docker build configuration"
    )
    cpu: RayCPUConfig = Field(default_factory=RayCPUConfig)
    gpu: RayGPUConfig = Field(default_factory=RayGPUConfig)

    def model_post_init(self, __context: dict[str, object]):
        """Propagate shared settings to CPU/GPU configs if not set"""
        # Propagate image
        if self.image:
            if self.cpu.image is None:
                self.cpu.image = self.image
            if self.gpu.image is None:
                self.gpu.image = self.image

        # Set defaults if still None
        if self.cpu.image is None:
            self.cpu.image = "rayproject/ray:latest"
        if self.gpu.image is None:
            self.gpu.image = "rayproject/ray:latest-gpu"

        # Propagate build config
        if self.build:
            if self.cpu.build is None:
                self.cpu.build = self.build.model_copy()
            if self.gpu.build is None:
                self.gpu.build = self.build.model_copy()


class MLflowPostgresConfig(BaseModel):
    """MLflow PostgreSQL configuration"""

    enabled: bool = Field(default=True)
    image: str = Field(default="postgres:16-alpine")
    user: str = Field(default="mlflow")
    password: str = Field(
        default="CHANGE_ME_INVALID_PASSWORD",
        description=(
            "Database password "
            "(must be overridden via config/.env/environment variable)"
        ),
    )
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
    build: Optional[BuildConfig] = Field(
        default=None, description="Docker build configuration"
    )
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
    ray_data: str = Field(
        default="./data/ray",
        description="Future/reserved for Ray data mount options",
    )


class ClusterTestConfig(BaseModel):
    """Cluster test configuration"""

    target: Literal["cpu", "gpu"] = Field(
        default="cpu", description="Cluster test target node"
    )
    test_network_subnet: str = Field(
        default="172.30.0.0/24", description="Isolated test network subnet"
    )
    worker_node_manager_port: int = Field(
        default=30000,
        ge=1024,
        le=65535,
        description="Fixed NodeManager port for test worker",
    )
    worker_object_manager_port: int = Field(
        default=30001,
        ge=1024,
        le=65535,
        description="Fixed ObjectManager port for test worker",
    )
    worker_min_worker_port: int = Field(
        default=30010,
        ge=1024,
        le=65535,
        description="Minimum worker process port for test worker",
    )
    worker_max_worker_port: int = Field(
        default=30020,
        ge=1024,
        le=65535,
        description="Maximum worker process port for test worker",
    )
    worker_cpu_node_manager_port: int = Field(
        default=30100,
        ge=1024,
        le=65535,
        description="Fixed NodeManager port for CPU-head test worker",
    )
    worker_cpu_object_manager_port: int = Field(
        default=30101,
        ge=1024,
        le=65535,
        description="Fixed ObjectManager port for CPU-head test worker",
    )
    worker_cpu_min_worker_port: int = Field(
        default=30110,
        ge=1024,
        le=65535,
        description="Minimum worker process port for CPU-head test worker",
    )
    worker_cpu_max_worker_port: int = Field(
        default=30120,
        ge=1024,
        le=65535,
        description="Maximum worker process port for CPU-head test worker",
    )

    @field_validator("test_network_subnet")
    @classmethod
    def validate_test_network_subnet(cls, v: str) -> str:
        """Validate CIDR notation for test network"""
        try:
            ipaddress.ip_network(v)
        except ValueError as e:
            raise ValueError(f"Invalid test network subnet CIDR: {e}")
        return v

    @model_validator(mode="after")
    def validate_worker_port_range(self) -> "ClusterTestConfig":
        """Validate cluster test worker port range"""
        if self.worker_min_worker_port > self.worker_max_worker_port:
            raise ValueError(
                "cluster_test.worker_min_worker_port must be less than or equal to "
                "cluster_test.worker_max_worker_port"
            )
        if self.worker_cpu_min_worker_port > self.worker_cpu_max_worker_port:
            raise ValueError(
                "cluster_test.worker_cpu_min_worker_port must be less than or equal "
                "to cluster_test.worker_cpu_max_worker_port"
            )
        return self


class NodesHealthServiceConfig(BaseModel):
    """Health service settings for head election"""

    url: str = Field(default="http://health:8080")
    timeout: int = Field(default=1, ge=1)
    max_retries: int = Field(default=3, ge=0)
    retry_interval: float = Field(default=0.5, ge=0)


class NodesClusterConfig(BaseModel):
    """Cluster timing settings for head discovery"""

    discovery_timeout: int = Field(default=5, ge=1)
    wait_for_head: int = Field(default=30, ge=1)


class NodesConfig(BaseModel):
    """Node whitelist and head election settings"""

    head_whitelist: list[str] = Field(default_factory=lambda: ["ray-cpu", "ray-gpu"])
    head_address: Optional[str] = Field(default=None)
    health_service: NodesHealthServiceConfig = Field(
        default_factory=NodesHealthServiceConfig
    )
    cluster: NodesClusterConfig = Field(default_factory=NodesClusterConfig)

    @field_validator("head_whitelist")
    @classmethod
    def validate_head_whitelist(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("head_whitelist must contain at least one host")
        return v


class Config(BaseSettings):
    """Main configuration model"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CSLR_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    host: HostConfig = Field(default_factory=HostConfig)
    project: ProjectConfig
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    services: ServicesConfig = Field(default_factory=ServicesConfig)
    volumes: VolumesConfig = Field(default_factory=VolumesConfig)
    cluster_test: ClusterTestConfig = Field(default_factory=ClusterTestConfig)
    nodes: NodesConfig = Field(default_factory=NodesConfig)

    @model_validator(mode="after")
    def check_port_conflicts(self) -> "Config":
        """Check for port conflicts across services"""
        ports: list[tuple[str, int]] = []

        def add_optional_ray_ports(prefix: str, ray_cfg: RayNodeConfig):
            if ray_cfg.node_manager_port is not None:
                ports.append((f"{prefix}-node-manager", ray_cfg.node_manager_port))
            if ray_cfg.object_manager_port is not None:
                ports.append((f"{prefix}-object-manager", ray_cfg.object_manager_port))

        def check_range_overlap(
            label: str,
            start: int,
            end: int,
            reserved: list[tuple[str, int]],
        ):
            conflicts = [
                f"{name}:{port}" for name, port in reserved if start <= port <= end
            ]
            if conflicts:
                raise ValueError(
                    f"Port range conflicts detected for {label} ({start}-{end}): "
                    f"{', '.join(conflicts)}"
                )

        # Ray ports
        if self.services.ray.cpu.enabled:
            ports.extend(
                [
                    ("ray-cpu-dashboard", self.services.ray.cpu.dashboard_port),
                    ("ray-cpu-client", self.services.ray.cpu.client_port),
                    ("ray-cpu-head", self.services.ray.cpu.head_port),
                ]
            )
            add_optional_ray_ports("ray-cpu", self.services.ray.cpu)

        if self.services.ray.gpu.enabled:
            ports.extend(
                [
                    ("ray-gpu-dashboard", self.services.ray.gpu.dashboard_port),
                    ("ray-gpu-client", self.services.ray.gpu.client_port),
                    ("ray-gpu-head", self.services.ray.gpu.head_port),
                ]
            )
            add_optional_ray_ports("ray-gpu", self.services.ray.gpu)

        # Cluster test worker ports
        ports.extend(
            [
                (
                    "cluster-test-worker-node-manager",
                    self.cluster_test.worker_node_manager_port,
                ),
                (
                    "cluster-test-worker-object-manager",
                    self.cluster_test.worker_object_manager_port,
                ),
                (
                    "cluster-test-worker-cpu-node-manager",
                    self.cluster_test.worker_cpu_node_manager_port,
                ),
                (
                    "cluster-test-worker-cpu-object-manager",
                    self.cluster_test.worker_cpu_object_manager_port,
                ),
            ]
        )

        # Other service ports
        if self.services.mlflow.enabled:
            ports.append(("mlflow", self.services.mlflow.port))

        if self.services.redis.enabled:
            ports.append(("redis", self.services.redis.port))

        if self.services.marimo.enabled:
            ports.append(("marimo", self.services.marimo.port))

        if self.services.health.enabled:
            ports.append(("health", self.services.health.port))

        # Check for duplicates
        seen = set[int]()
        duplicates: list[str] = []
        for name, port in ports:
            if port in seen:
                duplicates.append(f"{name}:{port}")
            seen.add(port)

        if duplicates:
            raise ValueError(f"Port conflicts detected: {', '.join(duplicates)}")

        check_range_overlap(
            "cluster-test-worker-port-range",
            self.cluster_test.worker_min_worker_port,
            self.cluster_test.worker_max_worker_port,
            ports,
        )
        check_range_overlap(
            "cluster-test-worker-cpu-port-range",
            self.cluster_test.worker_cpu_min_worker_port,
            self.cluster_test.worker_cpu_max_worker_port,
            ports,
        )

        return self

    @model_validator(mode="after")
    def check_mlflow_password_security(self) -> "Config":
        """Reject insecure/default MLflow PostgreSQL password values."""
        if not (self.services.mlflow.enabled and self.services.mlflow.postgres.enabled):
            return self

        password = (self.services.mlflow.postgres.password or "").strip()
        insecure_values = {
            "",
            "mlflow",
            "CHANGE_ME_INVALID_PASSWORD",
            "changeme",
            "password",
        }
        if password in insecure_values:
            raise ValueError(
                "services.mlflow.postgres.password is insecure or unset. "
                "Set a non-default value in config.yaml or via "
                "CSLR_SERVICES__MLFLOW__POSTGRES__PASSWORD."
            )

        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """
        Customize settings sources priority.
        Priority: env vars > .env file > YAML (init) > file secrets > defaults
        """
        return env_settings, dotenv_settings, init_settings, file_secret_settings
