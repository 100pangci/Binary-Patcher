import json
import shutil
import sys
from pathlib import Path

MANIFEST_NAME = "manifest.json"
BACKUP_SUFFIX = ".backup_before_patch"


def resolve_safe_path(base_dir, relative_path):
    base_resolved = Path(base_dir).resolve()
    target = (base_resolved / relative_path).resolve()
    try:
        target.relative_to(base_resolved)
    except ValueError:
        raise ValueError(f"路径穿越检测: {relative_path} 解析后超出基础目录")
    return target


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


def load_manifest(patch_dir):
    manifest_path = patch_dir / MANIFEST_NAME
    if not manifest_path.exists():
        print(f"错误: 未找到补丁清单文件 '{manifest_path}'")
        pause_and_exit(1)

    with open(manifest_path, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def ensure_parent_dir(file_path):
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)


def restore_backup_file(target_path: Path) -> bool:
    backup_path = target_path.with_name(target_path.name + BACKUP_SUFFIX)
    if not backup_path.exists():
        print(f"  跳过：未找到备份文件 {backup_path.name}")
        return False

    ensure_parent_dir(target_path)
    shutil.copy2(backup_path, target_path)
    backup_path.unlink()
    print(f"  已恢复备份: {backup_path.name} -> {target_path.name}")
    return True


def remove_added_file(target_path: Path) -> bool:
    if not target_path.exists():
        print(f"  跳过：新增文件不存在 {target_path}")
        return False

    if target_path.is_dir():
        print(f"  跳过：目标是目录，未删除 {target_path}")
        return False

    target_path.unlink()
    print(f"  已删除新增文件: {target_path}")
    return True


def main():
    print_header("整包补丁回滚脚本")

    base_dir = Path.cwd()
    patch_dir = base_dir / "Patch"

    if not patch_dir.exists():
        print(f"错误: 当前目录下未找到 Patch 文件夹: {patch_dir}")
        print("请把 Patch 文件夹复制到旧版本根目录后，再运行 rollback_patch.py / rollback_patch.exe。")
        pause_and_exit(1)

    manifest = load_manifest(patch_dir)
    changed = manifest.get("changed", [])
    added = manifest.get("added", [])
    deleted = manifest.get("deleted", [])

    print(f"检测到可回滚内容: 变更 {len(changed)}，新增 {len(added)}，删除 {len(deleted)}")

    restored_count = 0
    removed_count = 0

    for item in changed:
        relative_path = item["path"]
        try:
            target_path = resolve_safe_path(base_dir, relative_path)
        except ValueError as e:
            print(f"错误: {e}")
            pause_and_exit(1)
        print(f"[恢复变更] {relative_path}")
        if restore_backup_file(target_path):
            restored_count += 1

    for item in deleted:
        relative_path = item["path"]
        try:
            target_path = resolve_safe_path(base_dir, relative_path)
        except ValueError as e:
            print(f"错误: {e}")
            pause_and_exit(1)
        print(f"[恢复删除] {relative_path}")
        if restore_backup_file(target_path):
            restored_count += 1

    for item in added:
        relative_path = item["path"]
        try:
            target_path = resolve_safe_path(base_dir, relative_path)
        except ValueError as e:
            print(f"错误: {e}")
            pause_and_exit(1)
        print(f"[删除新增] {relative_path}")
        if remove_added_file(target_path):
            removed_count += 1

    print()
    print("补丁回滚完成！")
    print(f"- 恢复备份文件: {restored_count}")
    print(f"- 删除新增文件: {removed_count}")
    print("说明：已恢复的 *.backup_before_patch 备份文件会被自动删除。")
    pause_and_exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n发生未预料错误: {exc}")
        import traceback

        traceback.print_exc()
        pause_and_exit(1)