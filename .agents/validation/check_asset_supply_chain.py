"""Enforce one pinned Menagerie acquisition path across scripts and CI."""

from __future__ import annotations

import ast
import re
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_PATH = Path("scripts/bootstrap_and_run.py")
ASSET_MODULE_PATH = Path("src/mclab/application/assets.py")
ASSET_VERIFICATION_MODULE = "mclab.application._asset_verification"
ASSET_VERIFICATION_PATH = Path("src/mclab/application/_asset_verification.py")
ASSET_MANIFEST_PATH = Path("src/mclab/application/panda_runtime_manifest.py")
CLI_PATH = Path("src/mclab/cli.py")
WORKFLOW_PATHS = (
    Path(".github/workflows/ci.yml"),
    Path(".github/workflows/desktop.yml"),
)
ASSET_LAUNCHERS = (
    Path("run_mclab.cmd"),
    Path("run_all_batches.cmd"),
    Path("run_batch_lab04.cmd"),
    Path("run_batch_lab04_cartesian.cmd"),
    Path("run_lab04.cmd"),
    Path("run_lab04_cartesian_interactive.cmd"),
    Path("run_lab04_interactive.cmd"),
    Path("run_lab04_wall_interactive.cmd"),
)
WORKFLOW_ASSET_STEP = (
    "      - name: Install and verify pinned Panda assets\n"
    "        run: |\n"
    "          python -m mclab assets install\n"
    "          python -m mclab assets verify\n"
)
WORKFLOW_POLICY_STEP = (
    "      - name: Asset supply-chain policy\n"
    "        run: python .agents/validation/check_asset_supply_chain.py\n"
)
WORKFLOW_ASSET_STEP_NAME = "Install and verify pinned Panda assets"
LAUNCHER_VERIFY = '".venv\\Scripts\\python.exe" -m mclab assets verify >nul 2>&1'
LAUNCHER_FALLBACK = f"{LAUNCHER_VERIFY}\nif errorlevel 1 goto setup"
MUTABLE_MENAGERIE_TOKENS = (
    "github.com/google-deepmind/mujoco_menagerie.git",
    "sparse-checkout set franka_emika_panda",
)
ACQUISITION_SCRIPT_SUFFIXES = frozenset(
    {".bat", ".cmd", ".command", ".ps1", ".py", ".sh", ".spec", ".yaml", ".yml"}
)
ACQUISITION_SCAN_DIRECTORIES = (".github", "packaging", "scripts", "src", "tools")
FULL_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
APPROVED_MENAGERIE_COMMIT = "71f066ad0be9cd271f7ed58c030243ef157af9f4"
APPROVED_MENAGERIE_ARCHIVE_SHA256 = (
    "000b9f51abb404efb1de2b88b3c738674c472a85b6c4143168859abc4c98d423"
)
APPROVED_RUNTIME_MANIFEST_SCHEMA = 1
APPROVED_RUNTIME_FILE_COUNT = 72
APPROVED_RUNTIME_TOTAL_BYTES = 34_333_936
APPROVED_CRITICAL_RUNTIME_MEMBERS = (
    "LICENSE",
    "hand.xml",
    "panda.xml",
    "panda_nohand.xml",
    "scene.xml",
)


def _read(root: Path, relative: Path) -> str:
    return (root / relative).read_text(encoding="utf-8").replace("\r\n", "\n")


def _python_tree(root: Path, relative: Path) -> tuple[ast.Module | None, list[str]]:
    try:
        return ast.parse(_read(root, relative), filename=str(relative)), []
    except (OSError, SyntaxError) as exc:
        return None, [f"{relative}: could not parse Python: {exc}"]


def _literal_assignments(tree: ast.Module) -> dict[str, Any]:
    assignments: dict[str, Any] = {}
    for node in tree.body:
        name: str | None = None
        value: ast.expr | None = None
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            name = node.targets[0].id
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            value = node.value
        if name is None or value is None:
            continue
        try:
            assignments[name] = ast.literal_eval(value)
        except (ValueError, TypeError):
            continue
    return assignments


def _assignment_expressions(tree: ast.Module) -> dict[str, ast.expr]:
    assignments: dict[str, ast.expr] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            assignments[node.targets[0].id] = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            assignments[node.target.id] = node.value
    return assignments


def _canonical_asset_errors(root: Path) -> list[str]:
    errors: list[str] = []
    assets_tree, parse_errors = _python_tree(root, ASSET_MODULE_PATH)
    errors.extend(parse_errors)
    manifest_tree, parse_errors = _python_tree(root, ASSET_MANIFEST_PATH)
    errors.extend(parse_errors)
    cli_tree, parse_errors = _python_tree(root, CLI_PATH)
    errors.extend(parse_errors)
    if assets_tree is None or manifest_tree is None or cli_tree is None:
        return errors

    assets = _literal_assignments(assets_tree)
    asset_expressions = _assignment_expressions(assets_tree)
    manifest_values = _literal_assignments(manifest_tree)
    manifest_commit = manifest_values.get("PANDA_RUNTIME_MENAGERIE_COMMIT")
    manifest_archive_sha = manifest_values.get("PANDA_RUNTIME_ARCHIVE_SHA256")
    commit = assets.get("MENAGERIE_COMMIT")
    if commit is None:
        expression = asset_expressions.get("MENAGERIE_COMMIT")
        if isinstance(expression, ast.Name) and expression.id == "PANDA_RUNTIME_MENAGERIE_COMMIT":
            commit = manifest_commit
    archive_sha = assets.get("MENAGERIE_ARCHIVE_SHA256")
    if archive_sha is None:
        expression = asset_expressions.get("MENAGERIE_ARCHIVE_SHA256")
        if isinstance(expression, ast.Name) and expression.id == "PANDA_RUNTIME_ARCHIVE_SHA256":
            archive_sha = manifest_archive_sha
    if not isinstance(commit, str) or FULL_COMMIT_RE.fullmatch(commit) is None:
        errors.append(f"{ASSET_MODULE_PATH}: MENAGERIE_COMMIT must be a full 40-hex SHA")
    elif commit != APPROVED_MENAGERIE_COMMIT:
        errors.append(
            f"{ASSET_MODULE_PATH}: MENAGERIE_COMMIT must equal the approved provenance pin"
        )
    if not isinstance(archive_sha, str) or SHA256_RE.fullmatch(archive_sha) is None:
        errors.append(f"{ASSET_MODULE_PATH}: MENAGERIE_ARCHIVE_SHA256 must be a 64-hex SHA-256")
    elif archive_sha != APPROVED_MENAGERIE_ARCHIVE_SHA256:
        errors.append(
            f"{ASSET_MODULE_PATH}: MENAGERIE_ARCHIVE_SHA256 must equal the approved archive digest"
        )

    function_nodes = {
        node.name: node
        for node in assets_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    class_names = {node.name for node in assets_tree.body if isinstance(node, ast.ClassDef)}
    imported_verification_names = {
        alias.asname or alias.name
        for node in assets_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == ASSET_VERIFICATION_MODULE
        for alias in node.names
    }
    helper_class_names: set[str] = set()
    if imported_verification_names:
        helper_tree, helper_errors = _python_tree(root, ASSET_VERIFICATION_PATH)
        errors.extend(helper_errors)
        if helper_tree is not None:
            helper_class_names = {
                node.name for node in helper_tree.body if isinstance(node, ast.ClassDef)
            }
    if "install_assets" not in function_nodes:
        errors.append(f"{ASSET_MODULE_PATH}: install_assets API is missing")
    verify = function_nodes.get("verify_assets")
    if verify is None:
        errors.append(f"{ASSET_MODULE_PATH}: verify_assets API is missing")
    elif not verify.args.args or verify.args.args[0].arg != "root" or not verify.args.defaults:
        errors.append(f"{ASSET_MODULE_PATH}: verify_assets must expose a defaulted root")
    for class_name in ("AssetVerification", "AssetVerificationError", "AssetSafetyError"):
        defined_here = class_name in class_names
        imported_from_helper = (
            class_name in imported_verification_names and class_name in helper_class_names
        )
        if not defined_here and not imported_from_helper:
            errors.append(f"{ASSET_MODULE_PATH}: {class_name} is missing")

    schema = manifest_values.get("PANDA_RUNTIME_MANIFEST_SCHEMA")
    manifest = manifest_values.get("PANDA_RUNTIME_MANIFEST")
    file_count = manifest_values.get("PANDA_RUNTIME_FILE_COUNT")
    total_bytes = manifest_values.get("PANDA_RUNTIME_TOTAL_BYTES")
    if (
        not isinstance(schema, int)
        or isinstance(schema, bool)
        or schema != APPROVED_RUNTIME_MANIFEST_SCHEMA
    ):
        errors.append(
            f"{ASSET_MANIFEST_PATH}: manifest schema must equal approved integer "
            f"{APPROVED_RUNTIME_MANIFEST_SCHEMA}"
        )
    if manifest_commit != commit:
        errors.append(f"{ASSET_MANIFEST_PATH}: manifest commit does not match installer pin")
    if manifest_archive_sha != archive_sha:
        errors.append(f"{ASSET_MANIFEST_PATH}: manifest archive SHA does not match installer pin")

    valid_entries: list[tuple[str, int, str]] = []
    if not isinstance(manifest, tuple) or not manifest:
        errors.append(f"{ASSET_MANIFEST_PATH}: runtime manifest must be a nonempty tuple")
    else:
        for index, entry in enumerate(manifest):
            if not isinstance(entry, tuple) or len(entry) != 3:
                errors.append(
                    f"{ASSET_MANIFEST_PATH}: manifest entry {index} must be a path/size/SHA tuple"
                )
                continue
            path, size, digest = entry
            path_is_safe = (
                isinstance(path, str)
                and bool(path)
                and "\\" not in path
                and not PurePosixPath(path).is_absolute()
                and ".." not in PurePosixPath(path).parts
                and PurePosixPath(path).as_posix() == path
            )
            if not path_is_safe:
                errors.append(f"{ASSET_MANIFEST_PATH}: manifest entry {index} has unsafe path")
                continue
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                errors.append(f"{ASSET_MANIFEST_PATH}: manifest entry {path} has invalid size")
                continue
            if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
                errors.append(f"{ASSET_MANIFEST_PATH}: manifest entry {path} has invalid SHA-256")
                continue
            valid_entries.append((path, size, digest))

    paths = [entry[0] for entry in valid_entries]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        errors.append(f"{ASSET_MANIFEST_PATH}: runtime manifest paths must be sorted and unique")
    if len(paths) != len({path.casefold() for path in paths}):
        errors.append(
            f"{ASSET_MANIFEST_PATH}: runtime manifest paths must be case-insensitively unique"
        )
    for required in APPROVED_CRITICAL_RUNTIME_MEMBERS:
        if required not in paths:
            errors.append(f"{ASSET_MANIFEST_PATH}: runtime manifest is missing {required}")
    if file_count != len(valid_entries):
        errors.append(f"{ASSET_MANIFEST_PATH}: runtime file count does not match entries")
    if file_count != APPROVED_RUNTIME_FILE_COUNT:
        errors.append(
            f"{ASSET_MANIFEST_PATH}: runtime file count must equal approved count "
            f"{APPROVED_RUNTIME_FILE_COUNT}"
        )
    if total_bytes != sum(entry[1] for entry in valid_entries) or not total_bytes:
        errors.append(f"{ASSET_MANIFEST_PATH}: runtime byte total does not match entries")
    if total_bytes != APPROVED_RUNTIME_TOTAL_BYTES:
        errors.append(
            f"{ASSET_MANIFEST_PATH}: runtime byte total must equal approved total "
            f"{APPROVED_RUNTIME_TOTAL_BYTES}"
        )

    parser_commands = {
        call.args[0].value
        for call in ast.walk(cli_tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "add_parser"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    }
    called_names = {
        call.func.id
        for call in ast.walk(cli_tree)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }
    for command in ("install", "verify"):
        if command not in parser_commands:
            errors.append(f"{CLI_PATH}: assets {command} parser is missing")
    for function_name in ("install_assets", "verify_assets"):
        if function_name not in called_names:
            errors.append(f"{CLI_PATH}: {function_name} is not dispatched")
    return errors


def _is_canonical_bootstrap_delegate(statement: ast.stmt) -> bool:
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return False
    call = statement.value
    if (
        not isinstance(call.func, ast.Name)
        or call.func.id != "run"
        or call.keywords
        or len(call.args) != 1
        or not isinstance(call.args[0], ast.List)
    ):
        return False
    elements = call.args[0].elts
    if len(elements) != 5:
        return False
    python_expr = elements[0]
    if (
        not isinstance(python_expr, ast.Call)
        or not isinstance(python_expr.func, ast.Name)
        or python_expr.func.id != "str"
        or python_expr.keywords
        or len(python_expr.args) != 1
        or not isinstance(python_expr.args[0], ast.Name)
        or python_expr.args[0].id != "VENV_PYTHON"
    ):
        return False
    expected = ("-m", "mclab", "assets", "install")
    return all(
        isinstance(element, ast.Constant) and element.value == value
        for element, value in zip(elements[1:], expected, strict=True)
    )


def _bootstrap_errors(root: Path) -> list[str]:
    text = _read(root, BOOTSTRAP_PATH)
    errors: list[str] = []
    try:
        tree = ast.parse(text, filename=str(BOOTSTRAP_PATH))
    except SyntaxError as exc:
        return [*errors, f"{BOOTSTRAP_PATH}: could not parse Python: {exc}"]
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "ensure_menagerie"
    ]
    if len(functions) != 1:
        errors.append(f"{BOOTSTRAP_PATH}: expected exactly one ensure_menagerie function")
    elif len(functions[0].body) != 1 or not _is_canonical_bootstrap_delegate(functions[0].body[0]):
        errors.append(
            f"{BOOTSTRAP_PATH}: ensure_menagerie must delegate only to "
            "<venv-python> -m mclab assets install"
        )
    return errors


def _acquisition_surface_paths(root: Path) -> tuple[Path, ...]:
    """Return executable acquisition surfaces, excluding canonical core and docs."""

    absolute_paths: set[Path] = set()
    for directory_name in ACQUISITION_SCAN_DIRECTORIES:
        directory = root / directory_name
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if directory_name in {"scripts", "tools"} or (
                path.suffix.lower() in ACQUISITION_SCRIPT_SUFFIXES
            ):
                absolute_paths.add(path)
    absolute_paths.update(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in ACQUISITION_SCRIPT_SUFFIXES
    )
    absolute_paths.discard(root / ASSET_MODULE_PATH)
    return tuple(sorted((path.relative_to(root) for path in absolute_paths), key=str))


def _acquisition_surface_errors(root: Path) -> list[str]:
    errors: list[str] = []
    menagerie_marker = re.compile(
        r"(?:mujoco[_-]menagerie|franka[_-]emika[_-]panda)",
        flags=re.IGNORECASE,
    )
    git_clone = re.compile(r"\bgit(?:\.exe)?\b.*?\bclone\b", flags=re.IGNORECASE | re.DOTALL)
    sparse_checkout = re.compile(
        r"\bsparse[\s_-]*checkout\b",
        flags=re.IGNORECASE,
    )
    network_acquisition = re.compile(
        r"\b(?:curl|wget|invoke-(?:webrequest|restmethod)|iwr|irm|start-bitstransfer|"
        r"urlopen|urlretrieve|requests\s*\.\s*(?:get|request)|"
        r"httpx\s*\.\s*(?:get|stream)|gh\s+api)\b",
        flags=re.IGNORECASE,
    )
    for path in _acquisition_surface_paths(root):
        text = _read(root, path)
        for token in MUTABLE_MENAGERIE_TOKENS:
            if token.lower() in text.lower():
                errors.append(f"{path}: mutable Menagerie acquisition token remains: {token}")
        if menagerie_marker.search(text) is None:
            continue
        if git_clone.search(text) is not None:
            errors.append(f"{path}: mutable Menagerie git clone is not allowed")
        if sparse_checkout.search(text) is not None:
            errors.append(f"{path}: mutable Menagerie sparse checkout is not allowed")
        if network_acquisition.search(text) is not None:
            errors.append(f"{path}: direct Menagerie download bypasses the canonical installer")
    return errors


def _workflow_step_blocks(text: str) -> list[str]:
    lines = text.splitlines(keepends=True)
    starts: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)-\s+(?:name|uses):", line)
        if match:
            starts.append((index, len(match.group(1))))
    blocks: list[str] = []
    for position, (start, indent) in enumerate(starts):
        end = len(lines)
        for candidate, candidate_indent in starts[position + 1 :]:
            if candidate_indent == indent:
                end = candidate
                break
        blocks.append("".join(lines[start:end]))
    return blocks


def _yaml_scalar(value: str) -> str:
    scalar = value.split("#", 1)[0].strip()
    if scalar.startswith("-"):
        scalar = scalar[1:].strip()
    if len(scalar) >= 2 and scalar[0] == scalar[-1] and scalar[0] in {"'", '"'}:
        scalar = scalar[1:-1].strip()
    return scalar.replace("\\", "/")


def _is_exact_workflow_asset_step(block: str) -> bool:
    return block.strip() == WORKFLOW_ASSET_STEP.strip()


def _explicit_cache_errors(root: Path) -> list[str]:
    errors: list[str] = []
    github_root = root / ".github"
    if not github_root.exists():
        return errors
    for path in sorted((*github_root.rglob("*.yml"), *github_root.rglob("*.yaml"))):
        text = path.read_text(encoding="utf-8")
        if re.search(r"actions/cache(?:/[^@\s\"']+)?@", text, flags=re.IGNORECASE):
            errors.append(
                f"{path.relative_to(root)}: extracted Menagerie trees must not be cached; "
                "explicit actions/cache steps are forbidden"
            )
    return errors


def _workflow_errors(root: Path) -> list[str]:
    errors: list[str] = []
    order_contract = {
        WORKFLOW_PATHS[0]: ("Install package with dev tools", "Ruff lint"),
        WORKFLOW_PATHS[1]: (
            "Install desktop, test, and packaging dependencies",
            "Windows compatibility launcher repair matrix",
        ),
    }
    workflow_root = root / ".github" / "workflows"
    all_workflows = sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))
    for absolute_path in all_workflows:
        path = absolute_path.relative_to(root)
        text = _read(root, path)
        if path not in WORKFLOW_PATHS:
            continue
        asset_blocks = [
            block
            for block in _workflow_step_blocks(text)
            if "python -m mclab assets install" in block or "python -m mclab assets verify" in block
        ]
        if len(asset_blocks) != 1 or not _is_exact_workflow_asset_step(asset_blocks[0]):
            errors.append(
                f"{path}: expected one exact unconditional canonical assets install+verify "
                "step without if, continue-on-error, or shell weakening"
            )
        elif weakening := _asset_job_weakening(text, asset_blocks[0]):
            errors.append(
                f"{path}: asset install+verify job must be unconditional "
                f"(remove {', '.join(weakening)})"
            )
        if text.count("python -m mclab assets install") != 1:
            errors.append(f"{path}: expected exactly one canonical assets install command")
        if text.count("python -m mclab assets verify") != 1:
            errors.append(f"{path}: expected exactly one canonical assets verify command")
        if len(asset_blocks) == 1 and _is_exact_workflow_asset_step(asset_blocks[0]):
            before, after = order_contract[path]
            asset_job = _workflow_job_block(text, asset_blocks[0])
            step_names = (
                [_workflow_step_name(block) for block in _workflow_step_blocks(asset_job)]
                if asset_job is not None
                else []
            )
            required_names = (before, WORKFLOW_ASSET_STEP_NAME, after)
            if any(step_names.count(name) != 1 for name in required_names):
                errors.append(f"{path}: asset verification order anchors must be exact and unique")
            elif not (
                step_names.index(before)
                < step_names.index(WORKFLOW_ASSET_STEP_NAME)
                < step_names.index(after)
            ):
                errors.append(f"{path}: asset verification step is outside its required order")

    ci_text = _read(root, WORKFLOW_PATHS[0])
    if ci_text.count(WORKFLOW_POLICY_STEP) != 1:
        errors.append(f"{WORKFLOW_PATHS[0]}: expected one asset supply-chain policy gate")
    return errors


def _workflow_step_name(block: str) -> str | None:
    first_line = block.splitlines()[0]
    match = re.match(r"^\s*-\s+name\s*:\s*(.*)$", first_line)
    return _yaml_scalar(match.group(1)) if match is not None else None


def _asset_job_weakening(workflow: str, asset_block: str) -> tuple[str, ...]:
    """Return job/workflow controls that can skip or neutralize asset commands."""

    job = _workflow_job_block(workflow, asset_block)
    if job is None:
        return ("unresolved job",)
    weakening = [
        key
        for key in ("if", "continue-on-error", "needs", "defaults")
        if re.search(rf"(?m)^    [\"']?{re.escape(key)}[\"']?\s*:", job)
    ]
    if re.search(r"(?m)^[\"']?defaults[\"']?\s*:", workflow):
        weakening.append("workflow defaults")
    return tuple(weakening)


def _workflow_job_block(workflow: str, asset_block: str) -> str | None:
    asset_offset = workflow.index(asset_block)
    headers = list(re.finditer(r"(?m)^  [A-Za-z0-9_-]+:\s*(?:#.*)?$", workflow))
    containing = [header for header in headers if header.start() < asset_offset]
    if not containing:
        return None
    job_start = containing[-1].start()
    following = [header.start() for header in headers if header.start() > asset_offset]
    job_end = min(following, default=len(workflow))
    return workflow[job_start:job_end]


def _launcher_errors(root: Path) -> list[str]:
    errors: list[str] = []
    discovered = {
        path.relative_to(root)
        for path in root.iterdir()
        if path.is_file()
        and path.suffix.casefold() in {".bat", ".cmd"}
        and _is_panda_capable_launcher(path)
    }
    for path in sorted(set(ASSET_LAUNCHERS) | discovered, key=str):
        text = _read(root, path)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        verify_indices = [index for index, line in enumerate(lines) if line == LAUNCHER_VERIFY]
        if len(verify_indices) != 1:
            errors.append(f"{path}: expected exactly one canonical assets verify probe")
        if 'franka_emika_panda\\scene.xml" goto setup' in text.lower():
            errors.append(f"{path}: scene.xml existence must not bypass asset verification")
        if len(verify_indices) != 1:
            continue
        verify_index = verify_indices[0]
        expected_block = [LAUNCHER_VERIFY, "if errorlevel 1 goto setup", "goto run"]
        if lines[verify_index : verify_index + 3] != expected_block:
            errors.append(f"{path}: asset verification failure must enter :setup")
        before_probe = lines[:verify_index]
        early_run = any(
            re.search(r"\b(?:goto|call)\s+:?run\b", line, flags=re.IGNORECASE)
            for line in before_probe
            if not line.lower().startswith(("rem ", "::"))
        ) or any(line.lower() == ":run" for line in before_probe)
        early_run = early_run or _contains_panda_workload("\n".join(before_probe))
        if early_run:
            errors.append(f"{path}: asset verification must run before the workload")
    return errors


def _is_panda_capable_launcher(path: Path) -> bool:
    text = path.read_text(encoding="utf-8").casefold()
    return "lab04" in path.name.casefold() or _contains_panda_workload(text)


def _contains_panda_workload(text: str) -> bool:
    text = text.casefold()
    return (
        "-m mclab menu" in text
        or "-m mclab batch all" in text
        or "-m mclab run lab04" in text
        or "-m mclab batch lab04" in text
    )


def asset_supply_chain_errors(root: Path = ROOT) -> list[str]:
    """Return deterministic policy violations for controlled acquisition paths."""

    return [
        *_canonical_asset_errors(root),
        *_bootstrap_errors(root),
        *_acquisition_surface_errors(root),
        *_explicit_cache_errors(root),
        *_workflow_errors(root),
        *_launcher_errors(root),
    ]


def main() -> int:
    errors = asset_supply_chain_errors()
    if errors:
        print("Asset supply-chain policy: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "Asset supply-chain policy: PASS "
        "(approved source/archive pins, schema 1, 72 files/34333936 bytes, "
        "5 critical runtime members, "
        "install+verify CLI, 1 bootstrap delegate, 2 workflow install+verify steps, "
        "8 launcher verify probes, 0 extracted-tree caches, 0 mutable clones)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
