#!/usr/bin/env bash
# Install a built wheel with pipx in a throwaway home and run the offline smoke.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 path/to/peptaris_route_agent-*.whl" >&2
  exit 2
fi

wheel="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
if [[ ! -f "$wheel" ]]; then
  echo "wheel not found: $wheel" >&2
  exit 2
fi

tmp="$(mktemp -d "${TMPDIR:-/tmp}/route-agent-pipx.XXXXXX")"
cleanup() {
  rm -rf "$tmp"
}
trap cleanup EXIT

export PIPX_HOME="$tmp/pipx"
export PIPX_BIN_DIR="$tmp/bin"
export PATH="$PIPX_BIN_DIR:$PATH"
mkdir -p "$PIPX_HOME" "$PIPX_BIN_DIR"

if ! command -v pipx >/dev/null 2>&1; then
  python3 -m pip install --user pipx
  export PATH="${HOME}/.local/bin:${PATH}"
fi

python_for_pipx="$(command -v python3)"
if [[ -n "${DIST_SMOKE_PYTHON:-}" ]]; then
  python_for_pipx="$DIST_SMOKE_PYTHON"
fi

pipx install --python "$python_for_pipx" "$wheel"

# Leave the checkout so the install cannot fall back to source files.
cd "$tmp"

route-agent --version
version_line="$(route-agent --version)"
if [[ -n "${EXPECT_VERSION:-}" ]]; then
  if [[ "$version_line" != *"$EXPECT_VERSION"* ]]; then
    echo "version mismatch: $version_line does not contain $EXPECT_VERSION" >&2
    exit 1
  fi
fi
if [[ "$version_line" == *"0+unknown"* ]]; then
  echo "installed CLI reported unknown version: $version_line" >&2
  exit 1
fi

route-agent doctor --no-model

printf '%s\n' '{"request_id":"T-WHEEL","parent_name":"x","sequence":"ACDEK","parent_c_terminus":"amide","residue_annotations":{},"parent_features":[],"modifications":[{"family":"n_term_acetylation","site":"N-term"}],"intent":"pipx smoke"}' > req.json
ROUTE_AGENT_MOLECULAR_SKIP_3D=true route-agent run req.json --no-model > verdict.json
python3 -c 'import json, pathlib; json.load(pathlib.Path("verdict.json").open())'

venv_python="$PIPX_HOME/venvs/peptaris-route-agent/bin/python"
"$venv_python" - <<'PY'
from route_agent.version import package_version
from route_agent_api.app import create_app
from route_agent_api.deps import get_settings, get_store, health_payload

app = create_app()
version = package_version()
assert app.version == version, (app.version, version)
assert version != "0+unknown", version
payload = health_payload(get_store(), get_settings())
assert "checks" in payload, payload
print(f"api ok version={version}")
PY

echo "pipx smoke ok $wheel"
