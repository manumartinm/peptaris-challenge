"""Chemistry notebook copied from parent to child during the walk."""

from __future__ import annotations

from typing import Any

from route_agent.models.conflict import BRANCH_KEYS, LEDGER_KEYS, ProcessTrace


class Ledger:
    LEDGER_KEYS = LEDGER_KEYS
    BRANCH_KEYS = BRANCH_KEYS

    @staticmethod
    def seed(output: dict[str, Any], parent_c_terminus: str) -> dict[str, Any]:
        seeded = {
            key: deep_copy_value(output[key])
            for key in (*LEDGER_KEYS, "history")
            if key in output
        }
        for key, value in output.items():
            if key not in seeded:
                seeded[key] = deep_copy_value(value)
        seeded.setdefault("protected", {})
        seeded.setdefault("free_amines", {})
        seeded.setdefault("catalysts_used", {})
        seeded.setdefault("termini", {"c": parent_c_terminus, "n": "free"})
        seeded.setdefault("history", [])
        seeded.setdefault("permanent_connectivity", [])
        seeded.setdefault("product_fragments", [])
        seeded.setdefault("residue_overrides", {})
        seeded.setdefault("n_methyl_sites", [])
        seeded.setdefault("product_unknowns", [])
        return seeded

    @staticmethod
    def build_child_ledger(
        parent_output: dict[str, Any], trace: ProcessTrace
    ) -> dict[str, Any]:
        output = {key: deep_copy_value(value) for key, value in parent_output.items()}
        applied = trace.model_dump(mode="json")
        history = list(output.get("history") or [])
        history.append(applied)
        output["history"] = history
        output["applied"] = applied
        return output


def deep_copy_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: deep_copy_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [deep_copy_value(item) for item in value]
    return value
