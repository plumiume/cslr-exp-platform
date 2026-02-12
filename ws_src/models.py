#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration models for workspace management.
"""

from typing import Optional
from pydantic import BaseModel, Field


# ============================================================================
# Pydantic Models for Configuration
# ============================================================================


class HostConfig(BaseModel):
    """Host environment configuration"""

    has_gpu: bool = Field(default=False, description="GPU availability")
    gpu_type: Optional[str] = Field(
        default=None, description="GPU type (nvidia, amd)"
    )
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

    subnet: str = Field(
        default="172.28.0.0/16", description="Docker network subnet"
    )


class BuildConfig(BaseModel):
    """Docker build configuration"""

    enabled: bool = Field(
        default=False, description="Enable building from Dockerfile"
    )
    dockerfile: str = Field(
        default="Dockerfile", description="Path to Dockerfile"
    )
    target: str = Field(default="", description="Build target stage")
    context: str = Field(default=".", description="Build context path")


class RayCPUConfig(BaseModel):
    """Ray CPU service configuration"""

    enabled: bool = Field(default=True, description="Enable Ray CPU service")
    image: Optional[str] = Field(
        default=None, description="Docker image"
    )
    build: Optional[BuildConfig] = Field(
        default=None, description="Docker build configuration"
    )
    cpus: Optional[float] = Field(default=None, description="CPU limit")
    memory: Optional[str] = Field(default=None, description="Memory limit")
    dashboard_port: int = Field(
        default=8265, description="Ray Dashboard port"
    )
    client_port: int = Field(default=10001, description="Ray Client port")
    head_port: int = Field(
        default=6379, description="Head Ray process port"
    )
    address: Optional[str] = Field(
        default=None,
        description=(
            "Ray cluster address to connect to (None = start as head node)"
        ),
    )


class RayGPUConfig(BaseModel):
    """Ray GPU service configuration"""

    enabled: bool = Field(default=True, description="Enable Ray GPU service")
    image: Optional[str] = Field(
        default=None, description="Docker image"
    )
    build: Optional[BuildConfig] = Field(
        default=None, description="Docker build configuration"
    )
    runtime: str = Field(default="nvidia", description="Container runtime")
    cpus: Optional[float] = Field(default=None, description="CPU limit")
    memory: Optional[str] = Field(default=None, description="Memory limit")
    dashboard_port: int = Field(
        default=8266, description="Ray Dashboard port"
    )
    client_port: int = Field(default=10002, description="Ray Client port")
    head_port: int = Field(
        default=6380, description="Head Ray process port"
    )
    address: Optional[str] = Field(
        default=None,
        description=(
            "Ray cluster address to connect to (None = start as head node)"
        ),
    )


class RayConfig(BaseModel):
    """Ray service configuration"""

    image: Optional[str] = Field(
        default=None, description="Default Docker image"
    )
    build: Optional[BuildConfig] = Field(
        default=None, description="Default Docker build configuration"
    )
    cpu: RayCPUConfig = Field(default_factory=RayCPUConfig)
    gpu: RayGPUConfig = Field(default_factory=RayGPUConfig)

    def model_post_init(self, __context):
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
    password: str = Field(default="mlflow")
    database: str = Field(default="mlflow")


class MLflowConfig(BaseModel):
    """MLflow service configuration"""

    enabled: bool = Field(default=True)
    image: str = Field(default="ghcr.io/mlflow/mlflow:latest")
    port: int = Field(default=5000)
    postgres: MLflowPostgresConfig = Field(
        default_factory=MLflowPostgresConfig
    )


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
    ray_data: str = Field(default="./data/ray")


class Config(BaseModel):
    """Main configuration model"""

    host: HostConfig = Field(default_factory=HostConfig)
    project: ProjectConfig
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    services: ServicesConfig = Field(default_factory=ServicesConfig)
    volumes: VolumesConfig = Field(default_factory=VolumesConfig)
