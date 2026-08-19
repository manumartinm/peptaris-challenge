from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from route_agent.models.molecular import (
    Bond,
    MolecularIssue,
    MolecularRecipe,
    TwoDValidation,
)
from route_agent.molecular.fragments import FragmentCatalog, FragmentRecord

_BOND_TYPES = {
    "amide": Chem.BondType.SINGLE,
    "disulfide": Chem.BondType.SINGLE,
    "thioether": Chem.BondType.SINGLE,
    "single": Chem.BondType.SINGLE,
    "olefin": Chem.BondType.DOUBLE,
    "double": Chem.BondType.DOUBLE,
}


@dataclass
class BuildResult:
    mol: Chem.Mol | None
    two_d_validation: TwoDValidation
    ionizable: tuple[tuple[str, float, str], ...]
    issues: tuple[MolecularIssue, ...]


class MolecularBuilder:
    def __init__(self, catalog: FragmentCatalog | None = None) -> None:
        self._catalog = catalog or FragmentCatalog()

    def build(self, recipe: MolecularRecipe) -> BuildResult:
        issues: list[MolecularIssue] = []
        try:
            mol, ionizable = self._assemble_molecule(recipe, issues)
        except Exception as exc:  # noqa: BLE001
            issue = MolecularIssue(
                code="build_failed",
                message=str(exc),
                path="product",
            )
            return BuildResult(
                mol=None,
                two_d_validation=TwoDValidation(valid=False, issues=(issue,)),
                ionizable=(),
                issues=(issue,),
            )
        if mol is None:
            two_d_validation = TwoDValidation(valid=False, issues=tuple(issues))
            return BuildResult(
                mol=None,
                two_d_validation=two_d_validation,
                ionizable=(),
                issues=tuple(issues),
            )
        try:
            Chem.SanitizeMol(mol)
        except Exception as exc:  # noqa: BLE001
            issues.append(
                MolecularIssue(
                    code="invalid_graph",
                    message=f"sanitize failed: {exc}",
                    path="product",
                )
            )
            two_d_validation = TwoDValidation(valid=False, issues=tuple(issues))
            return BuildResult(
                mol=None,
                two_d_validation=two_d_validation,
                ionizable=ionizable,
                issues=tuple(issues),
            )
        mol.UpdatePropertyCache(strict=False)
        formula = rdMolDescriptors.CalcMolFormula(mol)
        exact_mw = float(rdMolDescriptors.CalcExactMolWt(mol))
        smiles = Chem.MolToSmiles(mol)
        two_d_validation = TwoDValidation(
            valid=True,
            formula=formula,
            exact_mw=exact_mw,
            smiles=smiles,
            issues=tuple(issues),
        )
        return BuildResult(
            mol=mol,
            two_d_validation=two_d_validation,
            ionizable=ionizable,
            issues=tuple(issues),
        )

    def _assemble(
        self, recipe: MolecularRecipe, issues: list[MolecularIssue]
    ) -> tuple[Chem.Mol | None, tuple[tuple[str, float, str], ...]]:
        return self._assemble_molecule(recipe, issues)

    def _assemble_molecule(
        self, recipe: MolecularRecipe, issues: list[MolecularIssue]
    ) -> tuple[Chem.Mol | None, tuple[tuple[str, float, str], ...]]:
        residues, ionizable = self._build_backbone(recipe, issues)
        if residues is None:
            return None, ()
        product, fragment_owners, ionizable = self._attach_fragments(
            residues, recipe, ionizable, issues
        )
        if product is None:
            return None, ()
        product = self._apply_bonds(product, recipe, residues, fragment_owners, issues)
        if product is None:
            return None, ()
        product = self._cap_termini(product, recipe, residues)
        for token, _record, _mol in residues:
            if self._matches_n_methyl_site(
                token, recipe.n_methyl_sites, recipe.sequence
            ):
                product = self._add_n_methyl(product, token)
        product = self._cap_remaining_open_ports(product, residues, fragment_owners)
        ionizable.extend(self._terminus_ionizable(recipe))
        return product, tuple(ionizable)

    def _build_backbone(
        self, recipe: MolecularRecipe, issues: list[MolecularIssue]
    ) -> tuple[
        list[tuple[str, FragmentRecord, Chem.Mol]] | None,
        list[tuple[str, float, str]],
    ]:
        if not recipe.sequence:
            issues.append(
                MolecularIssue(
                    code="empty_sequence", message="no residues", path="sequence"
                )
            )
            return None, []
        residues: list[tuple[str, FragmentRecord, Chem.Mol]] = []
        ionizable: list[tuple[str, float, str]] = []
        for index, letter in enumerate(recipe.sequence, start=1):
            token = f"{letter}{index}"
            record, d_stereo, missing = self._residue_record(recipe, token, letter)
            if record is None:
                issues.append(
                    MolecularIssue(
                        code="missing_fragment",
                        message=missing or f"no fragment for {token}",
                        path=token,
                    )
                )
                return None, []
            gem = recipe.c_terminus == "gem_diamino" and index == len(recipe.sequence)
            mol = self._build_fragment_molecule(
                record,
                owner=token,
                d_stereo=d_stereo,
                gem_diamino=gem,
            )
            if mol is None:
                issues.append(
                    MolecularIssue(
                        code="unreadable_smiles",
                        message=record.id,
                        path=token,
                    )
                )
                return None, []
            residues.append((token, record, mol))
            ionizable.extend(self._ionizable_sites_from_fragment(record, token))
        product = residues[0][2]
        for previous, current in zip(residues, residues[1:], strict=False):
            product = Chem.CombineMols(product, current[2])
            product = self._join_ports(
                product, previous[0], "C", current[0], "N", Chem.BondType.SINGLE
            )
        residues[0] = (residues[0][0], residues[0][1], product)
        return residues, ionizable

    def _attach_fragments(
        self,
        residues: list[tuple[str, FragmentRecord, Chem.Mol]],
        recipe: MolecularRecipe,
        ionizable: list[tuple[str, float, str]],
        issues: list[MolecularIssue],
    ) -> tuple[
        Chem.Mol | None,
        dict[str, FragmentRecord],
        list[tuple[str, float, str]],
    ]:
        product = residues[0][2]
        fragment_owners: dict[str, FragmentRecord] = {}
        for fragment in recipe.fragments:
            record = self._catalog.get(fragment.catalog_id)
            if record is None:
                issues.append(
                    MolecularIssue(
                        code="missing_fragment",
                        message=fragment.catalog_id,
                        path=fragment.instance_id,
                    )
                )
                return None, {}, ionizable
            incoming = self._build_fragment_molecule(record, owner=fragment.instance_id)
            if incoming is None:
                issues.append(
                    MolecularIssue(
                        code="unreadable_smiles",
                        message=record.id,
                        path=fragment.instance_id,
                    )
                )
                return None, {}, ionizable
            product = Chem.CombineMols(product, incoming)
            fragment_owners[fragment.instance_id] = record
            ionizable.extend(
                self._ionizable_sites_from_fragment(record, fragment.instance_id)
            )
        return product, fragment_owners, ionizable

    def _apply_bonds(
        self,
        product: Chem.Mol,
        recipe: MolecularRecipe,
        residues: list[tuple[str, FragmentRecord, Chem.Mol]],
        fragment_owners: dict[str, FragmentRecord],
        issues: list[MolecularIssue],
    ) -> Chem.Mol | None:
        for bond in recipe.bonds:
            product, bond_issue = self._apply_bond(
                product, bond, residues, fragment_owners
            )
            if bond_issue is not None:
                issues.append(bond_issue)
                return None
        return product

    def _cap_termini(
        self,
        product: Chem.Mol,
        recipe: MolecularRecipe,
        residues: list[tuple[str, FragmentRecord, Chem.Mol]],
    ) -> Chem.Mol:
        first_token = residues[0][0]
        last_token = residues[-1][0]
        if recipe.n_terminus == "free":
            product = self._cap_if_present(product, first_token, "N", "H")
        if recipe.c_terminus == "acid":
            product = self._cap_if_present(product, last_token, "C", "OH")
        elif recipe.c_terminus == "amide":
            product = self._cap_if_present(product, last_token, "C", "NH2")
        return product

    def _residue_record(
        self, recipe: MolecularRecipe, token: str, letter: str
    ) -> tuple[FragmentRecord | None, bool, str | None]:
        override = recipe.residue_overrides.get(token)
        annotation = _annotation_for(recipe.annotations, token, letter)
        d_stereo = bool(annotation and annotation.upper().startswith("D-"))
        if override:
            record = self._catalog.get(override)
            return record, d_stereo, None if record else override
        if annotation:
            record = self._catalog.get(annotation)
            if record is not None:
                if record.kind == "residue" and d_stereo:
                    return record, True, None
                return record, d_stereo, None
            if d_stereo:
                record = self._catalog.get(annotation[2:].strip())
                if record is not None:
                    return record, True, None
        record = self._catalog.get(letter)
        if record is None:
            return None, False, annotation or letter
        return record, d_stereo, None

    def _apply_bond(
        self,
        mol: Chem.Mol,
        bond: Bond,
        residues: list[tuple[str, FragmentRecord, Chem.Mol]],
        fragments: dict[str, FragmentRecord],
    ) -> tuple[Chem.Mol, MolecularIssue | None]:
        left_owner, left_port = self._parse_bond_endpoint(
            bond.from_atom, residues, fragments
        )
        right_owner, right_port = self._parse_bond_endpoint(
            bond.to_fragment, residues, fragments
        )
        if left_owner is None or left_port is None:
            return mol, MolecularIssue(
                code="unknown_port",
                message=bond.from_atom,
                path=bond.from_atom,
            )
        if right_owner is None or right_port is None:
            return mol, MolecularIssue(
                code="unknown_connectivity",
                message=bond.to_fragment,
                path=bond.to_fragment,
            )
        bond_type = _BOND_TYPES.get(bond.bond_type, Chem.BondType.SINGLE)
        try:
            joined = self._join_ports(
                mol, left_owner, left_port, right_owner, right_port, bond_type
            )
        except ValueError as exc:
            return mol, MolecularIssue(
                code="unknown_port",
                message=str(exc),
                path=f"{bond.from_atom}->{bond.to_fragment}",
            )
        return joined, None

    def _build_fragment_molecule(
        self,
        record: FragmentRecord,
        *,
        owner: str,
        d_stereo: bool = False,
        gem_diamino: bool = False,
    ) -> Chem.Mol | None:
        return _fragment_mol(
            record, owner=owner, d_stereo=d_stereo, gem_diamino=gem_diamino
        )

    def _join_ports(
        self,
        mol: Chem.Mol,
        owner_a: str,
        port_a: str,
        owner_b: str,
        port_b: str,
        bond_type: Chem.BondType,
    ) -> Chem.Mol:
        return _join_ports(mol, owner_a, port_a, owner_b, port_b, bond_type)

    def _cap_if_present(
        self, mol: Chem.Mol, owner: str, port: str, cap: str
    ) -> Chem.Mol:
        return _cap_if_present(mol, owner, port, cap)

    def _cap_remaining_open_ports(
        self,
        mol: Chem.Mol,
        residues: list[tuple[str, FragmentRecord, Chem.Mol]],
        fragments: dict[str, FragmentRecord],
    ) -> Chem.Mol:
        product, _issues = _cap_leftovers(mol, residues, fragments)
        return product

    def _add_n_methyl(self, mol: Chem.Mol, token: str) -> Chem.Mol:
        return _add_n_methyl(mol, token)

    def _parse_bond_endpoint(
        self,
        ref: str,
        residues: list[tuple[str, FragmentRecord, Chem.Mol]],
        fragments: dict[str, FragmentRecord],
    ) -> tuple[str | None, str | None]:
        return _parse_ref(ref, residues, fragments)

    def _matches_n_methyl_site(
        self, token: str, sites: tuple[str, ...], sequence: str
    ) -> bool:
        return _token_in(token, sites, sequence)

    def _ionizable_sites_from_fragment(
        self, record: FragmentRecord, owner: str
    ) -> tuple[tuple[str, float, str], ...]:
        return _ionizable_from(record, owner)

    def _terminus_ionizable(
        self, recipe: MolecularRecipe
    ) -> tuple[tuple[str, float, str], ...]:
        return _terminus_ionizable_groups(recipe)


def _fragment_mol(
    record: FragmentRecord,
    *,
    owner: str,
    d_stereo: bool = False,
    gem_diamino: bool = False,
) -> Chem.Mol | None:
    smiles = record.d_smiles if d_stereo and record.d_smiles else record.smiles
    if gem_diamino:
        smiles = smiles.replace("C(=O)[*:2]", "N")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    map_to_port = {port.map: name for name, port in record.ports.items()}
    for atom in mol.GetAtoms():
        atom.SetProp("owner", owner)
        if atom.GetAtomicNum() == 0:
            port = map_to_port.get(atom.GetAtomMapNum())
            if port:
                atom.SetProp("port", port)
                neighbors = atom.GetNeighbors()
                if neighbors and port == "N":
                    neighbors[0].SetProp("role", "backbone_n")
    return mol


def _join_ports(
    mol: Chem.Mol,
    owner_a: str,
    port_a: str,
    owner_b: str,
    port_b: str,
    bond_type: Chem.BondType,
) -> Chem.Mol:
    dummy_a = _find_dummy(mol, owner_a, port_a)
    dummy_b = _find_dummy(mol, owner_b, port_b)
    if dummy_a is None:
        raise ValueError(f"missing port {owner_a}.{port_a}")
    if dummy_b is None:
        raise ValueError(f"missing port {owner_b}.{port_b}")
    neigh_a = mol.GetAtomWithIdx(dummy_a).GetNeighbors()[0].GetIdx()
    neigh_b = mol.GetAtomWithIdx(dummy_b).GetNeighbors()[0].GetIdx()
    rw = Chem.RWMol(mol)
    rw.AddBond(neigh_a, neigh_b, bond_type)
    for dummy in sorted((dummy_a, dummy_b), reverse=True):
        rw.RemoveAtom(dummy)
    return rw.GetMol()


def _cap_if_present(mol: Chem.Mol, owner: str, port: str, cap: str) -> Chem.Mol:
    dummy = _find_dummy(mol, owner, port)
    if dummy is None:
        return mol
    return _cap_dummy(mol, dummy, cap)


def _cap_leftovers(
    mol: Chem.Mol,
    residues: list[tuple[str, FragmentRecord, Chem.Mol]],
    fragments: dict[str, FragmentRecord],
) -> tuple[Chem.Mol, list[MolecularIssue]]:
    owners: dict[str, FragmentRecord] = {token: record for token, record, _ in residues}
    owners.update(fragments)
    while True:
        dummies = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetAtomicNum() == 0]
        if not dummies:
            return mol, []
        dummy = max(dummies)
        atom = mol.GetAtomWithIdx(dummy)
        owner = atom.GetProp("owner") if atom.HasProp("owner") else ""
        port = atom.GetProp("port") if atom.HasProp("port") else ""
        record = owners.get(owner)
        cap = "H"
        if record is not None and port in record.ports:
            cap = record.ports[port].cap
        mol = _cap_dummy(mol, dummy, cap)


def _cap_dummy(mol: Chem.Mol, dummy_idx: int, cap: str) -> Chem.Mol:
    rw = Chem.RWMol(mol)
    dummy = rw.GetAtomWithIdx(dummy_idx)
    neigh = dummy.GetNeighbors()[0].GetIdx()
    if cap == "OH":
        oxygen = rw.AddAtom(Chem.Atom(8))
        rw.AddBond(neigh, oxygen, Chem.BondType.SINGLE)
    elif cap == "NH2":
        nitrogen = rw.AddAtom(Chem.Atom(7))
        rw.AddBond(neigh, nitrogen, Chem.BondType.SINGLE)
    rw.RemoveAtom(dummy_idx)
    return rw.GetMol()


def _add_n_methyl(mol: Chem.Mol, token: str) -> Chem.Mol:
    target = None
    for atom in mol.GetAtoms():
        if (
            atom.HasProp("owner")
            and atom.GetProp("owner") == token
            and atom.HasProp("role")
            and atom.GetProp("role") == "backbone_n"
        ):
            target = atom.GetIdx()
            break
    if target is None:
        return mol
    rw = Chem.RWMol(mol)
    carbon = rw.AddAtom(Chem.Atom(6))
    rw.AddBond(target, carbon, Chem.BondType.SINGLE)
    return rw.GetMol()


def _find_dummy(mol: Chem.Mol, owner: str, port: str) -> int | None:
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 0:
            continue
        if not atom.HasProp("owner") or not atom.HasProp("port"):
            continue
        if atom.GetProp("owner") == owner and atom.GetProp("port") == port:
            return atom.GetIdx()
    return None


def _parse_ref(
    ref: str,
    residues: list[tuple[str, FragmentRecord, Chem.Mol]],
    fragments: dict[str, FragmentRecord],
) -> tuple[str | None, str | None]:
    if ref in {"N-term", "N-terminal"}:
        return residues[0][0], "N"
    if ref in {"C-term", "C-terminal"}:
        return residues[-1][0], "C"
    if "." in ref:
        owner, port = ref.rsplit(".", 1)
        port = {
            "NZ": "S",
            "SG": "S",
            "CG": "S",
            "CD": "S",
            "OD": "S",
            "OE": "S",
            "NE": "S",
            "OG": "S",
            "OH": "S",
        }.get(port, port)
        return owner, port
    residue_tokens = {token for token, _record, _mol in residues}
    if ref in residue_tokens:
        return ref, "S"
    if ref in fragments:
        record = fragments[ref]
        if "C" in record.ports:
            return ref, "C"
        if "N" in record.ports:
            return ref, "N"
        return ref, next(iter(record.ports))
    for token in residue_tokens:
        if token == ref or token[1:] == ref[1:] and token[0] == ref[0]:
            return token, "S"
    return None, None


def _annotation_for(annotations: dict[str, str], token: str, letter: str) -> str | None:
    if token in annotations:
        return annotations[token]
    if letter == "X" and f"X{token[1:]}" in annotations:
        return annotations[f"X{token[1:]}"]
    return None


def _token_in(token: str, sites: tuple[str, ...], sequence: str) -> bool:
    if token in sites:
        return True
    index = token[1:]
    letter = token[0]
    for site in sites:
        if site == f"{letter}{index}":
            return True
        if len(site) >= 2 and site[0] == letter and site[1:] == index:
            return True
        if site.endswith(index) and sequence[int(index) - 1] == letter:
            return True
    return False


def _ionizable_from(
    record: FragmentRecord, owner: str
) -> tuple[tuple[str, float, str], ...]:
    return tuple((f"{owner}:{item.name}", item.value, item.kind) for item in record.pka)


def _terminus_ionizable_groups(
    recipe: MolecularRecipe,
) -> tuple[tuple[str, float, str], ...]:
    groups: list[tuple[str, float, str]] = []
    if recipe.n_terminus == "free":
        groups.append(("N-term", 9.0, "base"))
    if recipe.c_terminus == "acid":
        groups.append(("C-term", 2.2, "acid"))
    return tuple(groups)
