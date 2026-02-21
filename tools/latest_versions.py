# Copyright (c) 2026 plumiume
# SPDX-License-Identifier: <<spdxid>>
# License: MIT License (https://opensource.org/licenses/MIT)
# See LICENSE.txt for details.


#!/usr/bin/env python3
"""Latest versions summary fetcher.

- Docker CUDA images (Docker Hub: nvidia/cuda)
- Python (CPython GitHub Releases)
- PyTorch (PyPI: torch)

Usage:
    uv run python tools/latest_versions.py
    uv run python tools/latest_versions.py --ubuntu 22.04 --max-pages 8
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import requests
from requests.exceptions import RequestException

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False)
console = Console()


USER_AGENT = "cslr-exp-platform/latest_versions.py"

COMMON_HEADERS: dict[str, str] = {
    "User-Agent": USER_AGENT,
}

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
GITHUB_HEADERS: dict[str, str] = {
    **COMMON_HEADERS,
    "Accept": "application/vnd.github+json",
    **({"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}),
}

JSON_HEADERS: dict[str, str] = {
    **COMMON_HEADERS,
    "Accept": "application/json",
}

HTML_HEADERS: dict[str, str] = {
    **COMMON_HEADERS,
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}


@dataclass(frozen=True)
class CudaTagInfo:
    tag: str
    cuda_version: tuple[int, int, int] | None
    flavor: str | None  # base/runtime/devel
    cudnn: bool
    distro: str | None  # ubuntu/ubi
    distro_version: str | None  # 22.04, 9, etc.
    last_updated: str | None


_CUDA_TAG_RE = re.compile(
    r"^(?P<ver>\d+\.\d+\.\d+)-(?:(?P<cudnn>cudnn)-)?(?P<flavor>base|runtime|devel)-(?P<distro>ubuntu|ubi)(?P<distrover>\d+(?:\.\d+)?)$"  # noqa: E501
)


def _parse_cuda_version(s: str) -> tuple[int, int, int] | None:
    try:
        major_s, minor_s, patch_s = s.split(".")
        return int(major_s), int(minor_s), int(patch_s)
    except Exception:
        return None


def _iter_dockerhub_tags(
    repo: str, *, page_size: int, max_pages: int
) -> Iterable[dict[str, Any]]:
    # Docker Hub v2 public API
    # Example:
    # https://hub.docker.com/v2/repositories/nvidia/cuda/tags?page_size=100&page=1
    base = f"https://hub.docker.com/v2/repositories/{repo}/tags"
    for page in range(1, max_pages + 1):
        url = f"{base}?page_size={page_size}&page={page}"
        resp = requests.get(url, headers=JSON_HEADERS, timeout=20.0)
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()
        results: list[dict[str, Any] | Any] = payload.get("results") or []
        for item in results:
            if isinstance(item, dict):
                yield item
        if not payload.get("next"):
            return


def _parse_cuda_tag(tag: str, last_updated: str | None) -> CudaTagInfo:
    m = _CUDA_TAG_RE.match(tag)
    if not m:
        return CudaTagInfo(
            tag=tag,
            cuda_version=None,
            flavor=None,
            cudnn=False,
            distro=None,
            distro_version=None,
            last_updated=last_updated,
        )

    ver = _parse_cuda_version(m.group("ver"))
    return CudaTagInfo(
        tag=tag,
        cuda_version=ver,
        flavor=m.group("flavor"),
        cudnn=bool(m.group("cudnn")),
        distro=m.group("distro"),
        distro_version=m.group("distrover"),
        last_updated=last_updated,
    )


def _pick_latest(tags: Iterable[CudaTagInfo]) -> CudaTagInfo | None:
    best: CudaTagInfo | None = None
    for t in tags:
        if t.cuda_version is None:
            continue
        if best is None:
            best = t
            continue
        assert best.cuda_version is not None
        if t.cuda_version > best.cuda_version:
            best = t
            continue
        if t.cuda_version == best.cuda_version:
            # Tie-breaker: last_updated if available (lex order works for ISO8601)
            if (t.last_updated or "") > (best.last_updated or ""):
                best = t
    return best


def _fmt_ver(ver: tuple[int, int, int] | None) -> str:
    if ver is None:
        return "-"
    return f"{ver[0]}.{ver[1]}.{ver[2]}"


def _fetch_latest_python() -> tuple[str | None, str | None, str | None]:
    # Prefer GitHub Releases (stable). tag_name usually like "v3.13.1".
    github_url = "https://api.github.com/repos/python/cpython/releases/latest"
    try:
        resp = requests.get(github_url, headers=GITHUB_HEADERS, timeout=20.0)
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name")
        published_at = data.get("published_at")
        html_url = data.get("html_url")
        if isinstance(tag, str) and tag.startswith("v"):
            tag = tag[1:]
        if not isinstance(tag, str):
            tag = None
        if not isinstance(published_at, str):
            published_at = None
        if not isinstance(html_url, str):
            html_url = None
        if tag:
            return tag, published_at, html_url
    except RequestException:
        pass

    # Fallback: scrape python.org downloads.
    downloads_url = "https://www.python.org/downloads/"
    resp = requests.get(downloads_url, headers=HTML_HEADERS, timeout=20.0)
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    html = resp.text
    versions = re.findall(r"Python (\d+\.\d+\.\d+)", html)
    if not versions:
        return None, None, downloads_url

    def as_tuple(v: str) -> tuple[int, int, int]:
        a, b, c = v.split(".")
        return int(a), int(b), int(c)

    ver = max(versions, key=as_tuple)
    slug = ver.replace(".", "")

    release_path = None
    m2 = re.search(
        rf'href="(?P<href>/downloads/release/python-{re.escape(slug)}/)"', html
    )
    if m2:
        release_path = m2.group("href")
    else:
        # Best-effort: first release link on the page
        m_any = re.search(r'href="(?P<href>/downloads/release/python-[^"]+/)"', html)
        if m_any:
            release_path = m_any.group("href")

    release_url = (
        f"https://www.python.org{release_path}" if release_path else downloads_url
    )

    published = None
    try:
        resp2 = requests.get(release_url, headers=HTML_HEADERS, timeout=20.0)
        resp2.raise_for_status()
        resp2.encoding = resp2.encoding or "utf-8"
        release_html = resp2.text
        m3 = re.search(r"Release Date:\s*</strong>\s*(?P<date>[^<]+)", release_html)
        if m3:
            published = m3.group("date").strip()
    except RequestException:
        published = None

    return ver, published, release_url


def _fetch_latest_torch() -> tuple[str | None, str | None, str | None]:
    url = "https://pypi.org/pypi/torch/json"
    resp = requests.get(url, headers=JSON_HEADERS, timeout=20.0)
    resp.raise_for_status()
    data: dict[str, Any] | None = resp.json()
    if not isinstance(data, dict):
        return None, None, None

    info: dict[str, Any] | None = data.get("info")
    if not isinstance(info, dict):
        return None, None, None

    version = info.get("version")
    project_url = info.get("project_url") or info.get("package_url")

    upload_time = None
    # releases[version] is a list of files; pick max upload_time_iso_8601
    releases: dict[str, Any] | None = data.get("releases")
    if isinstance(releases, dict) and isinstance(version, str):
        files: list[dict[str, Any]] | None = releases.get(version)
        if isinstance(files, list):
            times: list[str] = []
            for f in files:
                if isinstance(f.get("upload_time_iso_8601"), str):
                    times.append(f["upload_time_iso_8601"])
            if times:
                upload_time = max(times)

    if not isinstance(version, str):
        version = None
    if not isinstance(project_url, str):
        project_url = None

    return version, upload_time, project_url


@app.command()
def main(
    ubuntu: str = typer.Option(
        "22.04",
        help="CUDA tag抽出で優先する Ubuntu バージョン (例: 22.04, 20.04)",
    ),
    repo: str = typer.Option(
        "nvidia/cuda",
        help="Docker Hub repository (owner/name)",
    ),
    max_pages: int = typer.Option(
        5,
        min=1,
        max=50,
        help="Docker Hub API の最大ページ数 (page_size=100)",
    ),
) -> None:
    now = datetime.now(timezone.utc).astimezone()

    # ---- Fetch
    try:
        raw_tags = list[dict[str, Any]](
            _iter_dockerhub_tags(repo, page_size=100, max_pages=max_pages)
        )
    except RequestException as e:
        console.print(f"[red]Docker Hub 取得に失敗: {e}[/red]")
        raw_tags = []

    cuda_tags: list[CudaTagInfo] = []
    for item in raw_tags:
        name: str | None = item.get("name")
        last_updated = item.get("last_updated")
        if isinstance(name, str):
            cuda_tags.append(
                _parse_cuda_tag(
                    name, last_updated if isinstance(last_updated, str) else None
                )
            )

    try:
        py_ver, py_published_at, py_url = _fetch_latest_python()
    except RequestException as e:
        console.print(f"[yellow]Python 取得に失敗: {e}[/yellow]")
        py_ver, py_published_at, py_url = None, None, None

    try:
        torch_ver, torch_uploaded_at, torch_url = _fetch_latest_torch()
    except RequestException as e:
        console.print(f"[yellow]PyTorch (PyPI) 取得に失敗: {e}[/yellow]")
        torch_ver, torch_uploaded_at, torch_url = None, None, None

    # ---- Summarize CUDA
    overall_latest = _pick_latest(cuda_tags)

    def by_key(
        *,
        flavor: str,
        cudnn: bool,
        distro: str,
        distro_version: str,
    ) -> CudaTagInfo | None:
        candidates = (
            t
            for t in cuda_tags
            if t.cuda_version is not None
            and t.flavor == flavor
            and t.cudnn == cudnn
            and t.distro == distro
            and t.distro_version == distro_version
        )
        return _pick_latest(candidates)

    picks: list[tuple[str, CudaTagInfo | None]] = []
    for flavor in ("base", "runtime", "devel"):
        picks.append(
            (
                f"{flavor} (no cudnn) ubuntu{ubuntu}",
                by_key(
                    flavor=flavor, cudnn=False, distro="ubuntu", distro_version=ubuntu
                ),
            )
        )
    for flavor in ("runtime", "devel"):
        picks.append(
            (
                f"{flavor} (cudnn) ubuntu{ubuntu}",
                by_key(
                    flavor=flavor, cudnn=True, distro="ubuntu", distro_version=ubuntu
                ),
            )
        )

    # ---- Output
    header = Table(show_header=False, box=None)
    header.add_column("k", style="bold")
    header.add_column("v")
    header.add_row("Generated", now.strftime("%Y-%m-%d %H:%M:%S %Z"))
    header.add_row("Docker Hub", f"{repo} (pages={max_pages}, page_size=100)")
    header.add_row("Python", "python/cpython releases/latest")
    header.add_row("PyTorch", "PyPI torch")
    console.print(header)

    t1 = Table(title="Latest Versions", show_lines=False)
    t1.add_column("Component", style="bold")
    t1.add_column("Version/Tag")
    t1.add_column("Date")
    t1.add_column("URL")

    if overall_latest is None:
        t1.add_row(
            "CUDA (overall)", "-", "-", "https://hub.docker.com/r/nvidia/cuda/tags"
        )
    else:
        t1.add_row(
            "CUDA (overall)",
            overall_latest.tag,
            overall_latest.last_updated or "-",
            "https://hub.docker.com/r/nvidia/cuda/tags",
        )

    t1.add_row(
        "Python",
        py_ver or "-",
        py_published_at or "-",
        py_url or "https://github.com/python/cpython/releases/latest",
    )
    t1.add_row(
        "PyTorch (torch)",
        torch_ver or "-",
        torch_uploaded_at or "-",
        torch_url or "https://pypi.org/project/torch/",
    )

    console.print(t1)

    t2 = Table(title=f"CUDA tag picks (ubuntu{ubuntu})")
    t2.add_column("Pick", style="bold")
    t2.add_column("CUDA")
    t2.add_column("Tag")
    t2.add_column("Updated")

    for label, info in picks:
        if info is None:
            t2.add_row(label, "-", "-", "-")
        else:
            t2.add_row(
                label, _fmt_ver(info.cuda_version), info.tag, info.last_updated or "-"
            )

    console.print(t2)

    # A small hint when GitHub API is used but likely blocked by auth/rate limit.
    if (
        py_ver is None
        and py_url
        and "github.com" in py_url
        and (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")) is None
    ):
        console.print(
            "[dim]Note: GitHub API が rate limit の場合は GITHUB_TOKEN/GH_TOKEN を設定すると改善します。[/dim]"  # noqa: E501
        )


if __name__ == "__main__":
    raise SystemExit(app())
