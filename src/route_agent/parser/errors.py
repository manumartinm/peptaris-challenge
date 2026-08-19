from __future__ import annotations

from typing import Any

from route_agent.models.validation import (
    ConflictKind,
    ErrorCode,
    ValidationCheck,
    ValidationError,
    ValidationStage,
)


class ErrorFactory:
    def __init__(self) -> None:
        self._count = 0

    def next_error_id(self) -> str:
        self._count += 1
        return f"err_{self._count:03d}"

    def build_error(
        self,
        *,
        code: ErrorCode,
        check: ValidationCheck,
        stage: ValidationStage,
        field_path: str,
        input_snapshot: dict[str, Any],
        expected: str,
        got: str,
        message: str,
        cause_type: str,
        ref: str | None = None,
        modification_ref: int | None = None,
        retryable: bool = False,
        conflict_kind: ConflictKind | None = None,
    ) -> ValidationError:
        return ValidationError(
            id=self.next_error_id(),
            code=code,
            check=check,
            stage=stage,
            field_path=field_path,
            input_snapshot=input_snapshot,
            expected=expected,
            got=got,
            ref=ref,
            modification_ref=modification_ref,
            message=message,
            cause_type=cause_type,
            retryable=retryable,
            conflict_kind=conflict_kind,
        )

    def sequence_error(
        self,
        *,
        code: ErrorCode,
        field_path: str,
        input_snapshot: dict[str, Any],
        expected: str,
        got: str,
        message: str,
    ) -> ValidationError:
        return self.build_error(
            code=code,
            check=ValidationCheck.VALIDATE_SEQUENCE,
            stage=ValidationStage.VALIDATE_SEQUENCE,
            field_path=field_path,
            input_snapshot=input_snapshot,
            expected=expected,
            got=got,
            message=message,
            cause_type="sequence_invalid",
        )

    def site_error(
        self,
        *,
        code: ErrorCode,
        token: str,
        modification_ref: int,
        expected: str,
        message: str,
        sequence_length: int,
        extra: dict[str, object] | None = None,
    ) -> ValidationError:
        snapshot: dict[str, Any] = {
            "site": token,
            "sequence_length": sequence_length,
        }
        if extra:
            snapshot.update(extra)
        return self.build_error(
            code=code,
            check=ValidationCheck.VALIDATE_MODIFICATION_SITES,
            stage=ValidationStage.VALIDATE_MODIFICATION_SITES,
            field_path=f"modifications[{modification_ref}].site",
            input_snapshot=snapshot,
            expected=expected,
            got=token,
            message=message,
            cause_type="site_invalid",
            modification_ref=modification_ref,
            conflict_kind="site_invalid",
        )

    def sequence_transform_error(
        self,
        *,
        modification_ref: int,
        detail: str | None,
        site: str,
        message: str,
    ) -> ValidationError:
        return self.build_error(
            code=ErrorCode.SEQUENCE_TRANSFORM_AMBIGUOUS,
            check=ValidationCheck.RESOLVE_SEQUENCE,
            stage=ValidationStage.RESOLVE_SEQUENCE,
            field_path=f"modifications[{modification_ref}].detail",
            input_snapshot={"detail": detail, "site": site},
            expected="explicit substitution such as Met->Nle or substitute D-Pro",
            got=detail or "",
            message=message,
            cause_type="sequence_transform_ambiguous",
            modification_ref=modification_ref,
        )

    def protecting_group_error(
        self,
        *,
        token: str,
        annotation: str | None,
        message: str,
        index: int,
    ) -> ValidationError:
        return self.build_error(
            code=ErrorCode.PROTECTING_GROUP_UNKNOWN,
            check=ValidationCheck.ASSIGN_PROTECTING_GROUPS,
            stage=ValidationStage.ASSIGN_PROTECTING_GROUPS,
            field_path=f"residue_annotations.X{index}",
            input_snapshot={"token": token, "annotation": annotation},
            expected="standard residue with a hard-coded Fmoc/tBu group",
            got=annotation or "X",
            message=message,
            cause_type="protecting_group_unknown",
        )

    def resin_error(
        self,
        *,
        parent_c_terminus: str,
        amidation_requested: bool,
        cyclization_anchor: bool,
        message: str,
    ) -> ValidationError:
        return self.build_error(
            code=ErrorCode.RESIN_UNSUPPORTED_TERMINUS,
            check=ValidationCheck.SELECT_RESIN,
            stage=ValidationStage.SELECT_RESIN,
            field_path="parent_c_terminus",
            input_snapshot={
                "parent_c_terminus": parent_c_terminus,
                "amidation_requested": amidation_requested,
                "cyclization_anchor_requested": cyclization_anchor,
            },
            expected="free_acid, amide, or a cyclization/amidation request",
            got=parent_c_terminus,
            message=message,
            cause_type="resin_unsupported",
        )
