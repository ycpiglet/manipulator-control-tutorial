from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / ".agents" / "validation" / "check_asset_supply_chain.py"
SPEC = importlib.util.spec_from_file_location("check_asset_supply_chain", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


class AssetSupplyChainTests(unittest.TestCase):
    def test_repository_has_one_canonical_menagerie_acquisition_path(self) -> None:
        self.assertEqual(CHECKER.asset_supply_chain_errors(), [])

    def test_mutable_bootstrap_clone_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            bootstrap = root / CHECKER.BOOTSTRAP_PATH
            bootstrap.write_text(
                bootstrap.read_text(encoding="utf-8").replace(
                    '    run([str(VENV_PYTHON), "-m", "mclab", "assets", "install"])',
                    (
                        '    run(["git", "clone", '
                        '"https://github.com/google-deepmind/mujoco_menagerie.git"])'
                    ),
                ),
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("mutable Menagerie acquisition token" in error for error in errors))
        self.assertTrue(any("must delegate only" in error for error in errors))

    def test_extracted_tree_cache_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            workflow = root / CHECKER.WORKFLOW_PATHS[0]
            cache_step = (
                "      - name: Cache extracted Panda tree\n"
                "        uses: actions/cache@" + "a" * 40 + "\n"
                "        with:\n"
                "          path: third_party/mujoco_menagerie/franka_emika_panda\n\n"
            )
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    CHECKER.WORKFLOW_ASSET_STEP,
                    cache_step + CHECKER.WORKFLOW_ASSET_STEP,
                ),
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(
            any("extracted Menagerie trees must not be cached" in error for error in errors)
        )

    def test_actions_cache_save_variant_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            workflow = root / CHECKER.WORKFLOW_PATHS[0]
            cache_step = (
                "      - name: Save extracted Panda tree\n"
                "        uses: actions/cache/save@" + "a" * 40 + "\n"
                "        with:\n"
                "          path: third_party/mujoco_menagerie/franka_emika_panda\n\n"
            )
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    CHECKER.WORKFLOW_ASSET_STEP,
                    cache_step + CHECKER.WORKFLOW_ASSET_STEP,
                ),
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(
            any("extracted Menagerie trees must not be cached" in error for error in errors)
        )

    def test_globbed_extracted_tree_cache_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            workflow = root / CHECKER.WORKFLOW_PATHS[0]
            cache_step = (
                "      - name: Cache third-party tree\n"
                "        uses: actions/cache@" + "a" * 40 + "\n"
                "        with:\n"
                "          path: third_party/**\n\n"
            )
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    CHECKER.WORKFLOW_ASSET_STEP,
                    cache_step + CHECKER.WORKFLOW_ASSET_STEP,
                ),
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(
            any("extracted Menagerie trees must not be cached" in error for error in errors)
        )

    def test_ancestor_cache_path_is_rejected(self) -> None:
        for cache_path in (
            "third_party",
            "./third_party",
            "${{ github.workspace }}/third_party",
        ):
            with self.subTest(cache_path=cache_path), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_contract_fixture(root)
                workflow = root / CHECKER.WORKFLOW_PATHS[0]
                cache_step = (
                    "      - name: Cache extracted dependency parent\n"
                    "        uses: actions/cache@" + "a" * 40 + "\n"
                    "        with:\n"
                    f"          path: {cache_path}\n\n"
                )
                workflow.write_text(
                    workflow.read_text(encoding="utf-8").replace(
                        CHECKER.WORKFLOW_ASSET_STEP,
                        cache_step + CHECKER.WORKFLOW_ASSET_STEP,
                    ),
                    encoding="utf-8",
                )

                errors = CHECKER.asset_supply_chain_errors(root)

            self.assertTrue(
                any("extracted Menagerie trees must not be cached" in error for error in errors)
            )

    def test_mutable_clone_in_an_additional_workflow_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            rogue = root / ".github" / "workflows" / "rogue.yml"
            rogue.write_text(
                "jobs:\n"
                "  fetch:\n"
                "    steps:\n"
                "      - name: Mutable fetch\n"
                "        run: git clone https://example.invalid/mujoco_menagerie.git\n",
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("mutable Menagerie git clone" in error for error in errors))

    def test_mutable_clone_and_sparse_checkout_in_rogue_script_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            rogue = root / "scripts" / "rogue_fetch.py"
            rogue.write_text(
                "import subprocess\n\n"
                "subprocess.run(\n"
                '    ["git", "clone", "https://example.invalid/mujoco-menagerie.git"]\n'
                ")\n"
                'subprocess.run(["git", "sparse-checkout", "set", '
                '"franka-emika-panda"])\n',
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        rogue_errors = [error for error in errors if "scripts/rogue_fetch.py" in error]
        self.assertTrue(any("mutable Menagerie git clone" in error for error in rogue_errors))
        self.assertTrue(any("mutable Menagerie sparse checkout" in error for error in rogue_errors))

    def test_mutable_clone_in_cross_platform_root_launcher_is_rejected(self) -> None:
        for launcher_name in ("start_here.sh", "START_HERE.command"):
            with self.subTest(launcher_name=launcher_name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_contract_fixture(root)
                launcher = root / launcher_name
                launcher.write_text(
                    "#!/bin/sh\ngit clone https://example.invalid/mujoco_menagerie.git\n",
                    encoding="utf-8",
                )

                errors = CHECKER.asset_supply_chain_errors(root)

            self.assertTrue(
                any(
                    launcher_name in error and "mutable Menagerie git clone" in error
                    for error in errors
                )
            )

    def test_mutable_archive_download_in_root_script_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            launcher = root / "rogue.sh"
            launcher.write_text(
                "#!/bin/sh\n"
                "curl -L https://github.com/google-deepmind/"
                "mujoco_menagerie/archive/main.tar.gz\n",
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(
            any(
                "rogue.sh" in error and "bypasses the canonical installer" in error
                for error in errors
            )
        )

    def test_cache_condition_cannot_bypass_install_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            workflow = root / CHECKER.WORKFLOW_PATHS[1]
            conditional = CHECKER.WORKFLOW_ASSET_STEP.replace(
                "        run: |\n",
                "        if: steps.panda-cache.outputs.cache-hit != 'true'\n        run: |\n",
            )
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    CHECKER.WORKFLOW_ASSET_STEP,
                    conditional,
                ),
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("unconditional canonical" in error for error in errors))

    def test_workflow_step_weakening_is_rejected(self) -> None:
        weakened_steps = {
            "if": CHECKER.WORKFLOW_ASSET_STEP.replace(
                "        run: |\n",
                "        if: success()\n        run: |\n",
            ),
            "continue-on-error": CHECKER.WORKFLOW_ASSET_STEP.replace(
                "        run: |\n",
                "        continue-on-error: true\n        run: |\n",
            ),
            "shell": CHECKER.WORKFLOW_ASSET_STEP.replace(
                "          python -m mclab assets verify\n",
                "          python -m mclab assets verify || true\n",
            ),
        }
        for weakening, weakened_step in weakened_steps.items():
            with self.subTest(weakening=weakening), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_contract_fixture(root)
                workflow = root / CHECKER.WORKFLOW_PATHS[0]
                workflow.write_text(
                    workflow.read_text(encoding="utf-8").replace(
                        CHECKER.WORKFLOW_ASSET_STEP,
                        weakened_step,
                    ),
                    encoding="utf-8",
                )

                errors = CHECKER.asset_supply_chain_errors(root)

            self.assertTrue(any("exact unconditional canonical" in error for error in errors))

    def test_job_level_condition_cannot_bypass_install_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            workflow = root / CHECKER.WORKFLOW_PATHS[0]
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "  simulator:\n    steps:\n",
                    "  simulator:\n    if: false\n    steps:\n",
                ),
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("asset install+verify job must be unconditional" in e for e in errors))

    def test_scene_existence_cannot_replace_launcher_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            launcher = root / CHECKER.ASSET_LAUNCHERS[0]
            launcher.write_text(
                launcher.read_text(encoding="utf-8").replace(
                    CHECKER.LAUNCHER_FALLBACK,
                    (
                        'if not exist "third_party\\mujoco_menagerie\\'
                        'franka_emika_panda\\scene.xml" goto setup'
                    ),
                ),
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("expected exactly one canonical" in error for error in errors))
        self.assertTrue(any("scene.xml existence" in error for error in errors))

    def test_short_source_pin_and_archive_digest_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            assets = root / CHECKER.ASSET_MODULE_PATH
            assets.write_text(
                assets.read_text(encoding="utf-8")
                .replace(f'"{CHECKER.APPROVED_MENAGERIE_COMMIT}"', '"abc123"')
                .replace(
                    f'"{CHECKER.APPROVED_MENAGERIE_ARCHIVE_SHA256}"',
                    '"deadbeef"',
                ),
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("full 40-hex SHA" in error for error in errors))
        self.assertTrue(any("64-hex SHA-256" in error for error in errors))

    def test_coherent_but_unapproved_provenance_pins_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            for relative in (CHECKER.ASSET_MODULE_PATH, CHECKER.ASSET_MANIFEST_PATH):
                path = root / relative
                path.write_text(
                    path.read_text(encoding="utf-8")
                    .replace(CHECKER.APPROVED_MENAGERIE_COMMIT, "a" * 40)
                    .replace(CHECKER.APPROVED_MENAGERIE_ARCHIVE_SHA256, "b" * 64),
                    encoding="utf-8",
                )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("approved provenance pin" in error for error in errors))
        self.assertTrue(any("approved archive digest" in error for error in errors))

    def test_coherent_runtime_manifest_shrink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            entries = tuple(
                entry
                for entry in _fixture_manifest_entries()
                if entry[0] != "assets/fixture_00.obj"
            )
            _write_fixture_manifest(root, entries)

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("approved count 72" in error for error in errors))
        self.assertTrue(any("approved total 34333936" in error for error in errors))

    def test_runtime_manifest_schema_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            _write_fixture_manifest(root, _fixture_manifest_entries(), schema=2)

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("schema must equal approved integer 1" in error for error in errors))

    def test_runtime_manifest_unsafe_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            entries = list(_fixture_manifest_entries())
            index = next(
                index for index, entry in enumerate(entries) if entry[0].startswith("assets/")
            )
            _, size, digest = entries[index]
            entries[index] = ("../escape.obj", size, digest)
            _write_fixture_manifest(root, tuple(entries))

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("has unsafe path" in error for error in errors))

    def test_runtime_manifest_case_collision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            entries = list(_fixture_manifest_entries())
            first_index = next(
                index for index, entry in enumerate(entries) if entry[0] == "assets/fixture_00.obj"
            )
            second_index = next(
                index for index, entry in enumerate(entries) if entry[0] == "assets/fixture_01.obj"
            )
            first_path, _, _ = entries[first_index]
            _, second_size, second_digest = entries[second_index]
            entries[second_index] = (first_path.upper(), second_size, second_digest)
            _write_fixture_manifest(root, tuple(sorted(entries)))

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("case-insensitively unique" in error for error in errors))

    def test_approved_critical_runtime_members_are_required(self) -> None:
        for required in CHECKER.APPROVED_CRITICAL_RUNTIME_MEMBERS:
            with self.subTest(required=required), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_contract_fixture(root)
                entries = list(_fixture_manifest_entries())
                index = next(index for index, entry in enumerate(entries) if entry[0] == required)
                _, size, digest = entries[index]
                replacement = "assets/replacement_" + required.replace(".", "_").lower()
                entries[index] = (replacement, size, digest)
                _write_fixture_manifest(root, tuple(sorted(entries)))

                errors = CHECKER.asset_supply_chain_errors(root)

            self.assertTrue(
                any(f"runtime manifest is missing {required}" in error for error in errors)
            )

    def test_empty_runtime_manifest_and_missing_verify_cli_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            manifest = root / CHECKER.ASSET_MANIFEST_PATH
            manifest_lines = manifest.read_text(encoding="utf-8").splitlines()
            manifest.write_text(
                "\n".join(
                    "PANDA_RUNTIME_MANIFEST = ()"
                    if line.startswith("PANDA_RUNTIME_MANIFEST =")
                    else line
                    for line in manifest_lines
                )
                + "\n",
                encoding="utf-8",
            )
            cli = root / CHECKER.CLI_PATH
            cli.write_text(
                cli.read_text(encoding="utf-8")
                .replace('    subparsers.add_parser("verify")\n', "")
                .replace("    verify_assets()\n", ""),
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("runtime manifest must be a nonempty" in error for error in errors))
        self.assertTrue(any("assets verify parser is missing" in error for error in errors))
        self.assertTrue(any("verify_assets is not dispatched" in error for error in errors))

    def test_public_verification_types_cannot_point_to_a_missing_helper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            assets = root / CHECKER.ASSET_MODULE_PATH
            source = assets.read_text(encoding="utf-8")
            class_block = (
                "class AssetVerification:\n"
                "    pass\n\n"
                "class AssetVerificationError(RuntimeError):\n"
                "    pass\n\n"
                "class AssetSafetyError(RuntimeError):\n"
                "    pass\n\n"
            )
            assets.write_text(
                source.replace(
                    "from pathlib import Path\n",
                    "from pathlib import Path\n"
                    "from mclab.application._asset_verification import (\n"
                    "    AssetSafetyError, AssetVerification, AssetVerificationError,\n"
                    ")\n",
                ).replace(class_block, ""),
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any(str(CHECKER.ASSET_VERIFICATION_PATH) in error for error in errors))
        self.assertTrue(any("AssetVerification is missing" in error for error in errors))

    def test_runtime_manifest_entries_must_be_exact_sorted_and_counted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract_fixture(root)
            manifest = root / CHECKER.ASSET_MANIFEST_PATH
            lines = manifest.read_text(encoding="utf-8").splitlines()
            bad_entry = (
                'PANDA_RUNTIME_MANIFEST = (("scene.xml", 8, "'
                + "4" * 64
                + '"), ("LICENSE", 7, "'
                + "3" * 64
                + '"), ("bad.bin", 1, "short"))'
            )
            manifest.write_text(
                "\n".join(
                    bad_entry
                    if line.startswith("PANDA_RUNTIME_MANIFEST =")
                    else "PANDA_RUNTIME_FILE_COUNT = 3"
                    if line.startswith("PANDA_RUNTIME_FILE_COUNT =")
                    else "PANDA_RUNTIME_TOTAL_BYTES = 16"
                    if line.startswith("PANDA_RUNTIME_TOTAL_BYTES =")
                    else line
                    for line in lines
                )
                + "\n",
                encoding="utf-8",
            )

            errors = CHECKER.asset_supply_chain_errors(root)

        self.assertTrue(any("invalid SHA-256" in error for error in errors))
        self.assertTrue(any("sorted and unique" in error for error in errors))
        self.assertTrue(any("file count does not match" in error for error in errors))
        self.assertTrue(any("byte total does not match" in error for error in errors))

    def test_explicit_cache_variants_and_local_actions_are_rejected(self) -> None:
        cases = {
            "case variant": (
                CHECKER.WORKFLOW_PATHS[0],
                "      - uses: Actions/cache@" + "a" * 40 + "\n",
            ),
            "id first": (
                CHECKER.WORKFLOW_PATHS[0],
                "      - id: panda-cache\n"
                "        uses: actions/cache@"
                + "a" * 40
                + "\n        with:\n          path: third_party\n",
            ),
            "dynamic path": (
                CHECKER.WORKFLOW_PATHS[0],
                "      - uses: actions/cache/restore@" + "a" * 40 + "\n        with:\n"
                "          path: ${{ format('{0}/third_party', github.workspace) }}\n",
            ),
            "local composite": (
                Path(".github/actions/panda-cache/action.yml"),
                "runs:\n  using: composite\n  steps:\n"
                "    - uses: actions/cache/save@"
                + "a" * 40
                + "\n      with:\n        path: third_party/**\n",
            ),
        }
        for label, (relative, addition) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_contract_fixture(root)
                path = root / relative
                if path.exists():
                    path.write_text(
                        path.read_text(encoding="utf-8").replace(
                            "    steps:\n",
                            "    steps:\n" + addition,
                            1,
                        ),
                        encoding="utf-8",
                    )
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(addition, encoding="utf-8")

                errors = CHECKER.asset_supply_chain_errors(root)

            self.assertTrue(
                any("explicit actions/cache steps are forbidden" in error for error in errors)
            )

    def test_split_and_indirect_download_surfaces_are_rejected(self) -> None:
        cases = {
            Path("rogue.sh"): (
                "base=https://github.com/google-deepmind\n"
                "repo=mujoco_menagerie\n"
                'curl -L "$base/$repo/archive/refs/heads/main.tar.gz"\n'
            ),
            Path("scripts/fetch_menagerie"): (
                "#!/bin/sh\n"
                "curl -L 'https://github.com/google-deepmind/'"
                '"mujoco_menagerie/archive/main.tar.gz"\n'
            ),
            Path("tools/fetch.sh"): (
                "repo = 'mujoco_menagerie'\nrequests.get('https://example.invalid/' + repo)\n"
            ),
            Path("packaging/rogue.spec"): (
                "repo = 'mujoco_menagerie'\nrequests.get('https://example.invalid/' + repo)\n"
            ),
            Path(".github/actions/fetch/action.yml"): (
                "runs:\n  using: composite\n  steps:\n"
                "    - shell: pwsh\n"
                "      run: Invoke-RestMethod https://example.invalid/mujoco_menagerie\n"
            ),
        }
        for relative, source in cases.items():
            with self.subTest(relative=str(relative)), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_contract_fixture(root)
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")

                errors = CHECKER.asset_supply_chain_errors(root)

            self.assertTrue(
                any(
                    str(relative) in error and "bypasses the canonical installer" in error
                    for error in errors
                )
            )

    def test_job_level_weakening_is_rejected(self) -> None:
        mutations = {
            "continue": "    continue-on-error: true\n",
            "needs": "    needs: skipped-guard\n",
            "defaults": ("    defaults:\n      run:\n        shell: \"sh -c 'true' {0}\"\n"),
        }
        for label, insertion in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_contract_fixture(root)
                workflow = root / CHECKER.WORKFLOW_PATHS[0]
                workflow.write_text(
                    workflow.read_text(encoding="utf-8").replace(
                        "  simulator:\n",
                        "  simulator:\n" + insertion,
                        1,
                    ),
                    encoding="utf-8",
                )

                errors = CHECKER.asset_supply_chain_errors(root)

            self.assertTrue(any("job must be unconditional" in error for error in errors))

    def test_workflow_defaults_are_rejected(self) -> None:
        for key in ("defaults", '"defaults"', "'defaults'"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_contract_fixture(root)
                workflow = root / CHECKER.WORKFLOW_PATHS[0]
                workflow.write_text(
                    f"{key}:\n  run:\n    shell: \"sh -c 'true' {{0}}\"\n"
                    + workflow.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )

                errors = CHECKER.asset_supply_chain_errors(root)

            self.assertTrue(any("workflow defaults" in error for error in errors))

    def test_order_comments_missing_anchors_and_cross_job_steps_are_rejected(self) -> None:
        package_step = (
            "      - name: Install package with dev tools\n"
            "        run: python scripts/install_locked.py dev\n\n"
        )
        mutations = {
            "comment spoof": lambda text: text.replace(package_step, "").replace(
                CHECKER.WORKFLOW_ASSET_STEP,
                "      # - name: Install package with dev tools\n"
                + CHECKER.WORKFLOW_ASSET_STEP
                + "\n"
                + package_step,
            ),
            "missing anchor": lambda text: text.replace(
                "Install package with dev tools",
                "Renamed package setup",
            ),
            "cross job": lambda text: text.replace(package_step, "").replace(
                "jobs:\n",
                "jobs:\n  setup-only:\n    steps:\n" + package_step,
                1,
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_contract_fixture(root)
                workflow = root / CHECKER.WORKFLOW_PATHS[0]
                workflow.write_text(
                    mutate(workflow.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )

                errors = CHECKER.asset_supply_chain_errors(root)

            self.assertTrue(
                any("asset verification" in error and "order" in error for error in errors)
            )

    def test_nonexecuting_and_early_launcher_probes_are_rejected(self) -> None:
        mutations = {
            "comment": lambda text: text.replace(
                CHECKER.LAUNCHER_VERIFY,
                "rem " + CHECKER.LAUNCHER_VERIFY,
            ),
            "echo": lambda text: text.replace(
                CHECKER.LAUNCHER_VERIFY,
                "echo " + CHECKER.LAUNCHER_VERIFY,
            ),
            "goto": lambda text: text.replace(
                CHECKER.LAUNCHER_VERIFY,
                "goto :run\n" + CHECKER.LAUNCHER_VERIFY,
            ),
            "call": lambda text: text.replace(
                CHECKER.LAUNCHER_VERIFY,
                "call :run\n" + CHECKER.LAUNCHER_VERIFY,
            ),
            "direct workload": lambda text: text.replace(
                CHECKER.LAUNCHER_VERIFY,
                '".venv\\Scripts\\python.exe" -m mclab run lab04 --headless\n'
                + CHECKER.LAUNCHER_VERIFY,
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_contract_fixture(root)
                launcher = root / CHECKER.ASSET_LAUNCHERS[0]
                launcher.write_text(
                    mutate(launcher.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )

                errors = CHECKER.asset_supply_chain_errors(root)

            self.assertTrue(
                any(
                    "canonical assets verify probe" in error
                    or "verification must run before" in error
                    for error in errors
                )
            )

    def test_new_lab04_launcher_must_include_the_probe(self) -> None:
        for launcher_name in (
            "run_lab04_new.cmd",
            "RUN_LAB04_NEW.CMD",
            "run_lab04_new.bat",
            "RUN_LAB04_NEW.BAT",
        ):
            with self.subTest(launcher_name=launcher_name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_contract_fixture(root)
                launcher = root / launcher_name
                launcher.write_text(
                    "@echo off\n.venv\\Scripts\\python.exe -m mclab run lab04 --headless\n",
                    encoding="utf-8",
                )

                errors = CHECKER.asset_supply_chain_errors(root)

            self.assertTrue(
                any(
                    launcher_name in error and "canonical assets verify probe" in error
                    for error in errors
                )
            )


def _fixture_manifest_entries() -> tuple[tuple[str, int, str], ...]:
    paths = sorted(
        (
            *CHECKER.APPROVED_CRITICAL_RUNTIME_MEMBERS,
            *(f"assets/fixture_{index:02d}.obj" for index in range(67)),
        )
    )
    first_size = CHECKER.APPROVED_RUNTIME_TOTAL_BYTES - len(paths) + 1
    return tuple(
        (
            path,
            first_size if index == 0 else 1,
            f"{index + 1:064x}",
        )
        for index, path in enumerate(paths)
    )


def _write_fixture_manifest(
    root: Path,
    entries: tuple[tuple[str, int, str], ...],
    *,
    schema: int = CHECKER.APPROVED_RUNTIME_MANIFEST_SCHEMA,
) -> None:
    application = root / "src" / "mclab" / "application"
    application.mkdir(parents=True, exist_ok=True)
    (application / "panda_runtime_manifest.py").write_text(
        f"PANDA_RUNTIME_MANIFEST_SCHEMA = {schema}\n"
        f'PANDA_RUNTIME_MENAGERIE_COMMIT = "{CHECKER.APPROVED_MENAGERIE_COMMIT}"\n'
        "PANDA_RUNTIME_ARCHIVE_SHA256 = "
        f'"{CHECKER.APPROVED_MENAGERIE_ARCHIVE_SHA256}"\n'
        f"PANDA_RUNTIME_MANIFEST = {entries!r}\n"
        f"PANDA_RUNTIME_FILE_COUNT = {len(entries)}\n"
        f"PANDA_RUNTIME_TOTAL_BYTES = {sum(entry[1] for entry in entries)}\n",
        encoding="utf-8",
    )


def _write_contract_fixture(root: Path) -> None:
    application = root / "src" / "mclab" / "application"
    application.mkdir(parents=True)
    (application / "assets.py").write_text(
        "from pathlib import Path\n"
        f'MENAGERIE_COMMIT = "{CHECKER.APPROVED_MENAGERIE_COMMIT}"\n'
        f'MENAGERIE_ARCHIVE_SHA256 = "{CHECKER.APPROVED_MENAGERIE_ARCHIVE_SHA256}"\n\n'
        "class AssetVerification:\n"
        "    pass\n\n"
        "class AssetVerificationError(RuntimeError):\n"
        "    pass\n\n"
        "class AssetSafetyError(RuntimeError):\n"
        "    pass\n\n"
        "def verify_assets(root: Path = Path('.')) -> object:\n"
        "    return object()\n\n"
        "def install_assets(root: Path = Path('.')) -> Path:\n"
        "    return root\n",
        encoding="utf-8",
    )
    _write_fixture_manifest(root, _fixture_manifest_entries())
    cli = root / "src" / "mclab" / "cli.py"
    cli.write_text(
        "def install_assets() -> None:\n"
        "    pass\n\n"
        "def verify_assets() -> None:\n"
        "    pass\n\n"
        "def configure(subparsers: object) -> None:\n"
        '    subparsers.add_parser("install")\n'
        '    subparsers.add_parser("verify")\n'
        "    install_assets()\n"
        "    verify_assets()\n",
        encoding="utf-8",
    )
    bootstrap = root / CHECKER.BOOTSTRAP_PATH
    bootstrap.parent.mkdir(parents=True)
    bootstrap.write_text(
        "from pathlib import Path\n"
        "VENV_PYTHON = Path('.venv/bin/python')\n\n"
        "def run(command: list[str]) -> None:\n"
        "    pass\n\n"
        "def ensure_menagerie() -> None:\n"
        '    run([str(VENV_PYTHON), "-m", "mclab", "assets", "install"])\n',
        encoding="utf-8",
    )
    workflow_root = root / ".github" / "workflows"
    workflow_root.mkdir(parents=True)
    (root / CHECKER.WORKFLOW_PATHS[0]).write_text(
        "jobs:\n"
        "  simulator:\n"
        "    steps:\n"
        + CHECKER.WORKFLOW_POLICY_STEP
        + "\n      - name: Install package with dev tools\n"
        "        run: python scripts/install_locked.py dev\n\n"
        + CHECKER.WORKFLOW_ASSET_STEP
        + "\n      - name: Ruff lint\n"
        "        run: python -m ruff check src tests\n",
        encoding="utf-8",
    )
    (root / CHECKER.WORKFLOW_PATHS[1]).write_text(
        "jobs:\n"
        "  desktop:\n"
        "    steps:\n"
        "      - name: Install desktop, test, and packaging dependencies\n"
        "        run: python scripts/install_locked.py package\n\n"
        + CHECKER.WORKFLOW_ASSET_STEP
        + "\n      - name: Windows compatibility launcher repair matrix\n"
        "        run: echo smoke\n",
        encoding="utf-8",
    )
    for relative in CHECKER.ASSET_LAUNCHERS:
        (root / relative).write_text(
            "@echo off\n"
            '".venv\\Scripts\\python.exe" "scripts\\install_locked.py" '
            "--check runtime >nul 2>&1\n"
            "if errorlevel 1 goto setup\n"
            + CHECKER.LAUNCHER_FALLBACK
            + "\ngoto run\n\n:setup\necho setup\n\n:run\necho run\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
