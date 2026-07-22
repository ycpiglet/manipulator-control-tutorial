"""Generate the bounded LIC-01A package-license inventory contract.

The registry is deliberately an inventory-coverage contract, not a notice
bundle or legal conclusion. It closes every direct producer input by path and
hash, including the reviewed build/package/scanner-tool locks and the existing
SBOM surface inputs. Accepted SUP-01 target observations retain raw and
canonical evidence provenance, but license and NOTICE bodies are never copied
into the committed registry.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import generate_sbom_inputs as supply  # noqa: E402


SCHEMA_VERSION = 1
CANDIDATE_COUNT = 49
TARGET_CELL_COUNT = 12
OBSERVED_TARGET_COUNT = 3
EVIDENCE_NORMALIZATION_ALGORITHM = "strict-json-sort-keys-indent-2-ensure-ascii-false-utf8-lf"
EVIDENCE_NORMALIZATION_VERSION = 1

REGISTRY_PATH = ".agents/supply_chain/license-inventory.json"
REGISTRY_SCHEMA_PATH = ".agents/supply_chain/license-inventory.schema.json"
EVIDENCE_SCHEMA_PATH = ".agents/supply_chain/python-license-evidence.schema.json"
GENERATOR_PATH = "scripts/generate_license_inventory.py"
CHECKER_PATH = ".agents/validation/check_license_inventory.py"
SCANNER_PATH = "scripts/audit_supply_chain.py"
SBOM_GENERATOR_PATH = "scripts/generate_sbom_inputs.py"
BUILD_LOCK_PATH = "requirements/locks/build.txt"
BUILD_SOURCE_PATH = "requirements/build.in"
PACKAGE_LOCK_PATH = "requirements/locks/package.txt"
SUPPLY_CHAIN_TOOL_LOCK_PATH = "requirements/tools/supply-chain.txt"
SUPPLY_CHAIN_TOOL_SOURCE_PATH = "requirements/tools/supply-chain.in"
PROJECT_PATH = "pyproject.toml"

SOURCE_PATHS = {
    "build_lock": BUILD_LOCK_PATH,
    "build_source": BUILD_SOURCE_PATH,
    "checker": CHECKER_PATH,
    "evidence_schema": EVIDENCE_SCHEMA_PATH,
    "font_license": supply.EXPECTED_FONT_LICENSE[0],
    "font_noto_sans_kr": supply.EXPECTED_FONT_FILES[0][1],
    "font_noto_sans_mono": supply.EXPECTED_FONT_FILES[1][1],
    "generator": GENERATOR_PATH,
    "package_lock": PACKAGE_LOCK_PATH,
    "packaging_spec": supply.PACKAGING_SPEC_PATH,
    "panda_manifest": supply.PANDA_MANIFEST_PATH,
    "project": PROJECT_PATH,
    "project_license": supply.PROJECT_LICENSE_PATH,
    "registry_schema": REGISTRY_SCHEMA_PATH,
    "scanner": SCANNER_PATH,
    "sbom_generator": SBOM_GENERATOR_PATH,
    "supply_chain_tool_lock": SUPPLY_CHAIN_TOOL_LOCK_PATH,
    "supply_chain_tool_source": SUPPLY_CHAIN_TOOL_SOURCE_PATH,
    "ubuntu_installer": supply.UBUNTU_INSTALLER_PATH,
    "ubuntu_manifest": supply.UBUNTU_MANIFEST_PATH,
}

SCANNER_EXCLUDED_PACKAGES = frozenset({"pip", "setuptools", "wheel"})
EXPECTED_PIP_LICENSES_VERSION = "5.5.5"
EXPECTED_SETUPTOOLS_VERSION = "83.0.0"
NOT_APPLICABLE_REASON = "marker-not-applicable-to-observed-targets"
SETUPTOOLS_EXCLUSION_REASON = "explicit-target-scoped-scanner-exclusion"
EDITABLE_PROJECT_ADDITION_REASON = "editable-project-target-addition"

BLOCKERS = (
    "copyright-attribution-review-pending",
    "distribution-closure-unproven",
    "license-expression-review-pending",
    "license-text-coverage-pending",
    "native-and-base-image-transitive-inventory-pending",
    "notice-text-coverage-pending",
    "qt-pyside-lgpl-compliance-decision-pending",
    "source-offer-and-relinking-obligations-pending",
)

EXPECTED_CELL_COUNTS = {
    "cpython-3.10-darwin-arm64": 46,
    "cpython-3.10-darwin-x86_64": 46,
    "cpython-3.10-linux-x86_64": 45,
    "cpython-3.10-win32-amd64": 48,
    "cpython-3.11-darwin-arm64": 45,
    "cpython-3.11-darwin-x86_64": 45,
    "cpython-3.11-linux-x86_64": 44,
    "cpython-3.11-win32-amd64": 47,
    "cpython-3.12-darwin-arm64": 44,
    "cpython-3.12-darwin-x86_64": 44,
    "cpython-3.12-linux-x86_64": 43,
    "cpython-3.12-win32-amd64": 46,
}

OBSERVATION_BASELINE = {
    "evidence_scope": "short-lived development evidence; not release provenance",
    "source_commit": "6f0995bd8fe52f8fa6832a03f83254eb13ff9cc1",
    "workflow_run_id": 29950992873,
}

OBSERVED_TARGETS = (
    {
        "artifact": {
            "canonical_evidence_sha256": (
                "cea1db18977740f449f413d87e13ee2c85707f6bcbc2684b020f396c82635d83"
            ),
            "expires_at": "2026-08-05T19:27:49Z",
            "id": 8542125543,
            "name": "mclab-supply-chain-Linux",
            "normalization_algorithm": EVIDENCE_NORMALIZATION_ALGORITHM,
            "normalization_version": EVIDENCE_NORMALIZATION_VERSION,
            "raw_evidence_sha256": (
                "cea1db18977740f449f413d87e13ee2c85707f6bcbc2684b020f396c82635d83"
            ),
        },
        "cell_id": "cpython-3.11-linux-x86_64",
        "id": "github-hosted-linux-cpython-3.11",
        "metadata_gaps": {
            "license": 1,
            "license_text": 3,
            "notice_text": 43,
            "url": 2,
        },
        "package_count": 44,
        "recorded_target": {
            "implementation": "CPython",
            "implementation_name": "cpython",
            "machine": "x86_64",
            "python_full_version": "3.11.15",
            "sys_platform": "linux",
        },
        "runner_os": "Linux",
    },
    {
        "artifact": {
            "canonical_evidence_sha256": (
                "fdc73a10a3e5a9bad525604d1ff7450021182fbb78965b7407da7620d50d44de"
            ),
            "expires_at": "2026-08-05T19:27:32Z",
            "id": 8542118388,
            "name": "mclab-supply-chain-macOS",
            "normalization_algorithm": EVIDENCE_NORMALIZATION_ALGORITHM,
            "normalization_version": EVIDENCE_NORMALIZATION_VERSION,
            "raw_evidence_sha256": (
                "fdc73a10a3e5a9bad525604d1ff7450021182fbb78965b7407da7620d50d44de"
            ),
        },
        "cell_id": "cpython-3.11-darwin-arm64",
        "id": "github-hosted-macos-cpython-3.11",
        "metadata_gaps": {
            "license": 1,
            "license_text": 3,
            "notice_text": 44,
            "url": 2,
        },
        "package_count": 45,
        "recorded_target": {
            "implementation": "CPython",
            "implementation_name": "cpython",
            "machine": "arm64",
            "python_full_version": "3.11.9",
            "sys_platform": "darwin",
        },
        "runner_os": "macOS",
    },
    {
        "artifact": {
            "canonical_evidence_sha256": (
                "dadbc2a1741e76909c18979045b98c62477ff819a44c90944e7c010ec0f09379"
            ),
            "expires_at": "2026-08-05T19:29:22Z",
            "id": 8542166959,
            "name": "mclab-supply-chain-Windows",
            "normalization_algorithm": EVIDENCE_NORMALIZATION_ALGORITHM,
            "normalization_version": EVIDENCE_NORMALIZATION_VERSION,
            "raw_evidence_sha256": (
                "bd9540d0b5a21f0772d9722b5fbf61e63902547074ac738d874da2bc9dfb987f"
            ),
        },
        "cell_id": "cpython-3.11-win32-amd64",
        "id": "github-hosted-windows-cpython-3.11",
        "metadata_gaps": {
            "license": 1,
            "license_text": 1,
            "notice_text": 46,
            "url": 2,
        },
        "package_count": 47,
        "recorded_target": {
            "implementation": "CPython",
            "implementation_name": "cpython",
            "machine": "AMD64",
            "python_full_version": "3.11.9",
            "sys_platform": "win32",
        },
        "runner_os": "Windows",
    },
)


OBSERVED_PACKAGE_OBSERVATIONS = {
    "Linux": (
        (
            "absl-py",
            "2.5.0",
            "Apache-2.0",
            "https://github.com/abseil/abseil-py",
            "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b",
            None,
        ),
        (
            "altgraph",
            "0.17.5",
            "MIT License",
            "https://altgraph.readthedocs.io",
            "6aedd24b2bb1c39278030dc031ac338a0b1ba5c748f8c55109b0e2024cf52575",
            None,
        ),
        (
            "ast-serialize",
            "0.6.0",
            "MIT",
            "https://github.com/mypyc/ast_serialize",
            "b8099477985fcd55f7af91efd698c27eec182f0c7d5d62c5d2cfb28ce53ecaf5",
            None,
        ),
        (
            "axe-playwright-python",
            "0.1.7",
            None,
            "https://pamelafox.github.io/axe-playwright-python",
            "e69be8261723b83133cef88b9e07452794f86ebf0b595766eb22ffe780835a3b",
            None,
        ),
        (
            "contourpy",
            "1.3.2",
            "BSD License",
            "https://github.com/contourpy/contourpy",
            "4e85324de598a629b159b1bc8184391b995a224e94b653464c782b3be4c80e0d",
            None,
        ),
        (
            "coverage",
            "7.15.2",
            "Apache-2.0",
            "https://github.com/coveragepy/coveragepy",
            "4bf96504d6e83ce5c6fc7167f1795d9ceaa68e70ab86bc5d08ab93184262bbbe",
            None,
        ),
        (
            "cycler",
            "0.12.1",
            "BSD License",
            "https://matplotlib.org/cycler/",
            "f1218143d766da3fea66f13396b7f15df46a83303f29bf96ba6e98eb4d42f408",
            None,
        ),
        (
            "etils",
            "1.13.0",
            "Apache Software License",
            "https://github.com/google/etils",
            "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b",
            None,
        ),
        (
            "fonttools",
            "4.63.0",
            "MIT",
            "http://github.com/fonttools/fonttools",
            "bcf9c4f3815a8ef8945325d6900169c034994e6f4a3c4ff11455cbcee43ff23f",
            None,
        ),
        (
            "fsspec",
            "2026.6.0",
            "BSD-3-Clause",
            "https://github.com/fsspec/filesystem_spec",
            "c03b1c97bf1e47e8f003ac479ba4cd9d2860827d340db50746b79ca5d3e921ca",
            None,
        ),
        (
            "glfw",
            "2.10.2",
            "MIT License",
            "https://github.com/FlorianRhiem/pyGLFW",
            "02f881774a8ff27734660cab4c4023fa716ef3f6401487fe373138882dca6b3d",
            None,
        ),
        (
            "greenlet",
            "3.5.3",
            "MIT AND PSF-2.0",
            "https://greenlet.readthedocs.io",
            "3db20b97e24acc77b0eac77195e4eaf4ee23b64c0049585be5a5edadaa7e20a8",
            None,
        ),
        (
            "importlib-resources",
            "7.1.0",
            "Apache-2.0",
            "https://github.com/python/importlib_resources",
            "36368470ab75b8642a1017023e3e069d548ae83b44f516d7c9a0435fe32b7531",
            None,
        ),
        (
            "iniconfig",
            "2.3.0",
            "MIT",
            "https://github.com/pytest-dev/iniconfig",
            "b25ef321fa3d1d268e71c366a7a0b43a85c4adc92d413f4213bf8a4fcc2186a8",
            None,
        ),
        (
            "kiwisolver",
            "1.5.0",
            "BSD License",
            "https://github.com/nucleic/kiwi",
            "9ebedced2216050cefa62c4832c13109a54de9aa3ad9bb0ff42fdb878d80443f",
            None,
        ),
        (
            "librt",
            "0.13.0",
            "MIT",
            "https://github.com/mypyc/librt",
            "aed81b48b09b6510920fca77e470d03c1db19759e19fd3f6c5d71526568faf60",
            None,
        ),
        (
            "matplotlib",
            "3.10.9",
            "Python Software Foundation License",
            "https://matplotlib.org",
            "329a9d7b2bb9b0190cb6d1441d048720dd4a4658e96dacaee376398c04788607",
            None,
        ),
        (
            "mujoco",
            "3.10.0",
            "Apache-2.0",
            "https://github.com/google-deepmind/mujoco",
            "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b",
            None,
        ),
        (
            "mujoco-manipulator-control-lab",
            "0.1.0",
            "Apache-2.0",
            None,
            "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b",
            None,
        ),
        (
            "mypy",
            "2.3.0",
            "MIT",
            "https://www.mypy-lang.org/",
            "b30156c32682d5cb5821fc9e3a88ca82cc3852da46a30ea5b3c9c188dff92a6e",
            None,
        ),
        (
            "mypy-extensions",
            "1.1.0",
            "MIT",
            "https://github.com/python/mypy_extensions",
            "873caa95fa01cebbed0594fe2ab5b94fcf4d8c3cf35ed62477b57a9a1bb0a24d",
            None,
        ),
        (
            "numpy",
            "2.2.6",
            "BSD License",
            "https://numpy.org",
            "2943ca732b32b4405aac3d4e77e2f4dfcff4f3eb47768aea6bee2fa9bd489b4d",
            None,
        ),
        (
            "packaging",
            "26.2",
            "Apache-2.0 OR BSD-2-Clause",
            "https://github.com/pypa/packaging",
            "e4dce5f35b25e78e3cfce568d20f4125821bfd61bce2d008f28656c4b576bd35",
            None,
        ),
        (
            "pathspec",
            "1.1.1",
            "Mozilla Public License 2.0 (MPL 2.0)",
            "https://python-path-specification.readthedocs.io/en/latest/index.html",
            "4b89d4518bd135ab4ee154a7bce722246b57a98c3d7efc1a09409898160c2bd1",
            None,
        ),
        (
            "pillow",
            "12.3.0",
            "MIT-CMU",
            "https://python-pillow.github.io",
            "62b280c1bcf9ab52ab601801c0561be70141de2774da018317c3b8ff49b00cf8",
            None,
        ),
        (
            "playwright",
            "1.61.0",
            "Apache-2.0",
            "https://github.com/Microsoft/playwright-python",
            "5b475effab78d12623dfa54915387571ec075e7f7e026cc0a196cfce2d764049",
            "7b1444e03705067d36e59fc8cd3260daf245b8d06006cad06d462578fb92eab5",
        ),
        (
            "pluggy",
            "1.6.0",
            "MIT License",
            None,
            "8360099724c6348aeb42a434fea463674af3c5f71223b835825afe784566af03",
            None,
        ),
        (
            "pyee",
            "13.0.1",
            "MIT License",
            "https://github.com/jfhbrook/pyee",
            "0f54cdb831bdbb6125bbd5f8d41f5c5fabd1982912f85ecd85e79be1ef4f9163",
            None,
        ),
        (
            "pygments",
            "2.20.0",
            "BSD-2-Clause",
            "https://pygments.org",
            "e0a04358a9a926507ae497776b472aa19cb233a897aa0eccb5a2e11b8f955f91",
            None,
        ),
        (
            "pyinstaller",
            "6.21.0",
            "GNU General Public License v2 (GPLv2)",
            "https://pyinstaller.org",
            "fd1ffa8eb114741cea84dcd57cecc853c2b0fd5375a9ce61c219248e7d2bc58a",
            None,
        ),
        (
            "pyinstaller-hooks-contrib",
            "2026.6",
            "Apache Software License; GNU General Public License v2 (GPLv2)",
            "https://github.com/pyinstaller/pyinstaller-hooks-contrib",
            "e0f26791e2ae4726a8b7e8cde0e1fb4ccb0eabfe1be921781f6cf2db918612b3",
            None,
        ),
        ("pyopengl", "3.1.10", "BSD License", "https://mcfletch.github.io/pyopengl/", None, None),
        (
            "pyparsing",
            "3.3.2",
            "MIT",
            "https://github.com/pyparsing/pyparsing/",
            "5f7d6cb9b616fcfb5a5cc958aaf3ca752158e350bcc9138df97acf5d71719888",
            None,
        ),
        (
            "pyside6-essentials",
            "6.11.1",
            "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
            "https://pyside.org",
            None,
            None,
        ),
        (
            "pytest",
            "9.1.1",
            "MIT",
            "https://docs.pytest.org/en/latest/",
            "f62c36bc71fefd24bbdd659c1003d49650c7930aa6763ad6a529314163e4f9ed",
            None,
        ),
        (
            "pytest-cov",
            "7.1.0",
            "MIT",
            "https://pytest-cov.readthedocs.io/en/latest/changelog.html",
            "f8f8d8f8f567083839566b05b066c25684a81b6aec4b930da88c6c7ccb9ad392",
            None,
        ),
        (
            "python-dateutil",
            "2.9.0.post0",
            "Apache Software License; BSD License",
            "https://github.com/dateutil/dateutil",
            "ba00f51a0d92823b5a1cde27d8b5b9d2321e67ed8da9bc163eff96d5e17e577e",
            None,
        ),
        (
            "pyyaml",
            "6.0.3",
            "MIT License",
            "https://pyyaml.org/",
            "d387564cc3a28ec35ea44a033c74dae724dbd31457fdbba30f1ee2f7090c4e40",
            None,
        ),
        (
            "ruff",
            "0.15.22",
            "MIT",
            "https://docs.astral.sh/ruff",
            "aaa18222a10861f3210e4c843794bf87cc56ce62f6732caa52b9525c2117ab25",
            None,
        ),
        (
            "shiboken6",
            "6.11.1",
            "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
            "https://pyside.org",
            None,
            None,
        ),
        (
            "six",
            "1.17.0",
            "MIT License",
            "https://github.com/benjaminp/six",
            "0a088cc4562b84017c036b81b663aad07829223c55abff490609470419f7be46",
            None,
        ),
        (
            "tomli",
            "2.4.1",
            "MIT",
            "https://github.com/hukkin/tomli",
            "bea8ef66252796e862df522e75b3251f7502ff6d8cf01d66125ac72621493d73",
            None,
        ),
        (
            "typing-extensions",
            "4.16.0",
            "PSF-2.0",
            "https://github.com/python/typing_extensions",
            "0e700f6605c5b82ecda8eba25e24577f7ea7a9842266777093f8756216cabe1e",
            None,
        ),
        (
            "zipp",
            "4.1.0",
            "MIT",
            "https://github.com/jaraco/zipp",
            "65a93b2a7c8bb79f09454834295034917075c80a5b4e4a688e97ea35798bde58",
            None,
        ),
    ),
    "macOS": (
        (
            "absl-py",
            "2.5.0",
            "Apache-2.0",
            "https://github.com/abseil/abseil-py",
            "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b",
            None,
        ),
        (
            "altgraph",
            "0.17.5",
            "MIT License",
            "https://altgraph.readthedocs.io",
            "6aedd24b2bb1c39278030dc031ac338a0b1ba5c748f8c55109b0e2024cf52575",
            None,
        ),
        (
            "ast-serialize",
            "0.6.0",
            "MIT",
            "https://github.com/mypyc/ast_serialize",
            "b8099477985fcd55f7af91efd698c27eec182f0c7d5d62c5d2cfb28ce53ecaf5",
            None,
        ),
        (
            "axe-playwright-python",
            "0.1.7",
            None,
            "https://pamelafox.github.io/axe-playwright-python",
            "e69be8261723b83133cef88b9e07452794f86ebf0b595766eb22ffe780835a3b",
            None,
        ),
        (
            "contourpy",
            "1.3.2",
            "BSD License",
            "https://github.com/contourpy/contourpy",
            "4e85324de598a629b159b1bc8184391b995a224e94b653464c782b3be4c80e0d",
            None,
        ),
        (
            "coverage",
            "7.15.2",
            "Apache-2.0",
            "https://github.com/coveragepy/coveragepy",
            "4bf96504d6e83ce5c6fc7167f1795d9ceaa68e70ab86bc5d08ab93184262bbbe",
            None,
        ),
        (
            "cycler",
            "0.12.1",
            "BSD License",
            "https://matplotlib.org/cycler/",
            "f1218143d766da3fea66f13396b7f15df46a83303f29bf96ba6e98eb4d42f408",
            None,
        ),
        (
            "etils",
            "1.13.0",
            "Apache Software License",
            "https://github.com/google/etils",
            "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b",
            None,
        ),
        (
            "fonttools",
            "4.63.0",
            "MIT",
            "http://github.com/fonttools/fonttools",
            "bcf9c4f3815a8ef8945325d6900169c034994e6f4a3c4ff11455cbcee43ff23f",
            None,
        ),
        (
            "fsspec",
            "2026.6.0",
            "BSD-3-Clause",
            "https://github.com/fsspec/filesystem_spec",
            "c03b1c97bf1e47e8f003ac479ba4cd9d2860827d340db50746b79ca5d3e921ca",
            None,
        ),
        (
            "glfw",
            "2.10.2",
            "MIT License",
            "https://github.com/FlorianRhiem/pyGLFW",
            "02f881774a8ff27734660cab4c4023fa716ef3f6401487fe373138882dca6b3d",
            None,
        ),
        (
            "greenlet",
            "3.5.3",
            "MIT AND PSF-2.0",
            "https://greenlet.readthedocs.io",
            "3db20b97e24acc77b0eac77195e4eaf4ee23b64c0049585be5a5edadaa7e20a8",
            None,
        ),
        (
            "importlib-resources",
            "7.1.0",
            "Apache-2.0",
            "https://github.com/python/importlib_resources",
            "36368470ab75b8642a1017023e3e069d548ae83b44f516d7c9a0435fe32b7531",
            None,
        ),
        (
            "iniconfig",
            "2.3.0",
            "MIT",
            "https://github.com/pytest-dev/iniconfig",
            "b25ef321fa3d1d268e71c366a7a0b43a85c4adc92d413f4213bf8a4fcc2186a8",
            None,
        ),
        (
            "kiwisolver",
            "1.5.0",
            "BSD License",
            "https://github.com/nucleic/kiwi",
            "9ebedced2216050cefa62c4832c13109a54de9aa3ad9bb0ff42fdb878d80443f",
            None,
        ),
        (
            "librt",
            "0.13.0",
            "MIT",
            "https://github.com/mypyc/librt",
            "aed81b48b09b6510920fca77e470d03c1db19759e19fd3f6c5d71526568faf60",
            None,
        ),
        (
            "macholib",
            "1.16.4",
            "MIT License",
            "http://github.com/ronaldoussoren/macholib",
            "5584285723baac3023c145c533edbbee6f36b21baeeba059378a6f3d744ec389",
            None,
        ),
        (
            "matplotlib",
            "3.10.9",
            "Python Software Foundation License",
            "https://matplotlib.org",
            "329a9d7b2bb9b0190cb6d1441d048720dd4a4658e96dacaee376398c04788607",
            None,
        ),
        (
            "mujoco",
            "3.10.0",
            "Apache-2.0",
            "https://github.com/google-deepmind/mujoco",
            "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b",
            None,
        ),
        (
            "mujoco-manipulator-control-lab",
            "0.1.0",
            "Apache-2.0",
            None,
            "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b",
            None,
        ),
        (
            "mypy",
            "2.3.0",
            "MIT",
            "https://www.mypy-lang.org/",
            "b30156c32682d5cb5821fc9e3a88ca82cc3852da46a30ea5b3c9c188dff92a6e",
            None,
        ),
        (
            "mypy-extensions",
            "1.1.0",
            "MIT",
            "https://github.com/python/mypy_extensions",
            "873caa95fa01cebbed0594fe2ab5b94fcf4d8c3cf35ed62477b57a9a1bb0a24d",
            None,
        ),
        (
            "numpy",
            "2.2.6",
            "BSD License",
            "https://numpy.org",
            "9c8c492908b4fcce4d2f8a336130c069ca441e9d8a76ca744f9fc3386168f3fe",
            None,
        ),
        (
            "packaging",
            "26.2",
            "Apache-2.0 OR BSD-2-Clause",
            "https://github.com/pypa/packaging",
            "e4dce5f35b25e78e3cfce568d20f4125821bfd61bce2d008f28656c4b576bd35",
            None,
        ),
        (
            "pathspec",
            "1.1.1",
            "Mozilla Public License 2.0 (MPL 2.0)",
            "https://python-path-specification.readthedocs.io/en/latest/index.html",
            "4b89d4518bd135ab4ee154a7bce722246b57a98c3d7efc1a09409898160c2bd1",
            None,
        ),
        (
            "pillow",
            "12.3.0",
            "MIT-CMU",
            "https://python-pillow.github.io",
            "62b280c1bcf9ab52ab601801c0561be70141de2774da018317c3b8ff49b00cf8",
            None,
        ),
        (
            "playwright",
            "1.61.0",
            "Apache-2.0",
            "https://github.com/Microsoft/playwright-python",
            "5b475effab78d12623dfa54915387571ec075e7f7e026cc0a196cfce2d764049",
            "7b1444e03705067d36e59fc8cd3260daf245b8d06006cad06d462578fb92eab5",
        ),
        (
            "pluggy",
            "1.6.0",
            "MIT License",
            None,
            "8360099724c6348aeb42a434fea463674af3c5f71223b835825afe784566af03",
            None,
        ),
        (
            "pyee",
            "13.0.1",
            "MIT License",
            "https://github.com/jfhbrook/pyee",
            "0f54cdb831bdbb6125bbd5f8d41f5c5fabd1982912f85ecd85e79be1ef4f9163",
            None,
        ),
        (
            "pygments",
            "2.20.0",
            "BSD-2-Clause",
            "https://pygments.org",
            "e0a04358a9a926507ae497776b472aa19cb233a897aa0eccb5a2e11b8f955f91",
            None,
        ),
        (
            "pyinstaller",
            "6.21.0",
            "GNU General Public License v2 (GPLv2)",
            "https://pyinstaller.org",
            "fd1ffa8eb114741cea84dcd57cecc853c2b0fd5375a9ce61c219248e7d2bc58a",
            None,
        ),
        (
            "pyinstaller-hooks-contrib",
            "2026.6",
            "Apache Software License; GNU General Public License v2 (GPLv2)",
            "https://github.com/pyinstaller/pyinstaller-hooks-contrib",
            "e0f26791e2ae4726a8b7e8cde0e1fb4ccb0eabfe1be921781f6cf2db918612b3",
            None,
        ),
        ("pyopengl", "3.1.10", "BSD License", "https://mcfletch.github.io/pyopengl/", None, None),
        (
            "pyparsing",
            "3.3.2",
            "MIT",
            "https://github.com/pyparsing/pyparsing/",
            "5f7d6cb9b616fcfb5a5cc958aaf3ca752158e350bcc9138df97acf5d71719888",
            None,
        ),
        (
            "pyside6-essentials",
            "6.11.1",
            "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
            "https://pyside.org",
            None,
            None,
        ),
        (
            "pytest",
            "9.1.1",
            "MIT",
            "https://docs.pytest.org/en/latest/",
            "f62c36bc71fefd24bbdd659c1003d49650c7930aa6763ad6a529314163e4f9ed",
            None,
        ),
        (
            "pytest-cov",
            "7.1.0",
            "MIT",
            "https://pytest-cov.readthedocs.io/en/latest/changelog.html",
            "f8f8d8f8f567083839566b05b066c25684a81b6aec4b930da88c6c7ccb9ad392",
            None,
        ),
        (
            "python-dateutil",
            "2.9.0.post0",
            "Apache Software License; BSD License",
            "https://github.com/dateutil/dateutil",
            "ba00f51a0d92823b5a1cde27d8b5b9d2321e67ed8da9bc163eff96d5e17e577e",
            None,
        ),
        (
            "pyyaml",
            "6.0.3",
            "MIT License",
            "https://pyyaml.org/",
            "d387564cc3a28ec35ea44a033c74dae724dbd31457fdbba30f1ee2f7090c4e40",
            None,
        ),
        (
            "ruff",
            "0.15.22",
            "MIT",
            "https://docs.astral.sh/ruff",
            "aaa18222a10861f3210e4c843794bf87cc56ce62f6732caa52b9525c2117ab25",
            None,
        ),
        (
            "shiboken6",
            "6.11.1",
            "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
            "https://pyside.org",
            None,
            None,
        ),
        (
            "six",
            "1.17.0",
            "MIT License",
            "https://github.com/benjaminp/six",
            "0a088cc4562b84017c036b81b663aad07829223c55abff490609470419f7be46",
            None,
        ),
        (
            "tomli",
            "2.4.1",
            "MIT",
            "https://github.com/hukkin/tomli",
            "bea8ef66252796e862df522e75b3251f7502ff6d8cf01d66125ac72621493d73",
            None,
        ),
        (
            "typing-extensions",
            "4.16.0",
            "PSF-2.0",
            "https://github.com/python/typing_extensions",
            "0e700f6605c5b82ecda8eba25e24577f7ea7a9842266777093f8756216cabe1e",
            None,
        ),
        (
            "zipp",
            "4.1.0",
            "MIT",
            "https://github.com/jaraco/zipp",
            "65a93b2a7c8bb79f09454834295034917075c80a5b4e4a688e97ea35798bde58",
            None,
        ),
    ),
    "Windows": (
        (
            "absl-py",
            "2.5.0",
            "Apache-2.0",
            "https://github.com/abseil/abseil-py",
            "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b",
            None,
        ),
        (
            "altgraph",
            "0.17.5",
            "MIT License",
            "https://altgraph.readthedocs.io",
            "6aedd24b2bb1c39278030dc031ac338a0b1ba5c748f8c55109b0e2024cf52575",
            None,
        ),
        (
            "ast-serialize",
            "0.6.0",
            "MIT",
            "https://github.com/mypyc/ast_serialize",
            "b8099477985fcd55f7af91efd698c27eec182f0c7d5d62c5d2cfb28ce53ecaf5",
            None,
        ),
        (
            "axe-playwright-python",
            "0.1.7",
            None,
            "https://pamelafox.github.io/axe-playwright-python",
            "e69be8261723b83133cef88b9e07452794f86ebf0b595766eb22ffe780835a3b",
            None,
        ),
        (
            "colorama",
            "0.4.6",
            "BSD License",
            "https://github.com/tartley/colorama",
            "77f8a85bf994bd02d124fdd6afb44768c4fd6f361844f992cc1c81f4f6bba74f",
            None,
        ),
        (
            "contourpy",
            "1.3.2",
            "BSD License",
            "https://github.com/contourpy/contourpy",
            "4e85324de598a629b159b1bc8184391b995a224e94b653464c782b3be4c80e0d",
            None,
        ),
        (
            "coverage",
            "7.15.2",
            "Apache-2.0",
            "https://github.com/coveragepy/coveragepy",
            "4bf96504d6e83ce5c6fc7167f1795d9ceaa68e70ab86bc5d08ab93184262bbbe",
            None,
        ),
        (
            "cycler",
            "0.12.1",
            "BSD License",
            "https://matplotlib.org/cycler/",
            "f1218143d766da3fea66f13396b7f15df46a83303f29bf96ba6e98eb4d42f408",
            None,
        ),
        (
            "etils",
            "1.13.0",
            "Apache Software License",
            "https://github.com/google/etils",
            "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b",
            None,
        ),
        (
            "fonttools",
            "4.63.0",
            "MIT",
            "http://github.com/fonttools/fonttools",
            "bcf9c4f3815a8ef8945325d6900169c034994e6f4a3c4ff11455cbcee43ff23f",
            None,
        ),
        (
            "fsspec",
            "2026.6.0",
            "BSD-3-Clause",
            "https://github.com/fsspec/filesystem_spec",
            "c03b1c97bf1e47e8f003ac479ba4cd9d2860827d340db50746b79ca5d3e921ca",
            None,
        ),
        (
            "glfw",
            "2.10.2",
            "MIT License",
            "https://github.com/FlorianRhiem/pyGLFW",
            "02f881774a8ff27734660cab4c4023fa716ef3f6401487fe373138882dca6b3d",
            None,
        ),
        (
            "greenlet",
            "3.5.3",
            "MIT AND PSF-2.0",
            "https://greenlet.readthedocs.io",
            "3db20b97e24acc77b0eac77195e4eaf4ee23b64c0049585be5a5edadaa7e20a8",
            None,
        ),
        (
            "importlib-resources",
            "7.1.0",
            "Apache-2.0",
            "https://github.com/python/importlib_resources",
            "36368470ab75b8642a1017023e3e069d548ae83b44f516d7c9a0435fe32b7531",
            None,
        ),
        (
            "iniconfig",
            "2.3.0",
            "MIT",
            "https://github.com/pytest-dev/iniconfig",
            "b25ef321fa3d1d268e71c366a7a0b43a85c4adc92d413f4213bf8a4fcc2186a8",
            None,
        ),
        (
            "kiwisolver",
            "1.5.0",
            "BSD License",
            "https://github.com/nucleic/kiwi",
            "9ebedced2216050cefa62c4832c13109a54de9aa3ad9bb0ff42fdb878d80443f",
            None,
        ),
        (
            "librt",
            "0.13.0",
            "MIT",
            "https://github.com/mypyc/librt",
            "aed81b48b09b6510920fca77e470d03c1db19759e19fd3f6c5d71526568faf60",
            None,
        ),
        (
            "matplotlib",
            "3.10.9",
            "Python Software Foundation License",
            "https://matplotlib.org",
            "329a9d7b2bb9b0190cb6d1441d048720dd4a4658e96dacaee376398c04788607",
            None,
        ),
        (
            "mujoco",
            "3.10.0",
            "Apache-2.0",
            "https://github.com/google-deepmind/mujoco",
            "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b",
            None,
        ),
        (
            "mujoco-manipulator-control-lab",
            "0.1.0",
            "Apache-2.0",
            None,
            "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b",
            None,
        ),
        (
            "mypy",
            "2.3.0",
            "MIT",
            "https://www.mypy-lang.org/",
            "b30156c32682d5cb5821fc9e3a88ca82cc3852da46a30ea5b3c9c188dff92a6e",
            None,
        ),
        (
            "mypy-extensions",
            "1.1.0",
            "MIT",
            "https://github.com/python/mypy_extensions",
            "873caa95fa01cebbed0594fe2ab5b94fcf4d8c3cf35ed62477b57a9a1bb0a24d",
            None,
        ),
        (
            "numpy",
            "2.2.6",
            "BSD License",
            "https://numpy.org",
            "fd485e1a0840a773ecdce55f12343b5ebf251edfc5037575151ffdb16ce98594",
            None,
        ),
        (
            "packaging",
            "26.2",
            "Apache-2.0 OR BSD-2-Clause",
            "https://github.com/pypa/packaging",
            "e4dce5f35b25e78e3cfce568d20f4125821bfd61bce2d008f28656c4b576bd35",
            None,
        ),
        (
            "pathspec",
            "1.1.1",
            "Mozilla Public License 2.0 (MPL 2.0)",
            "https://python-path-specification.readthedocs.io/en/latest/index.html",
            "4b89d4518bd135ab4ee154a7bce722246b57a98c3d7efc1a09409898160c2bd1",
            None,
        ),
        (
            "pefile",
            "2024.8.26",
            "MIT",
            "https://github.com/erocarrera/pefile",
            "d79c2b7f75de76042dd415655923fe474cba16aa0effb022fa356665aba0cc0d",
            None,
        ),
        (
            "pillow",
            "12.3.0",
            "MIT-CMU",
            "https://python-pillow.github.io",
            "12c1f21bf2645be6b312b4ece5ebbd5203a39d621ffe7a434062d419fb60644d",
            None,
        ),
        (
            "playwright",
            "1.61.0",
            "Apache-2.0",
            "https://github.com/Microsoft/playwright-python",
            "5b475effab78d12623dfa54915387571ec075e7f7e026cc0a196cfce2d764049",
            "7b1444e03705067d36e59fc8cd3260daf245b8d06006cad06d462578fb92eab5",
        ),
        (
            "pluggy",
            "1.6.0",
            "MIT License",
            None,
            "8360099724c6348aeb42a434fea463674af3c5f71223b835825afe784566af03",
            None,
        ),
        (
            "pyee",
            "13.0.1",
            "MIT License",
            "https://github.com/jfhbrook/pyee",
            "0f54cdb831bdbb6125bbd5f8d41f5c5fabd1982912f85ecd85e79be1ef4f9163",
            None,
        ),
        (
            "pygments",
            "2.20.0",
            "BSD-2-Clause",
            "https://pygments.org",
            "e0a04358a9a926507ae497776b472aa19cb233a897aa0eccb5a2e11b8f955f91",
            None,
        ),
        (
            "pyinstaller",
            "6.21.0",
            "GNU General Public License v2 (GPLv2)",
            "https://pyinstaller.org",
            "fd1ffa8eb114741cea84dcd57cecc853c2b0fd5375a9ce61c219248e7d2bc58a",
            None,
        ),
        (
            "pyinstaller-hooks-contrib",
            "2026.6",
            "Apache Software License; GNU General Public License v2 (GPLv2)",
            "https://github.com/pyinstaller/pyinstaller-hooks-contrib",
            "e0f26791e2ae4726a8b7e8cde0e1fb4ccb0eabfe1be921781f6cf2db918612b3",
            None,
        ),
        ("pyopengl", "3.1.10", "BSD License", "https://mcfletch.github.io/pyopengl/", None, None),
        (
            "pyparsing",
            "3.3.2",
            "MIT",
            "https://github.com/pyparsing/pyparsing/",
            "5f7d6cb9b616fcfb5a5cc958aaf3ca752158e350bcc9138df97acf5d71719888",
            None,
        ),
        (
            "pyside6-essentials",
            "6.11.1",
            "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
            "https://pyside.org",
            "ae27b47d47e55078a2bb282cb447eaef5c033874fa7103a13087bbc78967e103",
            None,
        ),
        (
            "pytest",
            "9.1.1",
            "MIT",
            "https://docs.pytest.org/en/latest/",
            "f62c36bc71fefd24bbdd659c1003d49650c7930aa6763ad6a529314163e4f9ed",
            None,
        ),
        (
            "pytest-cov",
            "7.1.0",
            "MIT",
            "https://pytest-cov.readthedocs.io/en/latest/changelog.html",
            "f8f8d8f8f567083839566b05b066c25684a81b6aec4b930da88c6c7ccb9ad392",
            None,
        ),
        (
            "python-dateutil",
            "2.9.0.post0",
            "Apache Software License; BSD License",
            "https://github.com/dateutil/dateutil",
            "ba00f51a0d92823b5a1cde27d8b5b9d2321e67ed8da9bc163eff96d5e17e577e",
            None,
        ),
        (
            "pywin32-ctypes",
            "0.2.3",
            "BSD-3-Clause",
            "https://github.com/enthought/pywin32-ctypes",
            "b46622ea2bc08df44e0052c2c31664327f3359c1f7b3ed0402562f504c4556bf",
            None,
        ),
        (
            "pyyaml",
            "6.0.3",
            "MIT License",
            "https://pyyaml.org/",
            "d387564cc3a28ec35ea44a033c74dae724dbd31457fdbba30f1ee2f7090c4e40",
            None,
        ),
        (
            "ruff",
            "0.15.22",
            "MIT",
            "https://docs.astral.sh/ruff",
            "aaa18222a10861f3210e4c843794bf87cc56ce62f6732caa52b9525c2117ab25",
            None,
        ),
        (
            "shiboken6",
            "6.11.1",
            "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
            "https://pyside.org",
            "ae27b47d47e55078a2bb282cb447eaef5c033874fa7103a13087bbc78967e103",
            None,
        ),
        (
            "six",
            "1.17.0",
            "MIT License",
            "https://github.com/benjaminp/six",
            "0a088cc4562b84017c036b81b663aad07829223c55abff490609470419f7be46",
            None,
        ),
        (
            "tomli",
            "2.4.1",
            "MIT",
            "https://github.com/hukkin/tomli",
            "bea8ef66252796e862df522e75b3251f7502ff6d8cf01d66125ac72621493d73",
            None,
        ),
        (
            "typing-extensions",
            "4.16.0",
            "PSF-2.0",
            "https://github.com/python/typing_extensions",
            "0e700f6605c5b82ecda8eba25e24577f7ea7a9842266777093f8756216cabe1e",
            None,
        ),
        (
            "zipp",
            "4.1.0",
            "MIT",
            "https://github.com/jaraco/zipp",
            "65a93b2a7c8bb79f09454834295034917075c80a5b4e4a688e97ea35798bde58",
            None,
        ),
    ),
}


class LicenseInventoryError(RuntimeError):
    """Raised when the bounded LIC-01A contract cannot be generated safely."""


def _exact_int(value: object, label: str) -> int:
    if type(value) is not int:
        raise LicenseInventoryError(f"{label} must be an exact integer")
    return value


def _lock_profile(
    identifier: str, expected_path: str, expected_source_path: str
) -> supply.LockProfile:
    matches = [profile for profile in supply.LOCK_PROFILES if profile.identifier == identifier]
    if (
        len(matches) != 1
        or matches[0].lock_path != expected_path
        or matches[0].source_path != expected_source_path
    ):
        raise LicenseInventoryError(f"{identifier} lock profile identity drift")
    return matches[0]


def _package_profile() -> supply.LockProfile:
    return _lock_profile("package", PACKAGE_LOCK_PATH, PROJECT_PATH)


def _candidate_records(root: Path, environments: list[dict[str, str]]) -> list[dict[str, object]]:
    parsed = supply._parse_lock(root, _package_profile(), environments)
    requirements = parsed.get("requirements")
    if not isinstance(requirements, list) or len(requirements) != CANDIDATE_COUNT:
        actual = None if not isinstance(requirements, list) else len(requirements)
        raise LicenseInventoryError(
            f"package lock candidate count drift: {actual} != {CANDIDATE_COUNT}"
        )
    candidates: list[dict[str, object]] = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            raise LicenseInventoryError("package lock candidate is not an object")
        candidates.append(
            {
                "environment_ids": requirement["environment_ids"],
                "marker": requirement["marker"],
                "name": requirement["name"],
                "review_status": "pending",
                "version": requirement["version"],
            }
        )
    names = [str(candidate["name"]) for candidate in candidates]
    if names != sorted(names) or len(names) != len(set(names)):
        raise LicenseInventoryError("package lock candidates must be sorted and unique")
    return candidates


def _validate_direct_lock_inputs(
    root: Path,
    environments: list[dict[str, str]],
    candidates: list[dict[str, object]],
) -> None:
    build = supply._parse_lock(
        root,
        _lock_profile("build", BUILD_LOCK_PATH, BUILD_SOURCE_PATH),
        environments,
    )["requirements"]
    scanner_tools = supply._parse_lock(
        root,
        _lock_profile(
            "supply-chain-tool",
            SUPPLY_CHAIN_TOOL_LOCK_PATH,
            SUPPLY_CHAIN_TOOL_SOURCE_PATH,
        ),
        environments,
    )["requirements"]
    if not isinstance(build, list) or not isinstance(scanner_tools, list):
        raise LicenseInventoryError("direct scanner lock requirements must be lists")
    pip_licenses = [
        requirement
        for requirement in scanner_tools
        if isinstance(requirement, dict) and requirement.get("name") == "pip-licenses"
    ]
    if (
        len(pip_licenses) != 1
        or pip_licenses[0].get("version") != EXPECTED_PIP_LICENSES_VERSION
        or pip_licenses[0].get("environment_ids")
        != sorted(environment["id"] for environment in environments)
    ):
        raise LicenseInventoryError("pip-licenses scanner-tool lock identity drift")

    package_by_name = {str(candidate["name"]): candidate for candidate in candidates}
    setuptools = package_by_name.get("setuptools")
    if setuptools is None or setuptools.get("version") != EXPECTED_SETUPTOOLS_VERSION:
        raise LicenseInventoryError("package lock setuptools identity drift")
    observed_target_ids = {str(target["cell_id"]) for target in OBSERVED_TARGETS}
    for environment in environments:
        cell_id = environment["id"]
        if cell_id not in observed_target_ids:
            continue
        combined = {
            str(candidate["name"]): str(candidate["version"])
            for candidate in candidates
            if cell_id in candidate["environment_ids"]
        }
        for requirement in build:
            if not isinstance(requirement, dict) or cell_id not in requirement.get(
                "environment_ids", []
            ):
                continue
            name = str(requirement["name"])
            version = str(requirement["version"])
            previous = combined.get(name)
            if previous is not None and previous != version:
                raise LicenseInventoryError(f"build/package lock conflict for {cell_id}:{name}")
            combined[name] = version
        for excluded in SCANNER_EXCLUDED_PACKAGES:
            combined.pop(excluded, None)
        combined[str(supply.EXPECTED_PROJECT["name"])] = str(supply.EXPECTED_PROJECT["version"])
        if dict(sorted(combined.items())) != _expected_observed_packages(candidates, cell_id):
            raise LicenseInventoryError(f"build/package scanner transformation drift for {cell_id}")


def _target_cells(
    environments: list[dict[str, str]], candidates: list[dict[str, object]]
) -> list[dict[str, object]]:
    cells: list[dict[str, object]] = []
    for environment in environments:
        identifier = environment["id"]
        candidate_count = sum(
            identifier in candidate["environment_ids"] for candidate in candidates
        )
        cells.append(
            {
                "candidate_count": candidate_count,
                "id": identifier,
                "marker": environment["marker"],
                "platform_machine": environment["platform_machine"],
                "python_version": environment["python_version"],
                "sys_platform": environment["sys_platform"],
            }
        )
    cells.sort(key=lambda item: str(item["id"]))
    measured = {str(cell["id"]): int(cell["candidate_count"]) for cell in cells}
    if measured != EXPECTED_CELL_COUNTS:
        raise LicenseInventoryError(f"package lock target-cell coverage drift: {measured}")
    return cells


def _source_records(root: Path) -> dict[str, dict[str, object]]:
    return {name: supply.source_record(root, path) for name, path in sorted(SOURCE_PATHS.items())}


def _normalized_observation_text(value: str) -> str:
    unix = value.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in unix.split("\n")).strip()


def _expected_observed_packages(
    candidates: list[dict[str, object]], cell_id: str
) -> dict[str, str]:
    expected = {
        str(candidate["name"]): str(candidate["version"])
        for candidate in candidates
        if cell_id in candidate["environment_ids"]
    }
    if expected.pop("setuptools", None) is None:
        raise LicenseInventoryError(
            f"reviewed package cell {cell_id} must contain excluded setuptools"
        )
    expected[str(supply.EXPECTED_PROJECT["name"])] = str(supply.EXPECTED_PROJECT["version"])
    return dict(sorted(expected.items()))


def _observed_package_records(
    runner_os: str,
    expected: dict[str, str],
    expected_gaps: dict[str, int],
) -> list[dict[str, object]]:
    rows = OBSERVED_PACKAGE_OBSERVATIONS.get(runner_os)
    if rows is None:
        raise LicenseInventoryError(f"missing observed packages for {runner_os}")
    records: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, tuple) or len(row) != 6:
            raise LicenseInventoryError(
                f"invalid observed package tuple for {runner_os} at {index}"
            )
        name, version, license_value, url, license_hash, notice_hash = row
        if not isinstance(name, str) or supply._normalise_name(name) != name:
            raise LicenseInventoryError(f"invalid observed package name for {runner_os} at {index}")
        if not isinstance(version, str) or not version:
            raise LicenseInventoryError(f"invalid observed package version for {runner_os}:{name}")
        for label, value in (("license", license_value), ("url", url)):
            if value is not None and (
                not isinstance(value, str)
                or not _normalized_observation_text(value)
                or _normalized_observation_text(value) != value
            ):
                raise LicenseInventoryError(
                    f"invalid normalized {label} observation for {runner_os}:{name}"
                )
        if isinstance(license_value, str):
            parts = [part.strip() for part in license_value.split(";") if part.strip()]
            normalized_license = "; ".join(
                sorted(set(parts), key=lambda item: (item.casefold(), item))
            )
            if normalized_license != license_value:
                raise LicenseInventoryError(f"unsorted license observation for {runner_os}:{name}")
        for label, value in (
            ("license_text_sha256", license_hash),
            ("notice_text_sha256", notice_hash),
        ):
            if value is not None and (
                not isinstance(value, str) or supply.SHA256_RE.fullmatch(value) is None
            ):
                raise LicenseInventoryError(f"invalid {label} observation for {runner_os}:{name}")
        records.append(
            {
                "license_observation": license_value,
                "license_text_sha256": license_hash,
                "name": name,
                "notice_text_sha256": notice_hash,
                "url_observation": url,
                "version": version,
            }
        )
    names = [str(record["name"]) for record in records]
    if names != sorted(names) or len(names) != len(set(names)):
        raise LicenseInventoryError(f"observed packages for {runner_os} must be sorted and unique")
    actual_versions = {str(record["name"]): str(record["version"]) for record in records}
    if actual_versions != expected:
        raise LicenseInventoryError(f"observed package coverage drift for {runner_os}")
    actual_gaps = {
        "license": sum(record["license_observation"] is None for record in records),
        "license_text": sum(record["license_text_sha256"] is None for record in records),
        "notice_text": sum(record["notice_text_sha256"] is None for record in records),
        "url": sum(record["url_observation"] is None for record in records),
    }
    if actual_gaps != expected_gaps:
        raise LicenseInventoryError(
            f"observed package metadata gaps drift for {runner_os}: {actual_gaps}"
        )
    return records


def _observed_target_records(
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for target in OBSERVED_TARGETS:
        runner_os = str(target["runner_os"])
        cell_id = str(target["cell_id"])
        expected = _expected_observed_packages(candidates, cell_id)
        metadata_gaps = target["metadata_gaps"]
        if not isinstance(metadata_gaps, dict) or set(metadata_gaps) != {
            "license",
            "license_text",
            "notice_text",
            "url",
        }:
            raise LicenseInventoryError(f"invalid observed metadata gaps for {runner_os}")
        exact_gaps = {
            str(key): _exact_int(value, f"{runner_os} metadata_gaps.{key}")
            for key, value in metadata_gaps.items()
        }
        package_count = _exact_int(target["package_count"], f"{runner_os} package_count")
        artifact = target.get("artifact")
        if not isinstance(artifact, dict):
            raise LicenseInventoryError(f"invalid artifact record for {runner_os}")
        _exact_int(artifact.get("id"), f"{runner_os} artifact.id")
        if (
            _exact_int(
                artifact.get("normalization_version"),
                f"{runner_os} artifact.normalization_version",
            )
            != EVIDENCE_NORMALIZATION_VERSION
        ):
            raise LicenseInventoryError(f"normalization version drift for {runner_os}")
        if artifact.get("normalization_algorithm") != EVIDENCE_NORMALIZATION_ALGORITHM:
            raise LicenseInventoryError(f"normalization algorithm drift for {runner_os}")
        for field in ("raw_evidence_sha256", "canonical_evidence_sha256"):
            digest = artifact.get(field)
            if not isinstance(digest, str) or supply.SHA256_RE.fullmatch(digest) is None:
                raise LicenseInventoryError(f"invalid {field} provenance for {runner_os}")
        package_observations = _observed_package_records(
            runner_os,
            expected,
            exact_gaps,
        )
        if len(package_observations) != package_count:
            raise LicenseInventoryError(f"observed package count drift for {runner_os}")
        applicable = [
            candidate for candidate in candidates if cell_id in candidate["environment_ids"]
        ]
        excluded = [candidate for candidate in applicable if candidate["name"] == "setuptools"]
        if (
            len(excluded) != 1
            or excluded[0]["version"] != EXPECTED_SETUPTOOLS_VERSION
            or excluded[0]["review_status"] != "pending"
        ):
            raise LicenseInventoryError(f"target-scoped setuptools exclusion drift for {runner_os}")
        observed_locked_names = {
            str(package["name"])
            for package in package_observations
            if package["name"] in {candidate["name"] for candidate in applicable}
        }
        if len(observed_locked_names) != len(applicable) - 1:
            raise LicenseInventoryError(f"observed locked-candidate count drift for {runner_os}")
        records.append(
            {
                **target,
                "added_observation_rows": [
                    {
                        "name": str(supply.EXPECTED_PROJECT["name"]),
                        "reason": EDITABLE_PROJECT_ADDITION_REASON,
                        "version": str(supply.EXPECTED_PROJECT["version"]),
                    }
                ],
                "applicable_lock_candidate_count": len(applicable),
                "excluded_applicable_lock_candidates": [
                    {
                        "name": "setuptools",
                        "reason": SETUPTOOLS_EXCLUSION_REASON,
                        "version": EXPECTED_SETUPTOOLS_VERSION,
                    }
                ],
                "observation_row_count": len(package_observations),
                "observed_locked_candidate_count": len(observed_locked_names),
                "package_observations": package_observations,
            }
        )
    return records


def _coverage_record(
    candidates: list[dict[str, object]], target_cells: list[dict[str, object]]
) -> dict[str, object]:
    observed_target_ids = sorted(str(target["cell_id"]) for target in OBSERVED_TARGETS)
    all_target_ids = sorted(str(cell["id"]) for cell in target_cells)
    unobserved_target_ids = sorted(set(all_target_ids) - set(observed_target_ids))
    applicable_candidates = [
        candidate
        for candidate in candidates
        if set(candidate["environment_ids"]).intersection(observed_target_ids)
    ]
    not_applicable_candidates = [
        {
            "applicable_target_ids": candidate["environment_ids"],
            "name": candidate["name"],
            "reason": NOT_APPLICABLE_REASON,
            "version": candidate["version"],
        }
        for candidate in candidates
        if not set(candidate["environment_ids"]).intersection(observed_target_ids)
    ]
    excluded_candidates = [
        candidate for candidate in applicable_candidates if candidate["name"] == "setuptools"
    ]
    observed_locked_candidates = [
        candidate for candidate in applicable_candidates if candidate["name"] != "setuptools"
    ]
    observation_row_names = {
        name
        for target_id in observed_target_ids
        for name in _expected_observed_packages(candidates, target_id)
    }
    if (
        len(observed_target_ids) != 3
        or len(unobserved_target_ids) != 9
        or len(applicable_candidates) != 48
        or len(observed_locked_candidates) != 47
        or len(observation_row_names) != 48
        or len(excluded_candidates) != 1
        or excluded_candidates[0]["name"] != "setuptools"
        or excluded_candidates[0]["version"] != EXPECTED_SETUPTOOLS_VERSION
        or not_applicable_candidates
        != [
            {
                "applicable_target_ids": [
                    "cpython-3.10-darwin-arm64",
                    "cpython-3.10-darwin-x86_64",
                    "cpython-3.10-linux-x86_64",
                    "cpython-3.10-win32-amd64",
                ],
                "name": "exceptiongroup",
                "reason": NOT_APPLICABLE_REASON,
                "version": "1.3.1",
            }
        ]
    ):
        raise LicenseInventoryError("reviewed observed/unobserved coverage drift")
    return {
        "added_observation_rows": [
            {
                "name": str(supply.EXPECTED_PROJECT["name"]),
                "reason": EDITABLE_PROJECT_ADDITION_REASON,
                "target_ids": observed_target_ids,
                "version": str(supply.EXPECTED_PROJECT["version"]),
            }
        ],
        "applicable_lock_candidate_union_count": len(applicable_candidates),
        "distribution_closure": "unproven",
        "distribution_surface_inventory": "enumerated-not-license-reviewed",
        "excluded_applicable_lock_candidates": [
            {
                "name": "setuptools",
                "reason": SETUPTOOLS_EXCLUSION_REASON,
                "target_ids": observed_target_ids,
                "version": EXPECTED_SETUPTOOLS_VERSION,
            }
        ],
        "license_observation_scope": "python-package-input-only",
        "lock_candidate_count": len(candidates),
        "not_applicable_to_observed_targets": not_applicable_candidates,
        "observation_row_union_count": len(observation_row_names),
        "observed_locked_candidate_union_count": len(observed_locked_candidates),
        "observed_target_count": len(observed_target_ids),
        "observed_target_ids": observed_target_ids,
        "unobserved_target_count": len(unobserved_target_ids),
        "unobserved_target_ids": unobserved_target_ids,
    }


def _distribution_surfaces(root: Path) -> dict[str, object]:
    ubuntu = supply._ubuntu(root)
    panda = supply._panda(root)
    fonts = supply._fonts(root)
    packaging = supply._packaging(root)
    return {
        "fonts": {"file_count": len(fonts["files"]), **fonts},
        "inventory_status": "enumerated-inputs-only-distribution-closure-unproven",
        "packaging": {
            "data_group_count": len(packaging["data_groups"]),
            **packaging,
        },
        "panda_runtime": {"file_count": len(panda["files"]), **panda},
        "ubuntu_system": {"package_count": len(ubuntu["packages"]), **ubuntu},
    }


def build_registry(root: Path = ROOT) -> dict[str, object]:
    """Build one canonical pending LIC-01A registry from reviewed sources."""

    _project, environments = supply._project_and_environments(root)
    if len(environments) != TARGET_CELL_COUNT:
        raise LicenseInventoryError(
            f"target cell count drift: {len(environments)} != {TARGET_CELL_COUNT}"
        )
    candidates = _candidate_records(root, environments)
    _validate_direct_lock_inputs(root, environments, candidates)
    target_cells = _target_cells(environments, candidates)
    cell_counts = {str(cell["id"]): int(cell["candidate_count"]) for cell in target_cells}
    if len(OBSERVED_TARGETS) != OBSERVED_TARGET_COUNT:
        raise LicenseInventoryError("observed target count drift")
    for observed in OBSERVED_TARGETS:
        if cell_counts.get(str(observed["cell_id"])) != observed["package_count"]:
            raise LicenseInventoryError(f"observed target coverage drift for {observed['id']}")
    observed_targets = _observed_target_records(candidates)
    return {
        "candidates": candidates,
        "contract": {
            "blockers": list(BLOCKERS),
            "candidate_count": CANDIDATE_COUNT,
            "compliance_status": "pending-lic-01",
            "id": "LIC-01A",
            "legal_approval": False,
            "notice_bundle_complete": False,
            "observed_target_count": OBSERVED_TARGET_COUNT,
            "public_distribution_authorized": False,
            "purpose": "deterministic inventory coverage contract; not legal approval",
            "qt_pyside_lgpl_decision": "pending",
            "target_cell_count": TARGET_CELL_COUNT,
        },
        "coverage": _coverage_record(candidates, target_cells),
        "distribution_surfaces": _distribution_surfaces(root),
        "observation_baseline": dict(OBSERVATION_BASELINE),
        "observed_targets": observed_targets,
        "schema_version": SCHEMA_VERSION,
        "sources": _source_records(root),
        "target_cells": target_cells,
    }


def canonical_json_bytes(document: dict[str, object]) -> bytes:
    return supply.canonical_json_bytes(document)


def check_committed_registry(root: Path = ROOT) -> tuple[dict[str, object], list[str]]:
    """Compare the committed registry byte-for-byte with two fresh generations."""

    errors: list[str] = []
    first = build_registry(root)
    second = build_registry(root)
    first_bytes = canonical_json_bytes(first)
    if first_bytes != canonical_json_bytes(second):
        errors.append("license inventory generation is not byte-deterministic")
    try:
        committed = supply.strict_json(root, REGISTRY_PATH)
        committed_bytes = supply.read_bytes(root, REGISTRY_PATH)
    except supply.SupplyChainInputError as exc:
        return first, [str(exc)]
    if canonical_json_bytes(committed) != committed_bytes:
        errors.append("committed license inventory is not canonical sorted JSON")
    if committed_bytes != first_bytes:
        errors.append("committed license inventory does not match reviewed sources")
    return committed, errors


def _write_output(path: Path, payload: bytes) -> None:
    if path.suffix.lower() != ".json":
        raise LicenseInventoryError("license inventory output must use a .json filename")
    candidate = Path(os.path.abspath(path))
    committed = Path(os.path.abspath(ROOT / REGISTRY_PATH))
    if candidate == committed:
        raise LicenseInventoryError(
            "generator will not overwrite the committed registry; generate elsewhere and review"
        )
    supply.write_document(path, payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Check the committed registry")
    mode.add_argument("--output", type=Path, help="Write a reviewed candidate JSON elsewhere")
    args = parser.parse_args(argv)
    try:
        if args.check:
            registry, errors = check_committed_registry(ROOT)
            if errors:
                raise LicenseInventoryError("; ".join(errors))
            print(
                "License inventory generation: PASS "
                f"({len(registry['candidates'])} candidates, "
                f"{len(registry['target_cells'])} cells, "
                f"{len(registry['observed_targets'])} observed targets, pending-lic-01)"
            )
            return 0
        document = build_registry(ROOT)
        assert args.output is not None
        _write_output(args.output, canonical_json_bytes(document))
        print(
            f"License inventory candidate written: {args.output} "
            f"({CANDIDATE_COUNT} candidates, {TARGET_CELL_COUNT} cells, "
            f"{OBSERVED_TARGET_COUNT} observed targets, pending-lic-01)"
        )
        return 0
    except (OSError, LicenseInventoryError, supply.SupplyChainInputError) as exc:
        print(f"License inventory generation failed closed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
