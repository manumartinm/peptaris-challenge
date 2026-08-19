"""Boltz structure-and-binding client. Chemistry stays in RDKit; this is 3D only."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Protocol

from route_agent.models.molecular import (
    ConformerEnsemble,
    MolecularIssue,
    MolecularRecipe,
)

BOLTZ_API_URL = "https://api.boltz.bio"
BOLTZ_MODEL = "boltz-2.1"
PREDICT_PATH = "/compute/v1/predictions/structure-and-binding"
CONFIDENCE_THRESHOLD = 0.5
DEFAULT_NUM_SAMPLES = 1


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes | None,
        timeout_s: float,
    ) -> tuple[int, str]: ...


class UrllibTransport:
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes | None,
        timeout_s: float,
    ) -> tuple[int, str]:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as response:
                return int(response.getcode() or 0), response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            return int(exc.code), payload
        except urllib.error.URLError as exc:
            raise BoltzRequestError("boltz_unavailable", str(exc.reason)) from exc


class BoltzRequestError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def recipe_is_cyclic(recipe: MolecularRecipe) -> bool:
    for bond in recipe.bonds:
        ends = {bond.from_atom, bond.to_fragment}
        if "N-term" in ends and "C-term" in ends:
            return True
    return False


def sequence_only_reasons(recipe: MolecularRecipe) -> tuple[str, ...]:
    reasons: list[str] = []
    if recipe.fragments:
        reasons.append("fragments")
    if recipe.n_methyl_sites:
        reasons.append("n_methyl_sites")
    if recipe.residue_overrides:
        reasons.append("residue_overrides")
    if recipe.unknowns:
        reasons.append("unknowns")
    return tuple(reasons)


def sequence_only_issue(recipe: MolecularRecipe) -> MolecularIssue | None:
    reasons = sequence_only_reasons(recipe)
    if not reasons:
        return None
    shown = ", ".join(reasons)
    return MolecularIssue(
        code="boltz_sequence_only",
        message=f"backbone only; PTMs not sent to Boltz ({shown})",
        path="product",
    )


def build_structure_input(
    recipe: MolecularRecipe, *, num_samples: int = DEFAULT_NUM_SAMPLES
) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "type": "protein",
        "value": recipe.sequence,
        "chain_ids": ["A"],
        "msa": {"type": "empty"},
    }
    if recipe_is_cyclic(recipe):
        entity["cyclic"] = True
    return {
        "model": BOLTZ_MODEL,
        "input": {"entities": [entity], "num_samples": num_samples},
    }


def failed_ensemble(
    *,
    code: str,
    message: str,
    extra_issues: tuple[MolecularIssue, ...] = (),
    n_requested: int = DEFAULT_NUM_SAMPLES,
) -> ConformerEnsemble:
    issues = (
        MolecularIssue(code=code, message=message, path="product"),
    ) + extra_issues
    return ConformerEnsemble(
        embedding_ok=False,
        converged=False,
        n_requested=n_requested,
        n_embedded=0,
        n_optimized=0,
        valid_fraction=0.0,
        forcefield="boltz",
        n_clashes=0,
        issues=issues,
    )


def ensemble_from_prediction(
    prediction: dict[str, Any],
    *,
    cif: str | None,
    extra_issues: tuple[MolecularIssue, ...] = (),
    n_requested: int = DEFAULT_NUM_SAMPLES,
) -> ConformerEnsemble:
    status = str(prediction.get("status") or "")
    if status == "failed":
        raw_error = prediction.get("error")
        error = raw_error if isinstance(raw_error, dict) else {}
        return failed_ensemble(
            code="boltz_failed",
            message=str(error.get("message") or "prediction failed"),
            extra_issues=extra_issues,
            n_requested=n_requested,
        )
    output = prediction.get("output")
    if status != "succeeded" or not isinstance(output, dict):
        return failed_ensemble(
            code="boltz_failed",
            message=f"unexpected status {status or 'missing'}",
            extra_issues=extra_issues,
            n_requested=n_requested,
        )
    sample = output.get("best_sample")
    if not isinstance(sample, dict):
        samples = output.get("all_sample_results")
        sample = samples[0] if isinstance(samples, list) and samples else None
    if not isinstance(sample, dict) or not cif:
        return failed_ensemble(
            code="boltz_failed",
            message="prediction succeeded but no structure CIF was returned",
            extra_issues=extra_issues,
            n_requested=n_requested,
        )
    raw_metrics = sample.get("metrics")
    metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
    confidence = _optional_float(metrics.get("structure_confidence"))
    ptm = _optional_float(metrics.get("ptm"))
    plddt = _optional_float(metrics.get("complex_plddt"))
    score = confidence if confidence is not None else plddt
    return ConformerEnsemble(
        embedding_ok=True,
        converged=score is not None and score >= CONFIDENCE_THRESHOLD,
        n_requested=n_requested,
        n_embedded=1,
        n_optimized=1,
        valid_fraction=1.0,
        forcefield="boltz",
        n_clashes=0,
        cif=cif,
        structure_confidence=confidence,
        ptm=ptm,
        complex_plddt=plddt,
        issues=extra_issues,
    )


class BoltzClient:
    """Submit, poll, and download one structure-and-binding prediction."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BOLTZ_API_URL,
        timeout_s: float = 180.0,
        poll_interval_s: float = 5.0,
        transport: HttpTransport | None = None,
        sleeper: Any = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._poll_interval_s = poll_interval_s
        self._transport = transport or UrllibTransport()
        self._sleep = sleeper

    def predict_structure(self, recipe: MolecularRecipe) -> ConformerEnsemble:
        extra = sequence_only_issue(recipe)
        extras = (extra,) if extra is not None else ()
        try:
            started = self._start(build_structure_input(recipe))
            finished = self._poll(str(started.get("id") or ""))
            cif = self._download_cif(finished)
            return ensemble_from_prediction(finished, cif=cif, extra_issues=extras)
        except BoltzRequestError as exc:
            return failed_ensemble(
                code=exc.code, message=exc.message, extra_issues=extras
            )

    def _start(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json(
            "POST",
            f"{self._base_url}{PREDICT_PATH}",
            body=payload,
            auth=True,
        )

    def _poll(self, prediction_id: str) -> dict[str, Any]:
        if not prediction_id:
            raise BoltzRequestError("boltz_failed", "start response missing id")
        deadline = time.monotonic() + self._timeout_s
        url = f"{self._base_url}{PREDICT_PATH}/{prediction_id}"
        latest: dict[str, Any] = {}
        while time.monotonic() < deadline:
            latest = self._json("GET", url, auth=True)
            status = latest.get("status")
            if status in {"succeeded", "failed"}:
                return latest
            self._sleep(self._poll_interval_s)
        raise BoltzRequestError(
            "boltz_timeout",
            f"exceeded {self._timeout_s}s waiting for {prediction_id}",
        )

    def _download_cif(self, prediction: dict[str, Any]) -> str | None:
        output = prediction.get("output")
        if not isinstance(output, dict):
            return None
        sample = output.get("best_sample")
        if not isinstance(sample, dict):
            return None
        structure = sample.get("structure")
        if not isinstance(structure, dict):
            return None
        url = structure.get("url")
        if not isinstance(url, str) or not url:
            return None
        status, body = self._transport.request(
            "GET",
            url,
            headers={},
            body=None,
            timeout_s=min(30.0, self._timeout_s),
        )
        if status >= 400 or not body.strip():
            return None
        return body

    def _json(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None = None,
        auth: bool,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode("utf-8")
        if auth:
            headers["x-api-key"] = self._api_key
        status, text = self._transport.request(
            method,
            url,
            headers=headers,
            body=payload,
            timeout_s=min(30.0, self._timeout_s),
        )
        if status >= 400:
            raise BoltzRequestError(
                "boltz_unavailable"
                if status >= 500 or status == 401
                else "boltz_failed",
                f"HTTP {status}: {_error_message(text)}",
            )
        try:
            loaded = json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            raise BoltzRequestError("boltz_failed", "invalid JSON from Boltz") from exc
        if not isinstance(loaded, dict):
            raise BoltzRequestError("boltz_failed", "Boltz JSON must be an object")
        return loaded


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _error_message(text: str) -> str:
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return text[:200] or "empty body"
    if isinstance(loaded, dict):
        error = loaded.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if loaded.get("message"):
            return str(loaded["message"])
    return text[:200]
