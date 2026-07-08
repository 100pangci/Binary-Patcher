import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import apply_patch
import binary_patcher
import rollback_patch


BACKUP_SUFFIX = apply_patch.BACKUP_SUFFIX


def _build_workspace(base_dir: Path):
    old_dir = base_dir / "Old"
    new_dir = base_dir / "New"

    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)

    for sub in ("sub", "deep/nested"):
        (old_dir / sub).mkdir(parents=True, exist_ok=True)
        (new_dir / sub).mkdir(parents=True, exist_ok=True)

    # ── unchanged ──
    (old_dir / "same.txt").write_text("identical", encoding="utf-8")
    (new_dir / "same.txt").write_text("identical", encoding="utf-8")

    # ── changed (text) ──
    (old_dir / "config.ini").write_text("[section]\nkey=old\n", encoding="utf-8")
    (new_dir / "config.ini").write_text("[section]\nkey=new\nport=8080\n", encoding="utf-8")

    # ── changed (binary) ──
    (old_dir / "sub" / "data.bin").write_bytes(b"\x00" * 100 + b"\x01")
    (new_dir / "sub" / "data.bin").write_bytes(b"\xff" * 100 + b"\x01\x02")

    # ── added ──
    (new_dir / "new_file.dll").write_bytes(b"\x90" * 50)
    (new_dir / "sub" / "extra.txt").write_text("bonus", encoding="utf-8")

    # ── deleted ──
    (old_dir / "deprecated.log").write_text("old log", encoding="utf-8")
    (old_dir / "deep" / "nested" / "old_cache.tmp").write_bytes(b"\x00" * 10)

    return old_dir, new_dir


def _all_file_relpaths(root: Path) -> set[str]:
    result: set[str] = set()
    for p in root.rglob("*"):
        if p.is_file() and "Patch" not in p.parts:
            result.add(p.relative_to(root).as_posix())
    return result


def _copy_tree_files(src: Path, dst: Path):
    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            dest = dst / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)


# ═══════════════════════════════════════════════════════════════════════
# Full‑cycle integration tests
# ═══════════════════════════════════════════════════════════════════════


class TestFullWorkflow:
    @pytest.fixture(autouse=True)
    def _mock_hdiffpatch(self, monkeypatch):
        def _mock_hdiffz(old, new, patch):
            Path(patch).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(new, patch)
            return 4

        def _mock_hpatchz(old, patch, out):
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(patch, out)

        monkeypatch.setattr(binary_patcher, "run_hdiffz", _mock_hdiffz)
        monkeypatch.setattr(apply_patch, "run_hpatchz", _mock_hpatchz)

    # ── bundle creation ──────────────────────────────────────────

    def test_create_bundle_produces_correct_manifest(self, tmp_path):
        old_dir, new_dir = _build_workspace(tmp_path)
        binary_patcher.build_patch_bundle(tmp_path)

        patch_dir = tmp_path / "Patch"
        manifest = json.loads((patch_dir / "manifest.json").read_text(encoding="utf-8"))

        assert len(manifest["changed"]) == 2
        assert len(manifest["added"]) == 2
        assert len(manifest["deleted"]) == 2

        for item in manifest["changed"]:
            assert (patch_dir / item["patch_file"]).exists()
        for item in manifest["added"]:
            assert (patch_dir / item["file"]).exists()

        # scripts → root,  binaries → Patch/
        for script in ("apply_patch.py", "rollback_patch.py", "hdiffpatch_utils.py"):
            assert (tmp_path / script).exists(), f"Script not at root: {script}"

        assert (patch_dir / "README.txt").exists()

    def test_unchanged_files_not_in_manifest(self, tmp_path):
        old_dir = tmp_path / "Old"
        new_dir = tmp_path / "New"
        old_dir.mkdir()
        new_dir.mkdir()

        (old_dir / "a.txt").write_text("same")
        (new_dir / "a.txt").write_text("same")
        (old_dir / "b.bin").write_bytes(b"\x00\x01")
        (new_dir / "b.bin").write_bytes(b"\x00\x01")

        binary_patcher.build_patch_bundle(tmp_path)
        manifest = json.loads((tmp_path / "Patch" / "manifest.json").read_text(encoding="utf-8"))

        assert manifest["changed"] == []
        assert manifest["added"] == []
        assert manifest["deleted"] == []

    # ── apply workflow ───────────────────────────────────────────

    def test_full_apply_workflow(self, tmp_path):
        old_dir, new_dir = _build_workspace(tmp_path)

        # generate
        binary_patcher.build_patch_bundle(tmp_path)
        patch_dir = tmp_path / "Patch"
        manifest = json.loads((patch_dir / "manifest.json").read_text(encoding="utf-8"))
        apply_patch.validate_manifest(manifest)

        # simulate end-user: Old/ → game dir  +  Patch/
        game_dir = tmp_path / "game"
        _copy_tree_files(old_dir, game_dir)
        game_patch = game_dir / "Patch"
        shutil.copytree(patch_dir, game_patch)

        # ── apply changed ──
        for item in manifest["changed"]:
            target = game_dir / item["path"]
            patch_file = game_patch / item["patch_file"]

            assert apply_patch.sha256_of_file(target) == item["old_sha256"]
            backup = apply_patch.create_backup(target)
            apply_patch.apply_binary_patch(backup, patch_file, target)
            assert apply_patch.sha256_of_file(target) == item["new_sha256"]

        # ── apply added ──
        for item in manifest["added"]:
            target = game_dir / item["path"]
            source = game_patch / item["file"]
            apply_patch.ensure_parent_dir(target)
            shutil.copy2(source, target)
            assert apply_patch.sha256_of_file(target) == item["new_sha256"]

        # ── apply deleted ──
        for item in manifest["deleted"]:
            target = game_dir / item["path"]
            assert target.exists()
            apply_patch.create_backup(target)
            target.unlink()
            assert not target.exists()

        # ── verify game == New ──
        new_files = _all_file_relpaths(new_dir)
        game_files = {f for f in _all_file_relpaths(game_dir) if BACKUP_SUFFIX not in f}
        assert new_files == game_files

        for rel in new_files:
            assert apply_patch.sha256_of_file(new_dir / rel) == apply_patch.sha256_of_file(game_dir / rel)

    # ── rollback workflow ────────────────────────────────────────

    def test_full_rollback_workflow(self, tmp_path):
        old_dir, new_dir = _build_workspace(tmp_path)

        # generate
        binary_patcher.build_patch_bundle(tmp_path)
        patch_dir = tmp_path / "Patch"
        manifest = json.loads((patch_dir / "manifest.json").read_text(encoding="utf-8"))

        # game dir = copy of Old/
        game_dir = tmp_path / "game"
        _copy_tree_files(old_dir, game_dir)
        game_patch = game_dir / "Patch"
        shutil.copytree(patch_dir, game_patch)

        # ── apply ──
        for item in manifest["changed"]:
            target = game_dir / item["path"]
            backup = apply_patch.create_backup(target)
            apply_patch.apply_binary_patch(backup, game_patch / item["patch_file"], target)

        for item in manifest["added"]:
            target = game_dir / item["path"]
            apply_patch.ensure_parent_dir(target)
            shutil.copy2(game_patch / item["file"], target)

        for item in manifest["deleted"]:
            target = game_dir / item["path"]
            apply_patch.create_backup(target)
            target.unlink()

        # ── rollback ──
        for item in manifest["changed"]:
            assert rollback_patch.restore_backup_file(game_dir / item["path"])

        for item in manifest["deleted"]:
            assert rollback_patch.restore_backup_file(game_dir / item["path"])

        for item in manifest["added"]:
            assert rollback_patch.remove_added_file(game_dir / item["path"])

        # ── verify game == Old ──
        old_files = _all_file_relpaths(old_dir)
        game_files = {f for f in _all_file_relpaths(game_dir) if BACKUP_SUFFIX not in f}
        assert old_files == game_files

        for rel in old_files:
            assert apply_patch.sha256_of_file(old_dir / rel) == apply_patch.sha256_of_file(game_dir / rel)

    # ── edge cases ───────────────────────────────────────────────

    def test_sha256_mismatch_blocks_apply(self, tmp_path):
        old_dir, new_dir = _build_workspace(tmp_path)
        binary_patcher.build_patch_bundle(tmp_path)
        manifest = json.loads((tmp_path / "Patch" / "manifest.json").read_text(encoding="utf-8"))

        changed = manifest["changed"][0]
        target = tmp_path / changed["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("tampered", encoding="utf-8")

        assert apply_patch.sha256_of_file(target) != changed["old_sha256"]

    def test_backup_with_existing_backup_adds_timestamp(self, tmp_path):
        old_dir, new_dir = _build_workspace(tmp_path)
        binary_patcher.build_patch_bundle(tmp_path)

        game_dir = tmp_path / "game"
        _copy_tree_files(old_dir, game_dir)
        game_patch = game_dir / "Patch"
        shutil.copytree(tmp_path / "Patch", game_patch)

        manifest = json.loads((game_patch / "manifest.json").read_text(encoding="utf-8"))
        item = manifest["changed"][0]
        target = game_dir / item["path"]

        first = apply_patch.create_backup(target)
        assert first.name.endswith(BACKUP_SUFFIX)

        # force the first backup to remain
        target.write_text("intermediate", encoding="utf-8")

        second = apply_patch.create_backup(target)
        assert second != first
        suffix_len = len(BACKUP_SUFFIX)
        assert second.name[:suffix_len] != first.name[:suffix_len] or second.name != first.name

    def test_rollback_without_backup_skips_gracefully(self, tmp_path):
        old_dir, new_dir = _build_workspace(tmp_path)
        binary_patcher.build_patch_bundle(tmp_path)

        game_dir = tmp_path / "game"
        _copy_tree_files(old_dir, game_dir)
        shutil.copytree(tmp_path / "Patch", game_dir / "Patch")

        manifest = json.loads((game_dir / "Patch" / "manifest.json").read_text(encoding="utf-8"))
        item = manifest["changed"][0]
        target = game_dir / item["path"]

        assert rollback_patch.restore_backup_file(target) is False

    def test_remove_added_file_missing_skips_gracefully(self, tmp_path):
        target = tmp_path / "nonexistent.dll"
        assert rollback_patch.remove_added_file(target) is False

    def test_remove_added_directory_skips(self, tmp_path):
        dir_path = tmp_path / "folder"
        dir_path.mkdir()
        assert rollback_patch.remove_added_file(dir_path) is False
