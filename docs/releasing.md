# Releasing route-agent

This repository ships a Python package. CI validates every pull request.
Publication happens only when Release Please creates a GitHub Release on
`main`. Do not reuse a version number: PyPI is immutable.

Eval tests are not a release gate yet. Pull requests already run the
offline official eval (`eval-offline`). Live-model scoring is a separate
weekly/manual workflow and does not block publish.

## Everyday flow

1. Merge changes to `main` with [Conventional Commits](https://www.conventionalcommits.org/):
   `feat:`, `fix:`, `perf:`, `docs:`, `chore:`. A `feat` on 0.x bumps minor
   (`0.1.0` → `0.2.0`). A `fix` bumps patch. `feat!` or a `BREAKING CHANGE`
   footer still stays on 0.x as a minor bump (`bump-minor-pre-major`).
2. Release Please opens or updates a release PR that edits `pyproject.toml`
   and `CHANGELOG.md`.
3. Review that PR, then merge it.
4. The same `release.yml` workflow sees `release_created`, checks out the new
   tag, builds wheel+sdist once, inspects metadata, runs the pipx smoke, attaches
   artifacts to the GitHub Release, and publishes those same files to PyPI via
   Trusted Publishing.

The version in `pyproject.toml` is the source of truth for the next tagged
release. CLI (`route-agent --version`) and the FastAPI app read
`importlib.metadata` after install. Do not edit the version by hand.

## Local checks before you push

```bash
uv sync --frozen --group dev
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src tests
uv run pytest tests -m "not live and not eval"
uv build
uv run twine check --strict dist/*
uv run python scripts/inspect_dist.py dist
DIST_SMOKE_PYTHON="$(uv python find 3.12)" ./scripts/dist_smoke.sh dist/peptaris_route_agent-*.whl
```

The smoke script installs into a temporary `PIPX_HOME`. It must not read files
from the git checkout.

## First-time GitHub and PyPI setup

Do this once after the remote exists. These steps are not automated from this
repo.

### GitHub

- Enable Actions.
- Protect `main`: require the `ci` check, require pull requests, and block
  direct pushes.
- Create an Environment named `pypi`. Restrict it to `main`. Add required
  reviewers if you want a human gate on publish. Do not store a PyPI API token
  in GitHub Secrets; publishing uses OIDC.

### PyPI Trusted Publishing

The PyPI project is `peptaris-route-agent`. `route-agent` / `routeagent` is
already taken by an unrelated package. The CLI entry point stays `route-agent`.

1. Create a PyPI account.
2. Add a pending trusted publisher:
   - Project name: `peptaris-route-agent`
   - Publisher: GitHub
   - Owner / repository: the GitHub repo that will run Actions
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. The first successful publish from that workflow claims the name.

If publish fails after a GitHub Release exists, cut a new version. Never try to
overwrite files already on PyPI.

## Failure recovery

| Symptom | What to do |
| --- | --- |
| Release PR looks wrong | Fix commits on `main` or adjust the PR; do not push a handmade tag. |
| `package` / `build` smoke fails | Fix packaging, merge, let the next release PR retry. |
| PyPI publish fails after the GitHub Release | Inspect the `pypi` environment logs. After a failed upload of a new version you may retry the same version only if PyPI never stored the files. If any file landed, bump. |
| Installed CLI prints `0+unknown` | The environment is not an install. Reinstall the wheel or the PyPI package. |
| `uv sync --frozen` fails after a version bump | Run `uv lock` on the release PR if the lockfile still lists the previous local version. |

## What CI does not do

- No `git push`, tag, or PyPI upload from a pull request.
- No live model tests (`pytest -m live`).
- No live official eval (`eval-live.yml`). That workflow is manual/weekly and
  fails when `data/score.py` reports `score < 0.75`. It is not a release gate.
- No GitHub or PyPI settings changes. Those stay manual.

PR CI does run `eval-offline`: `debug eval --no-model --strict` against
`data/design_requests.jsonl` and `data/expected_dev.jsonl`. That job checks
schema, traces, and wiring, not live-model quality.
