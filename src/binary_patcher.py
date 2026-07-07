# binary_patcher.py
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import sys

from hdiffpatch_utils import _bundled_base_dir, run_hdiffz, run_hpatchz


WORKSPACE_DIRS = ("Old", "New", "Patch")
MANIFEST_NAME = "manifest.json"
INSTRUCTIONS_NAME = "README.txt"
APPLIER_SCRIPT_NAME = "apply_patch.py"
ROLLBACK_SCRIPT_NAME = "rollback_patch.py"
HDIFFPATCH_HELPER_NAME = "hdiffpatch_utils.py"


def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def ensure_parent_dir(file_path):
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)


def sha256_of_file(file_path):
    hasher = hashlib.sha256()
    with open(file_path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def iter_files(base_dir):
    for path in sorted(base_dir.rglob("*")):
        if path.is_file():
            yield path


def relative_file_map(base_dir):
    files = {}
    for path in iter_files(base_dir):
        files[path.relative_to(base_dir).as_posix()] = path
    return files


def pause_if_needed():
    if not sys.stdin.isatty():
        return
    print("\n按 Enter 键退出...")
    try:
        input()
    except EOFError:
        pass


def display_path(path, base_dir):
    try:
        return Path(path).resolve().relative_to(Path(base_dir).resolve()).as_posix()
    except ValueError:
        return str(path)


def init_workspace(base_dir):
    created = []
    for folder_name in WORKSPACE_DIRS:
        folder_path = base_dir / folder_name
        if not folder_path.exists():
            folder_path.mkdir(parents=True, exist_ok=True)
            created.append(folder_name)

    if created:
        print("已初始化工作目录：" + ", ".join(created))

    old_dir = base_dir / "Old"
    new_dir = base_dir / "New"
    patch_dir = base_dir / "Patch"

    if not any(old_dir.rglob("*")) or not any(new_dir.rglob("*")):
        print("\n请按以下方式准备文件：")
        print(f"- 旧版本完整目录放入: {display_path(old_dir, base_dir)}")
        print(f"- 新版本完整目录放入: {display_path(new_dir, base_dir)}")
        print(f"- 生成的补丁输出到: {display_path(patch_dir, base_dir)}")
        print("\n准备完成后，再次运行本程序即可自动生成整包补丁。")
        return False

    return True


def create_patch(old_file_path, new_file_path, patch_file_path):
    try:
        ensure_parent_dir(patch_file_path)
        old_size = Path(old_file_path).stat().st_size
        new_size = Path(new_file_path).stat().st_size

        print(f"正在读取旧文件: {old_file_path}")
        print(f"正在读取新文件: {new_file_path}")
        print("正在调用 HDiffPatch 生成补丁...")
        thread_count = run_hdiffz(old_file_path, new_file_path, patch_file_path)
        patch_size = Path(patch_file_path).stat().st_size

        print("-" * 30)
        print("补丁创建成功！")
        print(f"  - 使用线程数: {thread_count}")
        print(f"  - 旧文件大小: {format_size(old_size)}")
        print(f"  - 新文件大小: {format_size(new_size)}")
        print(f"  - 补丁文件大小: {format_size(patch_size)}")
        print("-" * 30)
    except FileNotFoundError as e:
        print(f"错误: 文件未找到 - {e.filename}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"创建补丁时发生未知错误: {e}", file=sys.stderr)
        sys.exit(1)


def apply_patch(old_file_path, patch_file_path, output_file_path):
    try:
        print(f"正在读取旧文件: {old_file_path}")
        print(f"正在读取补丁文件: {patch_file_path}")

        ensure_parent_dir(output_file_path)
        print("正在调用 HDiffPatch 应用补丁...")
        run_hpatchz(old_file_path, patch_file_path, output_file_path)
        output_size = Path(output_file_path).stat().st_size

        print("-" * 30)
        print("补丁应用成功！")
        print(f"  - 输出文件 '{output_file_path}' 已生成。")
        print(f"  - 输出文件大小: {format_size(output_size)}")
        print("-" * 30)
    except FileNotFoundError as e:
        print(f"错误: 文件未找到 - {e.filename}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"应用补丁时发生未知错误: {e}", file=sys.stderr)
        sys.exit(1)


def write_patch_instructions(patch_dir):
    instructions = (
        "这是由 binary_patcher 自动生成的整包补丁目录。\n\n"
        "使用方式：\n"
        "1. 将整个 Patch 文件夹复制到旧版本根目录（Old）内。\n"
        "2. 将 apply_patch.py 或 apply_patch.exe 放到旧版本根目录并运行。\n"
        "3. 程序会按 manifest.json 和原始目录结构自动完成补丁应用。\n"
    )
    (patch_dir / INSTRUCTIONS_NAME).write_text(instructions, encoding="utf-8")


def _find_script(script_name):
    source = Path(__file__).with_name(script_name)
    if source.exists():
        return source
    if getattr(sys, "frozen", False):
        source = _bundled_base_dir() / script_name
        if source.exists():
            return source
    return None


def copy_applier_script(patch_dir):
    for script_name in (APPLIER_SCRIPT_NAME, ROLLBACK_SCRIPT_NAME, HDIFFPATCH_HELPER_NAME):
        source = _find_script(script_name)
        if source:
            shutil.copy2(source, patch_dir / script_name)
        else:
            print(f"警告: 未找到 {script_name}，请手动复制到补丁目录")

    for binary_name in ("hpatchz.exe", "hdiffz.exe"):
        candidate_paths = [
            Path(__file__).resolve().parent.parent / "bin" / binary_name,
            Path.cwd() / "bin" / binary_name,
        ]
        if getattr(sys, "frozen", False):
            candidate_paths.append(_bundled_base_dir() / binary_name)
            candidate_paths.append(_bundled_base_dir() / "bin" / binary_name)
        for candidate in candidate_paths:
            if candidate.exists():
                shutil.copy2(candidate, patch_dir / binary_name)
                break


def build_patch_bundle(base_dir):
    old_dir = base_dir / "Old"
    new_dir = base_dir / "New"
    patch_dir = base_dir / "Patch"

    if patch_dir.exists():
        shutil.rmtree(patch_dir)
    patch_dir.mkdir(parents=True, exist_ok=True)

    old_files = relative_file_map(old_dir)
    new_files = relative_file_map(new_dir)
    all_paths = sorted(set(old_files) | set(new_files))

    manifest = {
        "format": 1,
        "source_root": "Old",
        "target_root": "New",
        "changed": [],
        "added": [],
        "deleted": [],
    }

    changed_count = 0
    added_count = 0
    deleted_count = 0

    print("开始扫描 Old / New 并计算 SHA256...")

    for relative_path in all_paths:
        old_path = old_files.get(relative_path)
        new_path = new_files.get(relative_path)

        if old_path and new_path:
            old_hash = sha256_of_file(old_path)
            new_hash = sha256_of_file(new_path)
            if old_hash == new_hash:
                continue

            patch_output = patch_dir / f"{relative_path}.patch"
            print(f"[变更] {relative_path}")
            create_patch(old_path, new_path, patch_output)
            manifest["changed"].append(
                {
                    "path": relative_path,
                    "old_sha256": old_hash,
                    "new_sha256": new_hash,
                    "patch_file": f"{relative_path}.patch",
                }
            )
            changed_count += 1
            continue

        if new_path and not old_path:
            added_output = patch_dir / f"{relative_path}.new"
            ensure_parent_dir(added_output)
            shutil.copy2(new_path, added_output)
            new_hash = sha256_of_file(new_path)
            print(f"[新增] {relative_path}")
            manifest["added"].append(
                {
                    "path": relative_path,
                    "new_sha256": new_hash,
                    "file": f"{relative_path}.new",
                }
            )
            added_count += 1
            continue

        if old_path and not new_path:
            old_hash = sha256_of_file(old_path)
            print(f"[删除] {relative_path}")
            manifest["deleted"].append(
                {
                    "path": relative_path,
                    "old_sha256": old_hash,
                }
            )
            deleted_count += 1

    (patch_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_patch_instructions(patch_dir)
    copy_applier_script(patch_dir)

    print("\n补丁包生成完成！")
    print(f"- 变更文件: {changed_count}")
    print(f"- 新增文件: {added_count}")
    print(f"- 删除文件: {deleted_count}")
    print(f"- 输出目录: {patch_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="一个用于创建和应用二进制文件补丁的工具。",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用的命令")

    parser_create = subparsers.add_parser("create", help="比较两个文件并创建一个补丁文件。")
    parser_create.add_argument("old_file", help="旧版本（原始）文件路径")
    parser_create.add_argument("new_file", help="新版本文件路径")
    parser_create.add_argument("patch_file", help="要生成的补丁文件路径")

    parser_apply = subparsers.add_parser("apply", help="将补丁应用到旧文件以生成新文件。")
    parser_apply.add_argument("old_file", help="旧版本（原始）文件路径")
    parser_apply.add_argument("patch_file", help="要应用的补丁文件路径")
    parser_apply.add_argument("output_file", help="还原后输出的新文件路径")

    parser_bundle = subparsers.add_parser("bundle", help="按 Old/New/Patch 目录工作流生成整包补丁。")
    parser_bundle.add_argument("--base-dir", default=".", help="包含 Old/New/Patch 的工作目录")

    args = parser.parse_args()

    if args.command == "create":
        create_patch(args.old_file, args.new_file, args.patch_file)
        return

    if args.command == "apply":
        apply_patch(args.old_file, args.patch_file, args.output_file)
        return

    if args.command == "bundle":
        build_patch_bundle(Path(args.base_dir).resolve())
        return

    base_dir = Path.cwd()
    if init_workspace(base_dir):
        build_patch_bundle(base_dir)
    pause_if_needed()


if __name__ == "__main__":
    main()
