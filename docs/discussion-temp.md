# Discussion Notes (Temporary)

## Goal
Update compose.yaml to use Dockerfile `ray-runtime` and validate service viability, including marimo-ray connectivity.

## Current Status
- Dockerfile already provides `ray-runtime` and `marimo-runtime` stages.
- Plan created in notes with phased steps and validation checks.
- Implementation work started:
  - Added `.dockerignore` for faster builds.
  - Updated `template/ray-ep.sh` to detect conda env and use `conda run -n py` when `USE_CONDA_ENV=1`.
  - Added build config support to `ws` config models (`BuildConfig` and `build` fields for Ray/Marimo).
  - Updated `config.yaml` and `config.example.yaml` to use `cslr-exp-platform:ray-runtime` and `cslr-exp-platform:marimo-runtime` with build settings.

## Key Decisions
- Use Dockerfile `ray-runtime` image for both CPU and GPU services.
- Use `marimo-runtime` for marimo service.
- Use build section in compose template when build settings are enabled.
- Switch runtime behavior via `USE_CONDA_ENV=1`.

## Pending
- Re-apply compose template changes (build sections and marimo command) after a reset.
- Run `uv run ws generate` to confirm template compiles.
- Build images and test services:
  - `docker build --target ray-runtime -t cslr-exp-platform:ray-runtime .`
  - `docker build --target marimo-runtime -t cslr-exp-platform:marimo-runtime .`
  - `uv run ws up -d`
- Verify:
  - Ray status and dashboard.
  - marimo connects to Ray via `ray://ray-cpu:10001`.

## Notes
- Compose template previously failed due to malformed Jinja blocks; it was reset and needs careful re-editing.
- Tests to run after updates: `uv run ws generate`, `uv run ws up -d`, Ray client connection from marimo.
