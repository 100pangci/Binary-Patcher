# apply_patch.py
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

from hdiffpatch_utils import is_bundled, run_hpatchz


MANIFEST_NAME = "manifest.json"
BACKUP_SUFFIX = ".backup_before_patch"


def print_header(title):
    print("=" * 60)
    print(f"== {title.center(54)} ==")
    print("=" * 60)
    print()


def pause_and_exit(exit_code=0):
    print("\n按 Enter 键退出...")
    try:
        input()
    except EOFError:
        pass
    sys.exit(exit_code)


def resolve_safe_path(base_dir, relative_path):
    base_resolved = Path(base_dir).resolve()
    target = (base_resolved / relative_path).resolve()
    try:
        target.relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"路径穿越检测: {relative_path} 解析后超出基础目录")
    return target


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("manifest 格式错误: 应为 JSON 对象")

    fmt = manifest.get("format", 1)
    if not isinstance(fmt, int) or fmt != 1:
        raise ValueError(f"不支持的 manifest 格式版本: {fmt}。当前工具仅支持格式版本 1。")

    for key in ("changed", "added", "deleted"):
        if not isinstance(manifest.get(key), list):
            raise ValueError(f"manifest 格式错误: '{key}' 应为数组")
    for idx, item in enumerate(manifest.get("changed", [])):
        for field in ("path", "old_sha256", "new_sha256", "patch_file"):
            if field not in item:
                raise ValueError(f"manifest changed[{idx}] 缺少字段 '{field}'")
    for idx, item in enumerate(manifest.get("added", [])):
        for field in ("path", "new_sha256", "file"):
            if field not in item:
                raise ValueError(f"manifest added[{idx}] 缺少字段 '{field}'")
    for idx, item in enumerate(manifest.get("deleted", [])):
        for field in ("path", "old_sha256"):
            if field not in item:
                raise ValueError(f"manifest deleted[{idx}] 缺少字段 '{field}'")


def sha256_of_file(file_path):
    hasher = hashlib.sha256()
    with open(file_path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def ensure_parent_dir(file_path):
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)


def load_manifest(patch_dir):
    manifest_path = patch_dir / MANIFEST_NAME
    if not manifest_path.exists():
        print(f"错误: 未找到补丁清单文件 '{manifest_path}'")
        pause_and_exit(1)

    with open(manifest_path, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def apply_binary_patch(old_file_path, patch_file_path, output_file_path):
    ensure_parent_dir(output_file_path)
    run_hpatchz(old_file_path, patch_file_path, output_file_path)


def create_backup(target_path):
    backup_path = target_path.with_name(target_path.name + BACKUP_SUFFIX)
    if backup_path.exists():
        backup_path = target_path.with_name(
            target_path.name + BACKUP_SUFFIX + f".{int(time.time())}"
        )
    shutil.copy2(target_path, backup_path)
    return backup_path


def restore_backup(backup_path, target_path):
    shutil.copy2(backup_path, target_path)


def main():
    print_header("整包自动补丁应用脚本")

    base_dir = Path.cwd()
    patch_dir = base_dir / "Patch"

    if not patch_dir.exists():
        print(f"错误: 当前目录下未找到 Patch 文件夹: {patch_dir}")
        print(f"请把 Patch 文件夹复制到旧版本根目录后，再运行 apply_patch{'exe' if is_bundled() else 'py'}。")
        print("（Release 用户请使用 apply_patch.exe，Python 用户请运行 apply_patch.py）")
        pause_and_exit(1)

    manifest = load_manifest(patch_dir)
    try:
        validate_manifest(manifest)
    except ValueError as e:
        print(f"错误: {e}")
        pause_and_exit(1)

    changed = manifest.get("changed", [])
    added = manifest.get("added", [])
    deleted = manifest.get("deleted", [])

    print(f"检测到补丁内容: 变更 {len(changed)}，新增 {len(added)}，删除 {len(deleted)}")

    for item in changed:
        relative_path = item["path"]
        try:
            target_path = resolve_safe_path(base_dir, relative_path)
            patch_file = resolve_safe_path(patch_dir, item["patch_file"])
        except ValueError as e:
            print(f"错误: {e}")
            pause_and_exit(1)

        if not target_path.exists():
            print(f"错误: 缺少需要打补丁的旧文件: {target_path}")
            pause_and_exit(1)

        current_hash = sha256_of_file(target_path)
        expected_hash = item["old_sha256"]
        if current_hash != expected_hash:
            print(f"错误: 文件校验不匹配，无法应用补丁: {relative_path}")
            print(f"- 当前 SHA256: {current_hash}")
            print(f"- 预期 SHA256: {expected_hash}")
            pause_and_exit(1)

        backup_path = create_backup(target_path)
        print(f"[变更] {relative_path}")
        print(f"  已备份到: {backup_path.name}")
        apply_binary_patch(backup_path, patch_file, target_path)

        new_hash = sha256_of_file(target_path)
        if new_hash != item["new_sha256"]:
            print(f"错误: 补丁应用后校验失败: {relative_path}")
            restore_backup(backup_path, target_path)
            print("已自动恢复原始文件。")
            pause_and_exit(1)

    for item in added:
        relative_path = item["path"]
        try:
            target_path = resolve_safe_path(base_dir, relative_path)
            source_file = resolve_safe_path(patch_dir, item["file"])
        except ValueError as e:
            print(f"错误: {e}")
            pause_and_exit(1)
        print(f"[新增] {relative_path}")
        ensure_parent_dir(target_path)
        shutil.copy2(source_file, target_path)

        new_hash = sha256_of_file(target_path)
        if new_hash != item["new_sha256"]:
            print(f"错误: 新增文件校验失败: {relative_path}")
            pause_and_exit(1)

    for item in deleted:
        relative_path = item["path"]
        try:
            target_path = resolve_safe_path(base_dir, relative_path)
        except ValueError as e:
            print(f"错误: {e}")
            pause_and_exit(1)
        if target_path.exists():
            backup_path = create_backup(target_path)
            print(f"[删除] {relative_path}")
            print(f"  已备份到: {backup_path.name}")
            target_path.unlink()

    print()
    print("整包补丁应用完成！")
    if is_bundled():
        print("如果需要回滚，请使用同目录下的 rollback_patch.exe 恢复。")
    else:
        print("如果需要回滚，请使用同目录下的 rollback_patch.py 恢复。")
    pause_and_exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n发生未预料错误: {exc}")
        import traceback

        traceback.print_exc()
        pause_and_exit(1)