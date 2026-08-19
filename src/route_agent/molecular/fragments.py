from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from rdkit import Chem

from route_agent.models.frozen import FrozenModel
from route_agent.paths import fragments_path

DEFAULT_FRAGMENTS_PATH = fragments_path()
SUPPORTED_FRAGMENTS_SCHEMA = "1.0.0"


class FragmentPort(FrozenModel):
    map: int
    cap: str


class FragmentPka(FrozenModel):
    name: str
    value: float
    kind: Literal["acid", "base"]


class FragmentRecord(FrozenModel):
    id: str
    aliases: tuple[str, ...]
    kind: str
    smiles: str
    d_smiles: str | None = None
    ports: dict[str, FragmentPort]
    pka: tuple[FragmentPka, ...] = ()


class FragmentCatalog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_FRAGMENTS_PATH
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        version = str(payload.get("schema_version") or "")
        if version != SUPPORTED_FRAGMENTS_SCHEMA:
            raise ValueError(
                f"unsupported molecular_fragments schema_version {version!r}; "
                f"expected {SUPPORTED_FRAGMENTS_SCHEMA!r}"
            )
        records = tuple(
            FragmentRecord.model_validate(item) for item in payload["fragments"]
        )
        self.records = records
        by_id: dict[str, FragmentRecord] = {}
        aliases: dict[str, str] = {}
        seen_ids: set[str] = set()
        for record in records:
            if record.id in seen_ids:
                raise ValueError(f"duplicate fragment id {record.id!r}")
            seen_ids.add(record.id)
            _parse_smiles(record.smiles, record.id)
            if record.d_smiles:
                _parse_smiles(record.d_smiles, f"{record.id}.d")
            _validate_ports(record)
            by_id[record.id] = record
            aliases[_normalize_alias(record.id)] = record.id
            for alias in record.aliases:
                aliases[_normalize_alias(alias)] = record.id
        self._by_id = by_id
        self._aliases = aliases

    def get(self, key: str) -> FragmentRecord | None:
        for candidate in _alias_lookup_keys(key):
            fragment_id = self._aliases.get(_normalize_alias(candidate))
            if fragment_id is not None:
                return self._by_id[fragment_id]
            record = self._by_id.get(candidate)
            if record is not None:
                return record
        return None

    def require(self, key: str) -> FragmentRecord:
        record = self.get(key)
        if record is None:
            raise KeyError(key)
        return record


def _parse_smiles(smiles: str, label: str) -> None:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"unreadable SMILES for {label}: {smiles}")


def _validate_ports(record: FragmentRecord) -> None:
    mol = Chem.MolFromSmiles(record.smiles)
    assert mol is not None
    maps = {
        atom.GetAtomMapNum()
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() == 0 and atom.GetAtomMapNum()
    }
    declared = {port.map for port in record.ports.values()}
    if maps != declared:
        raise ValueError(
            f"{record.id} port maps {sorted(declared)} != dummy maps {sorted(maps)}"
        )


def _normalize_alias(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())


def _alias_lookup_keys(key: str) -> tuple[str, ...]:
    stripped = key.strip()
    if not stripped:
        return ()
    keys = [stripped, _normalize_alias(stripped)]
    if "(" in stripped:
        keys.append(stripped.split("(", 1)[0].strip())
        keys.append(_normalize_alias(stripped.split("(", 1)[0]))
    if stripped.lower().startswith("d-"):
        keys.append(stripped[2:].strip())
        keys.append(_normalize_alias(stripped[2:]))
    return tuple(dict.fromkeys(keys))
