from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
BUILD = ROOT / "build"
RELEASES = ROOT / "Releases"
BIN_DIR = ROOT / "bin"
PACKAGE_DIR = RELEASES / "binary_patcher_toolkit"
HDIFFPATCH_REPO_API = "https://api.github.com/repos/sisong/HDiffPatch/releases/latest"
HDIFFPATCH_REPO_URL = "https://github.com/sisong/HDiffPatch/releases"
BINARY_DESTINATION = "bin"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def _make_github_request(url: str) -> dict | None:
    """Make an authenticated GitHub API request, returning parsed JSON or None on failure."""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "BinaryPatcher-BuildScript/2.0")
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                print(f"[WARN] GitHub API rate limited (attempt {attempt + 1}/3), retrying in 10s...")
                time.sleep(10)
                continue
            print(f"[ERROR] GitHub API HTTP {e.code}: {e.reason}")
            return None
        except (urllib.error.URLError, OSError) as e:
            print(f"[ERROR] Network error: {e}")
            return None
    return None


def _get_fallback_download_url() -> str | None:
    """Fallback: scrape the releases page for a windows64 download URL (no API needed)."""
    req = urllib.request.Request(HDIFFPATCH_REPO_URL + "/latest")
    req.add_header("User-Agent", "BinaryPatcher-BuildScript/2.0")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            html = response.read().decode("utf-8")
        # Find the first .zip download URL for windows64
        import re
        patterns = [
            r'href="(/sisong/HDiffPatch/releases/download/[^"]*windows64[^"]*\.zip)"',
            r'href="(/sisong/HDiffPatch/releases/download/[^"]*win64[^"]*\.zip)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return "https://github.com" + match.group(1)
        return None
    except Exception as e:
        print(f"[ERROR] Failed to scrape releases page: {e}")
        return None


def run(command: list[str]) -> None:
    print(f"[RUN] {' '.join(command)}")
    subprocess.run(command, check=True, cwd=ROOT)


def make_relative_display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def clean() -> None:
    for path in (BUILD, RELEASES):
        if path.exists():
            shutil.rmtree(path)

def _download_and_extract_hdiffpatch(download_url: str, display_name: str) -> bool:
    """Download and extract a HDiffPatch zip archive into BIN_DIR. Returns True on success."""
    print(f"[INFO] Downloading HDiffPatch ({display_name}) from {download_url}")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        archive_path = temp_path / "hdiffpatch.zip"
        try:
            with urllib.request.urlopen(download_url, timeout=120) as response:
                archive_path.write_bytes(response.read())
        except Exception as e:
            print(f"[ERROR] Download failed: {e}")
            return False

        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(temp_path / "extract")

        # Find the windows64 directory within the extracted folder
        extracted_dirs = list((temp_path / "extract").iterdir())
        if not extracted_dirs:
            print("[ERROR] No files extracted from archive")
            return False

        extracted_root = extracted_dirs[0]
        # Try common directory names
        for candidate in ["windows64", "windows", "win64"]:
            candidate_path = extracted_root / candidate
            if candidate_path.is_dir():
                extracted_root = candidate_path
                break

        for binary_name in ["hdiffz.exe", "hpatchz.exe"]:
            binary_path = extracted_root / binary_name
            if not binary_path.exists():
                print(f"[ERROR] {binary_name} not found in extracted archive")
                return False
            target = BIN_DIR / binary_name
            shutil.copy2(binary_path, target)
            print(f"[INFO] Prepared {target}")

    return True


def ensure_hdiffpatch_binaries() -> list[Path]:
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: check if binaries already exist locally
    if all((BIN_DIR / name).exists() for name in ["hdiffz.exe", "hpatchz.exe"]):
        print("[INFO] HDiffPatch binaries already exist locally, skipping download")
        return [BIN_DIR / "hdiffz.exe", BIN_DIR / "hpatchz.exe"]

    # Step 2: try GitHub API (with token if available)
    release = _make_github_request(HDIFFPATCH_REPO_API)
    if release is not None:
        assets = release.get("assets", [])
        asset = next(
            (item for item in assets if item["name"].endswith("windows64.zip")),
            None,
        )
        if asset is not None:
            download_url = asset["browser_download_url"]
            tag_name = release.get("tag_name", "latest")
            if _download_and_extract_hdiffpatch(download_url, tag_name):
                return [BIN_DIR / "hdiffz.exe", BIN_DIR / "hpatchz.exe"]
        else:
            print("[WARN] No windows64.zip asset found in latest release")

    # Step 3: fallback - scrape the releases page
    print("[INFO] Falling back to scraping releases page...")
    fallback_url = _get_fallback_download_url()
    if fallback_url and _download_and_extract_hdiffpatch(fallback_url, "fallback"):
        return [BIN_DIR / "hdiffz.exe", BIN_DIR / "hpatchz.exe"]

    # Step 4: last resort - use a well-known URL
    KNOWN_RELEASE = "https://github.com/sisong/HDiffPatch/releases/download/v4.5.4/HDiffPatch_win64.zip"
    print(f"[INFO] Using known release URL: {KNOWN_RELEASE}")
    if _download_and_extract_hdiffpatch(KNOWN_RELEASE, "v4.5.4"):
        return [BIN_DIR / "hdiffz.exe", BIN_DIR / "hpatchz.exe"]

    raise RuntimeError(
        "Failed to download HDiffPatch binaries. "
        "Please download them manually from "
        "https://github.com/sisong/HDiffPatch/releases "
        "and place hdiffz.exe and hpatchz.exe in the bin/ directory."
    )


def build_executable(script_path: Path, exe_name: str) -> Path:
    BUILD.mkdir(parents=True, exist_ok=True)
    RELEASES.mkdir(parents=True, exist_ok=True)
    include_data_args = []
    for binary in ensure_hdiffpatch_binaries():
        include_data_args.append(
            f"--include-data-files={binary}={BINARY_DESTINATION}/{binary.name}"
        )
    if exe_name == "binary_patcher":
        for helper_file in ("apply_patch.py", "rollback_patch.py", "hdiffpatch_utils.py"):
            helper_path = SRC_DIR / helper_file
            include_data_args.append(f"--include-data-files={helper_path}={helper_file}")

    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--assume-yes-for-downloads",
        "--remove-output",
        f"--output-dir={BUILD}",
        f"--output-filename={exe_name}.exe",
        *include_data_args,
        str(script_path),
    ]

    if os.name == "nt":
        command.insert(5, "--windows-console-mode=force")

    run(
        command
    )

    built_executable = BUILD / f"{exe_name}.exe"
    release_executable = RELEASES / built_executable.name
    shutil.copy2(built_executable, release_executable)
    return release_executable


def create_release_package(executables: list[Path]) -> Path:
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    for executable in executables:
        shutil.copy2(executable, PACKAGE_DIR / executable.name)

    archive_base = RELEASES / "binary_patcher_toolkit"
    archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=PACKAGE_DIR)
    shutil.rmtree(PACKAGE_DIR)
    return Path(archive_path)


def main() -> None:
    clean()
    executables = [
        build_executable(SRC_DIR / "binary_patcher.py", "binary_patcher"),
        build_executable(SRC_DIR / "apply_patch.py", "apply_patch"),
        build_executable(SRC_DIR / "rollback_patch.py", "rollback_patch"),
    ]
    archive_path = create_release_package(executables)

    if BUILD.exists():
        shutil.rmtree(BUILD)

    print("\nBuild completed. Output directory:")
    print(f"- Releases: {make_relative_display_path(RELEASES)}")
    print(f"- Toolkit zip: {make_relative_display_path(archive_path)}")


if __name__ == "__main__":
    main()
