"""Fail-closed validator for the bounded LIC-01B repository evidence contract."""

from __future__ import annotations

import argparse
import json
import re
import runpy
import sys
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import generate_license_review as review  # noqa: E402


class SchemaValidationError(RuntimeError):
    """Raised by the dependency-free validator for the committed v1 schema."""


def _json_equal(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _type_matches(value: object, expected: str) -> bool:
    return {
        "array": isinstance(value, list),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "object": isinstance(value, dict),
        "string": isinstance(value, str),
    }.get(expected, False)


def _schema_validate(
    value: object,
    schema: Mapping[str, object],
    root_schema: Mapping[str, object],
    path: str = "$",
) -> None:
    reference = schema.get("$ref")
    if reference is not None:
        if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
            raise SchemaValidationError(f"{path}: unsupported schema reference")
        name = reference.removeprefix("#/$defs/")
        definitions = root_schema.get("$defs")
        if not isinstance(definitions, dict) or not isinstance(definitions.get(name), dict):
            raise SchemaValidationError(f"{path}: unresolved schema reference {reference}")
        _schema_validate(value, definitions[name], root_schema, path)
        return

    expected_type = schema.get("type")
    if expected_type is not None:
        if not isinstance(expected_type, str) or not _type_matches(value, expected_type):
            raise SchemaValidationError(f"{path}: expected {expected_type}")
    if "const" in schema and not _json_equal(value, schema["const"]):
        raise SchemaValidationError(f"{path}: value differs from required constant")
    enumeration = schema.get("enum")
    if enumeration is not None:
        if not isinstance(enumeration, list) or not any(
            _json_equal(value, item) for item in enumeration
        ):
            raise SchemaValidationError(f"{path}: value is not in the allowed enumeration")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise SchemaValidationError(f"{path}: malformed object schema")
        missing = [key for key in required if key not in value]
        if missing:
            raise SchemaValidationError(f"{path}: missing required keys {missing}")
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise SchemaValidationError(f"{path}: unexpected keys {extra}")
        for key, item in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                _schema_validate(item, child_schema, root_schema, f"{path}.{key}")

    if isinstance(value, list):
        minimum_items = schema.get("minItems")
        if isinstance(minimum_items, int) and len(value) < minimum_items:
            raise SchemaValidationError(f"{path}: fewer than {minimum_items} items")
        if schema.get("uniqueItems") is True:
            serialized = [
                json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                for item in value
            ]
            if len(serialized) != len(set(serialized)):
                raise SchemaValidationError(f"{path}: duplicate array items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _schema_validate(item, item_schema, root_schema, f"{path}[{index}]")

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            raise SchemaValidationError(f"{path}: string is too short")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            raise SchemaValidationError(f"{path}: string does not match {pattern!r}")

    if isinstance(value, int) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, int) and value < minimum:
            raise SchemaValidationError(f"{path}: integer is below {minimum}")


_UNRESOLVED_SENTINELS = frozenset(
    {"n/a", "na", "noassertion", "none", "null", "tbd", "unknown"}
)


def _unresolved_values(value: object, path: str = "$") -> list[str]:
    errors: list[str] = []
    if value is None:
        errors.append(f"{path}: null is not allowed in the declared reviewed scope")
    elif isinstance(value, str):
        if not value:
            errors.append(f"{path}: empty string is not allowed")
        if value.strip().casefold() in _UNRESOLVED_SENTINELS:
            errors.append(f"{path}: unresolved sentinel is not allowed: {value!r}")
    elif isinstance(value, dict):
        for key, item in value.items():
            errors.extend(_unresolved_values(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_unresolved_values(item, f"{path}[{index}]"))
    return errors


def _expression_metrics(
    root: Path,
    contract: Mapping[str, object],
) -> tuple[int, int, list[str]]:
    errors: list[str] = []
    try:
        inputs = review._strict_json(review.INPUT_PATH, root=root)
    except (review.LicenseReviewError, OSError, UnicodeError) as exc:
        return 0, 0, [f"SPDX definition input could not be read: {exc}"]
    definitions = inputs.get("license_ref_components")
    if not isinstance(definitions, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in definitions.items()
    ):
        return 0, 0, ["SPDX LicenseRef definitions are malformed"]
    components = contract.get("components")
    if not isinstance(components, list):
        return 0, 0, ["SPDX component expressions are missing"]
    valid = 0
    invalid = 0
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            invalid += 1
            errors.append(f"components[{index}]: SPDX component record is malformed")
            continue
        expression = component.get("evidence_expression")
        component_id = component.get("id")
        if not isinstance(expression, str):
            invalid += 1
            errors.append(
                f"components[{index}].evidence_expression: SPDX expression is missing"
            )
            continue
        try:
            review.validate_evidence_expression(
                expression,
                defined_license_refs=frozenset(definitions),
            )
        except review.LicenseReviewError as exc:
            invalid += 1
            errors.append(f"{component_id}: {exc}")
        else:
            valid += 1
    return valid, invalid, errors


def _packaging_errors(root: Path) -> list[str]:
    errors: list[str] = []
    hook_path = root / review.PACKAGING_HOOK_PATH
    builder_path = root / review.PACKAGE_BUILDER_PATH
    spec_path = root / "packaging/mclab.spec"
    notice_path = root / review.NOTICE_PATH
    try:
        namespace = runpy.run_path(str(hook_path))
    except (OSError, RuntimeError, SyntaxError) as exc:
        return [f"packaging hook could not be evaluated: {exc}"]
    expected = [(str(notice_path), ".")]
    if namespace.get("datas") != expected:
        errors.append("packaging hook must bundle only THIRD_PARTY_NOTICES.md")
    try:
        spec_source = spec_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"packaging spec could not be read: {exc}")
    else:
        if 'hookspath=[str(ROOT / "packaging/hooks")]' not in spec_source:
            errors.append("packaging spec does not activate the reviewed custom hook path")
    try:
        builder = runpy.run_path(str(builder_path))
    except (OSError, RuntimeError, SyntaxError) as exc:
        errors.append(f"package builder could not be evaluated: {exc}")
    else:
        if (
            builder.get("THIRD_PARTY_NOTICES_NAME") != review.NOTICE_PATH
            or builder.get("EVIDENCE_SCHEMA") != "mclab.package-metrics.v2"
            or not callable(builder.get("_atomic_replace_third_party_notices"))
            or not callable(builder.get("_third_party_notices_evidence"))
        ):
            errors.append(
                "package builder must copy and attest THIRD_PARTY_NOTICES.md "
                "at the bundle root"
            )
    return errors


def validate(root: Path = ROOT) -> tuple[dict[str, int], list[str]]:
    """Return bounded coverage metrics and all fail-closed validation errors."""

    errors: list[str] = []
    try:
        contract, generation_errors = review.check_committed(root)
        errors.extend(generation_errors)
    except (review.LicenseReviewError, OSError, UnicodeError) as exc:
        return {}, [f"deterministic generation failed: {exc}"]
    try:
        schema_payload = (root / review.SCHEMA_PATH).read_text(encoding="utf-8")
        schema = json.loads(schema_payload)
        if not isinstance(schema, dict):
            raise SchemaValidationError("schema root must be an object")
        _schema_validate(contract, schema, schema)
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaValidationError) as exc:
        errors.append(f"v1 schema validation failed: {exc}")
    errors.extend(_unresolved_values(contract))
    errors.extend(_packaging_errors(root))
    valid_expressions, unresolved_expressions, expression_errors = _expression_metrics(
        root, contract
    )
    errors.extend(expression_errors)

    contract_record = contract.get("contract")
    if contract_record != {
        "blockers": list(review.BLOCKERS),
        "declared_scope": (
            "repository-known Python package-profile inputs and reviewed "
            "static bundle inputs only"
        ),
        **review.EXPECTED_GOVERNANCE,
        "id": "LIC-01B",
        "purpose": (
            "deterministic repository evidence corpus; not legal approval "
            "or distribution closure"
        ),
        "status": "bounded-candidate-evidence-only",
    }:
        errors.append("LIC-01B open governance contract drift")
    coverage = contract.get("coverage")
    if not isinstance(coverage, dict):
        errors.append("LIC-01B coverage record is missing")
        return {}, errors
    metrics = {
        key: int(value)
        for key, value in coverage.items()
        if isinstance(key, str) and isinstance(value, int)
    }
    expected_metrics = {
        "component_count": 53,
        "evidence_expression_count": valid_expressions,
        "license_text_complete_count": 51,
        "license_text_partial_count": 2,
        "notice_text_captured_component_count": 1,
        "python_component_count": 50,
        "source_url_count": 53,
        "static_component_count": 3,
        "unknown_value_count": unresolved_expressions,
    }
    if metrics != expected_metrics:
        errors.append("LIC-01B bounded coverage metrics drift")
    return metrics, errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    metrics, errors = validate()
    if errors:
        for error in errors:
            print(f"LIC-01B policy error: {error}", file=sys.stderr)
        return 1
    print(
        "LIC-01B reviewed repository evidence policy: PASS "
        f"({metrics['component_count']} components, "
        f"{metrics['unknown_value_count']} UNKNOWN values; aggregate/G3 open)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
