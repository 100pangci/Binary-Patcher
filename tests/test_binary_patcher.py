import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import apply_patch
import binary_patcher
import rollback_patch
from hdiffpatch_utils import _bundled_base_dir, get_recommended_thread_count

# =============================================================================
# format_size
# =============================================================================

class TestFormatSize:
    def test_bytes(self):
        assert binary_patcher.format_size(512) == "512 B"

    def test_kb(self):
        assert binary_patcher.format_size(1024) == "1.00 KB"
        assert binary_patcher.format_size(1536) == "1.50 KB"

    def test_mb(self):
        result = binary_patcher.format_size(1024 * 1024)
        assert result == "1.00 MB"
        result = binary_patcher.format_size(1024 * 1024 * 2)
        assert result == "2.00 MB"

    def test_gb(self):
        result = binary_patcher.format_size(1024 * 1024 * 1024)
        assert result == "1.00 GB"

    def test_zero(self):
        assert binary_patcher.format_size(0) == "0 B"

    def test_large_gb(self):
        result = binary_patcher.format_size(int(3.5 * 1024 * 1024 * 1024))
        assert result == "3.50 GB"

# =============================================================================
# resolve_safe_path
# =============================================================================

class TestResolveSafePath:
    def test_normal_path(self, tmp_path):
        target = apply_patch.resolve_safe_path(tmp_path, "sub/file.txt")
        assert target == (tmp_path / "sub/file.txt").resolve()

    def test_normal_path_with_dot(self, tmp_path):
        target = apply_patch.resolve_safe_path(tmp_path, "./sub/file.txt")
        assert target == (tmp_path / "sub/file.txt").resolve()

    def test_same_directory(self, tmp_path):
        target = apply_patch.resolve_safe_path(tmp_path, ".")
        assert target == tmp_path.resolve()

    def test_rejects_traversal(self, tmp_path):
        with pytest.raises(ValueError, match="路径穿越"):
            apply_patch.resolve_safe_path(tmp_path, "../outside.txt")

    def test_rejects_deep_traversal(self, tmp_path):
        with pytest.raises(ValueError, match="路径穿越"):
            apply_patch.resolve_safe_path(tmp_path, "sub/../../outside.txt")

    def test_rollback_same_logic(self, tmp_path):
        target = rollback_patch.resolve_safe_path(tmp_path, "folder/file.txt")
        assert target == (tmp_path / "folder/file.txt").resolve()

    def test_rollback_rejects_traversal(self, tmp_path):
        with pytest.raises(ValueError, match="路径穿越"):
            rollback_patch.resolve_safe_path(tmp_path, "../escaped.txt")

    def test_nested_subdir(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        target = apply_patch.resolve_safe_path(tmp_path, "a/b/c/../d.txt")
        assert target == (tmp_path / "a" / "b" / "d.txt").resolve()

    def test_absolute_path_rejected(self, tmp_path):
        if sys.platform == "win32":
            with pytest.raises(ValueError, match="路径穿越"):
                apply_patch.resolve_safe_path(tmp_path, "C:/Windows/system32.dll")
        else:
            with pytest.raises(ValueError, match="路径穿越"):
                apply_patch.resolve_safe_path(tmp_path, "/etc/passwd")

# =============================================================================
# validate_manifest
# =============================================================================

class TestValidateManifest:
    def test_valid_manifest(self):
        manifest = {
            "changed": [{"path": "a.txt", "old_sha256": "a" * 64, "new_sha256": "b" * 64, "patch_file": "a.txt.patch"}],
            "added": [{"path": "b.txt", "new_sha256": "c" * 64, "file": "b.txt.new"}],
            "deleted": [{"path": "c.txt", "old_sha256": "d" * 64}],
        }
        apply_patch.validate_manifest(manifest)

    def test_not_dict(self):
        with pytest.raises(ValueError, match="应为 JSON 对象"):
            apply_patch.validate_manifest([])

    def test_changed_not_list(self):
        with pytest.raises(ValueError, match="应为数组"):
            apply_patch.validate_manifest({"changed": "not_list", "added": [], "deleted": []})

    def test_missing_path_in_changed(self):
        with pytest.raises(ValueError, match="缺少字段"):
            apply_patch.validate_manifest({
                "changed": [{"old_sha256": "a" * 64, "new_sha256": "b" * 64, "patch_file": "x.patch"}],
                "added": [], "deleted": [],
            })

    def test_missing_sha_in_added(self):
        with pytest.raises(ValueError, match="缺少字段"):
            apply_patch.validate_manifest({
                "changed": [], "added": [{"path": "x.txt", "file": "x.txt.new"}], "deleted": [],
            })

    def test_missing_old_sha_in_deleted(self):
        with pytest.raises(ValueError, match="缺少字段"):
            apply_patch.validate_manifest({
                "changed": [], "added": [], "deleted": [{"path": "x.txt"}],
            })

    def test_empty_manifest(self):
        apply_patch.validate_manifest({"changed": [], "added": [], "deleted": []})

    def test_extra_fields_ignored(self):
        manifest = {
            "changed": [{"path": "a.txt", "old_sha256": "a" * 64, "new_sha256": "b" * 64, "patch_file": "a.patch", "extra": "ignored"}],
            "added": [], "deleted": [],
        }
        apply_patch.validate_manifest(manifest)

# =============================================================================
# sha256_of_file
# =============================================================================

class TestSha256OfFile:
    def test_known_hash(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(b"hello world")
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert apply_patch.sha256_of_file(file_path) == expected

    def test_empty_file(self, tmp_path):
        file_path = tmp_path / "empty.txt"
        file_path.write_bytes(b"")
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert apply_patch.sha256_of_file(file_path) == expected

    def test_large_file(self, tmp_path):
        file_path = tmp_path / "large.bin"
        data = b"test" * 1024 * 256
        file_path.write_bytes(data)
        result = apply_patch.sha256_of_file(file_path)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_binary_data(self, tmp_path):
        file_path = tmp_path / "binary.bin"
        file_path.write_bytes(b"\x00\x01\x02\xff\xfe")
        result = apply_patch.sha256_of_file(file_path)
        assert len(result) == 64

# =============================================================================
# create_backup
# =============================================================================

class TestCreateBackup:
    def test_backup_created(self, tmp_path):
        target = tmp_path / "original.txt"
        target.write_text("content")
        backup = apply_patch.create_backup(target)
        assert backup.exists()
        assert backup.read_text() == "content"

    def test_backup_suffix(self, tmp_path):
        target = tmp_path / "file.txt"
        target.write_text("original")
        backup = apply_patch.create_backup(target)
        assert backup.name.endswith(apply_patch.BACKUP_SUFFIX)

    def test_backup_with_existing_backup(self, tmp_path):
        target = tmp_path / "file.txt"
        target.write_text("original")
        first = apply_patch.create_backup(target)
        assert first.name.endswith(apply_patch.BACKUP_SUFFIX)
        first.touch()

        target.write_text("modified")
        second = apply_patch.create_backup(target)
        assert second != first
        assert second.name.startswith("file.txt" + apply_patch.BACKUP_SUFFIX)
        assert second.exists()

# =============================================================================
# relative_file_map / iter_files
# =============================================================================

class TestFileUtils:
    def test_iter_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.txt").write_text("b")
        (tmp_path / "sub" / "subsub").mkdir()
        (tmp_path / "sub" / "subsub" / "c.txt").write_text("c")

        files = list(binary_patcher.iter_files(tmp_path))
        assert len(files) == 3

    def test_relative_file_map(self, tmp_path):
        (tmp_path / "dir1").mkdir()
        (tmp_path / "dir1" / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        mapping = binary_patcher.relative_file_map(tmp_path)
        assert "dir1/a.txt" in mapping
        assert "b.txt" in mapping
        assert mapping["dir1/a.txt"] == (tmp_path / "dir1" / "a.txt")
        assert mapping["b.txt"] == (tmp_path / "b.txt")

    def test_empty_directory(self, tmp_path):
        files = list(binary_patcher.iter_files(tmp_path))
        assert files == []

    def test_relative_file_map_empty(self, tmp_path):
        mapping = binary_patcher.relative_file_map(tmp_path)
        assert mapping == {}

# =============================================================================
# ensure_parent_dir
# =============================================================================

class TestEnsureParentDir:
    def test_creates_parent(self, tmp_path):
        target = tmp_path / "new_dir" / "sub" / "file.txt"
        apply_patch.ensure_parent_dir(target)
        assert (tmp_path / "new_dir" / "sub").exists()

    def test_existing_parent(self, tmp_path):
        target = tmp_path / "file.txt"
        apply_patch.ensure_parent_dir(target)
        assert tmp_path.exists()

# =============================================================================
# hdiffpatch_utils
# =============================================================================

class TestHdiffpatchUtils:
    def test_get_recommended_thread_count(self):
        count = get_recommended_thread_count()
        assert count >= 1
        assert isinstance(count, int)

    def test_bundled_base_dir_exists(self):
        path = _bundled_base_dir()
        assert path is not None
        assert path.exists()

# =============================================================================
# sha256_of_file from binary_patcher (the module-level function)
# =============================================================================

class TestBinaryPatcherSha256:
    def test_sha256_matches_apply_patch(self, tmp_path):
        file_path = tmp_path / "test.bin"
        file_path.write_bytes(b"test data for sha256 verification")
        bp_hash = binary_patcher.sha256_of_file(file_path)
        ap_hash = apply_patch.sha256_of_file(file_path)
        assert bp_hash == ap_hash

# =============================================================================
# Integration tests for bundle creation / build_patch_bundle
# =============================================================================

@pytest.fixture(autouse=True)
def _mock_hdiffz(monkeypatch):
    def mock_create_patch(old_file_path, new_file_path, patch_file_path):
        Path(patch_file_path).parent.mkdir(parents=True, exist_ok=True)
        Path(patch_file_path).write_bytes(b"")
        return 1
    monkeypatch.setattr(binary_patcher, "create_patch", mock_create_patch)
    monkeypatch.setattr(binary_patcher, "run_hpatchz", lambda old, patch, out: None)

class TestBuildPatchBundle:
    def test_bundle_no_changes(self, tmp_path):
        old_dir = tmp_path / "Old"
        new_dir = tmp_path / "New"
        old_dir.mkdir()
        new_dir.mkdir()

        (old_dir / "same.txt").write_text("identical")
        (new_dir / "same.txt").write_text("identical")

        binary_patcher.build_patch_bundle(tmp_path)

        patch_dir = tmp_path / "Patch"
        manifest_path = patch_dir / "manifest.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["changed"] == []
        assert manifest["added"] == []
        assert manifest["deleted"] == []

    def test_bundle_with_changes(self, tmp_path):
        old_dir = tmp_path / "Old"
        new_dir = tmp_path / "New"
        old_dir.mkdir()
        new_dir.mkdir()

        (old_dir / "modified.txt").write_text("old content")
        (new_dir / "modified.txt").write_text("new content with changes")
        (new_dir / "added.txt").write_text("new file")

        binary_patcher.build_patch_bundle(tmp_path)

        patch_dir = tmp_path / "Patch"
        manifest = json.loads((patch_dir / "manifest.json").read_text(encoding="utf-8"))
        assert len(manifest["changed"]) == 1
        assert len(manifest["added"]) == 1
        assert manifest["changed"][0]["path"] == "modified.txt"

    def test_bundle_with_deletion(self, tmp_path):
        old_dir = tmp_path / "Old"
        new_dir = tmp_path / "New"
        old_dir.mkdir()
        new_dir.mkdir()

        (old_dir / "deleted.txt").write_text("will be removed")

        binary_patcher.build_patch_bundle(tmp_path)

        patch_dir = tmp_path / "Patch"
        manifest = json.loads((patch_dir / "manifest.json").read_text(encoding="utf-8"))
        assert len(manifest["deleted"]) == 1
        assert manifest["deleted"][0]["path"] == "deleted.txt"

    def test_bundle_creates_instructions(self, tmp_path):
        old_dir = tmp_path / "Old"
        new_dir = tmp_path / "New"
        old_dir.mkdir()
        new_dir.mkdir()
        (old_dir / "f.txt").write_text("old")
        (new_dir / "f.txt").write_text("new")

        binary_patcher.build_patch_bundle(tmp_path)
        instructions = tmp_path / "Patch" / binary_patcher.INSTRUCTIONS_NAME
        assert instructions.exists()

    def test_bundle_rejects_traversal_in_manifest(self, tmp_path):
        old_dir = tmp_path / "Old"
        new_dir = tmp_path / "New"
        old_dir.mkdir()
        new_dir.mkdir()

        (old_dir / "a.txt").write_text("old")
        (new_dir / "a.txt").write_text("new")

        binary_patcher.build_patch_bundle(tmp_path)
        patch_dir = tmp_path / "Patch"
        manifest = json.loads((patch_dir / "manifest.json").read_text(encoding="utf-8"))

        manifest["changed"][0]["path"] = "../../../etc/passwd"
        (patch_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        with pytest.raises(ValueError, match="路径穿越"):
            apply_patch.resolve_safe_path(tmp_path, "../../../etc/passwd")

    def test_manifest_format(self, tmp_path):
        old_dir = tmp_path / "Old"
        new_dir = tmp_path / "New"
        old_dir.mkdir()
        new_dir.mkdir()

        (old_dir / "f.txt").write_text("old")
        (new_dir / "f.txt").write_text("new")

        binary_patcher.build_patch_bundle(tmp_path)
        manifest = json.loads((tmp_path / "Patch" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["format"] == 1
        assert manifest["source_root"] == "Old"
        assert manifest["target_root"] == "New"
