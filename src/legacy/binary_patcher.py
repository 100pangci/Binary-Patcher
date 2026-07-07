# binary_patcher.py
import argparse
import sys
import bsdiff4

def create_patch(old_file_path, new_file_path, patch_file_path):
    """
    使用 bsdiff 算法创建二进制补丁文件。
    """
    try:
        print(f"正在读取旧文件: {old_file_path}")
        with open(old_file_path, 'rb') as f_old:
            old_data = f_old.read()

        print(f"正在读取新文件: {new_file_path}")
        with open(new_file_path, 'rb') as f_new:
            new_data = f_new.read()

        print("正在计算差异并生成补丁...")
        patch_data = bsdiff4.diff(old_data, new_data)

        print(f"正在将补丁写入: {patch_file_path}")
        with open(patch_file_path, 'wb') as f_patch:
            f_patch.write(patch_data)

        print("-" * 30)
        print("补丁创建成功！")
        print(f"  - 旧文件大小: {len(old_data) / 1024:.2f} KB")
        print(f"  - 新文件大小: {len(new_data) / 1024:.2f} KB")
        print(f"  - 补丁文件大小: {len(patch_data) / 1024:.2f} KB")
        print("-" * 30)

    except FileNotFoundError as e:
        print(f"错误: 文件未找到 - {e.filename}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"创建补丁时发生未知错误: {e}", file=sys.stderr)
        sys.exit(1)

def apply_patch(old_file_path, patch_file_path, output_file_path):
    """
    应用二进制补丁文件，从旧文件还原出新文件。
    """
    try:
        print(f"正在读取旧文件: {old_file_path}")
        with open(old_file_path, 'rb') as f_old:
            old_data = f_old.read()

        print(f"正在读取补丁文件: {patch_file_path}")
        with open(patch_file_path, 'rb') as f_patch:
            patch_data = f_patch.read()

        print("正在应用补丁...")
        new_data = bsdiff4.patch(old_data, patch_data)

        print(f"正在将还原后的新文件写入: {output_file_path}")
        with open(output_file_path, 'wb') as f_output:
            f_output.write(new_data)
        
        print("-" * 30)
        print("补丁应用成功！")
        print(f"  - 输出文件 '{output_file_path}' 已生成。")
        print(f"  - 输出文件大小: {len(new_data) / 1024:.2f} KB")
        print("-" * 30)

    except FileNotFoundError as e:
        print(f"错误: 文件未找到 - {e.filename}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"应用补丁时发生未知错误: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="一个用于创建和应用二进制文件补丁的工具。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', required=True, help='可用的命令')

    # 创建 'create' 命令
    parser_create = subparsers.add_parser('create', help='比较两个文件并创建一个补丁文件。')
    parser_create.add_argument('old_file', help='旧版本（原始）文件路径')
    parser_create.add_argument('new_file', help='新版本文件路径')
    parser_create.add_argument('patch_file', help='要生成的补丁文件路径')

    # 创建 'apply' 命令
    parser_apply = subparsers.add_parser('apply', help='将补丁应用到旧文件以生成新文件。')
    parser_apply.add_argument('old_file', help='旧版本（原始）文件路径')
    parser_apply.add_argument('patch_file', help='要应用的补丁文件路径')
    parser_apply.add_argument('output_file', help='还原后输出的新文件路径')

    args = parser.parse_args()

    if args.command == 'create':
        create_patch(args.old_file, args.new_file, args.patch_file)
    elif args.command == 'apply':
        apply_patch(args.old_file, args.patch_file, args.output_file)

if __name__ == '__main__':
    main()
