# apply_patch.py
import os
import sys
import shutil
import subprocess

# --- 配置区域 ---
# 您可以在这里修改配置
PATCH_TOOL_NAME = 'binary_patcher.exe'

# 脚本会按顺序在当前目录寻找下面的补丁文件，并使用找到的第一个
POSSIBLE_PATCH_FILENAMES = [
    'app.asar.patch',
    'patch.patch' # 您可以添加更多可能的补丁文件名
]

# 脚本会根据找到的补丁文件名，在下面的目录中寻找对应的原始文件
# 例如，如果找到 app.asar.patch，它会在 '.' (当前目录) 和 'resources' 目录中寻找 app.asar
SEARCH_DIRS = [
    '.',          # '.' 代表当前目录
    'resources'   # 原来的目标目录
]

# 补丁文件的后缀，用于推断原始文件名
PATCH_EXTENSION = '.patch'
# 备份文件的后缀
BACKUP_EXTENSION = '.jp.old'
# --- 配置结束 ---

def print_header(title):
    """ 打印带边框的标题 """
    print("=" * 60)
    print(f"== {title.center(54)} ==")
    print("=" * 60)
    print()

def pause_and_exit(exit_code=0):
    """ 等待用户按键后退出 """
    print("\n按 Enter 键退出...")
    input()
    sys.exit(exit_code)

def find_patch_and_target():
    """
    智能查找补丁文件和对应的目标文件。

    逻辑:
    1. 遍历 POSSIBLE_PATCH_FILENAMES 列表，查找存在的补丁文件。
    2. 找到一个补丁文件后，根据其名称推断出原始目标文件名
       (例如 'app.asar.patch' -> 'app.asar')。
    3. 遍历 SEARCH_DIRS 列表，在这些目录中查找推断出的目标文件。
    4. 如果找到匹配的一对，返回它们的路径。
    5. 如果遍历完所有可能性都找不到，返回 None。

    返回:
        tuple: (patch_file_path, target_file_path) 或 (None, None)
    """
    print("[1/4] 正在查找补丁和目标文件...")
    
    for patch_filename in POSSIBLE_PATCH_FILENAMES:
        if not os.path.exists(patch_filename):
            continue # 如果此补丁文件不存在，跳过，继续找下一个

        # 找到了一个存在的补丁文件
        print(f"      > 找到补丁文件: '{patch_filename}'")
        
        # 推断目标文件名
        if not patch_filename.endswith(PATCH_EXTENSION):
            print(f"      > 警告: 补丁文件名 '{patch_filename}' 不以 '{PATCH_EXTENSION}' 结尾，无法自动推断目标文件。跳过...")
            continue
            
        target_filename = patch_filename[:-len(PATCH_EXTENSION)]
        backup_filename = target_filename + BACKUP_EXTENSION

        print(f"      > 推断目标文件为: '{target_filename}'")

        # 在搜索目录中寻找目标文件或其备份
        for search_dir in SEARCH_DIRS:
            potential_target_path = os.path.join(search_dir, target_filename)
            potential_backup_path = os.path.join(search_dir, backup_filename)

            # 优先使用已存在的备份文件作为源文件，这可以支持重复打补丁或恢复操作
            if os.path.exists(potential_backup_path):
                print(f"      > 在 '{search_dir}' 目录中找到已存在的备份文件 '{backup_filename}'。")
                print("      > 将使用此备份文件作为补丁源。")
                return patch_filename, potential_backup_path, potential_target_path

            # 如果没有备份文件，则查找原始目标文件
            if os.path.exists(potential_target_path):
                print(f"      > 在 '{search_dir}' 目录中找到目标文件 '{target_filename}'。")
                return patch_filename, potential_target_path, None # 第三个返回值为None表示没有找到预先存在的备份

    # 如果所有循环都结束了还没找到
    return None, None, None


def main():
    """ 脚本主逻辑 """
    print_header("智能自动补丁应用脚本")

    # --- 1. 环境检查与文件发现 ---
    # 检查补丁工具
    if not os.path.exists(PATCH_TOOL_NAME):
        print(f"错误: 未找到补丁工具 '{PATCH_TOOL_NAME}'。")
        print("请确保它和本脚本在同一个目录下。")
        pause_and_exit(1)

    # 智能查找补丁和目标文件
    patch_file, source_path, final_target_path = find_patch_and_target()

    if not patch_file:
        print("\n错误: 未能找到匹配的补丁文件和目标文件。")
        print("脚本尝试了以下组合:")
        for p_name in POSSIBLE_PATCH_FILENAMES:
            if p_name.endswith(PATCH_EXTENSION):
                t_name = p_name[:-len(PATCH_EXTENSION)]
                print(f"  - 补丁: '{p_name}' -> 目标: '{t_name}' (在 {', '.join(SEARCH_DIRS)} 中查找)")
        pause_and_exit(1)

    # 如果 find_patch_and_target 找到了一个已存在的备份文件，
    # 那么 source_path 就是备份文件路径, final_target_path 是最终要生成的文件路径。
    # 如果它找到了原始文件，那么 source_path 是原始文件路径, final_target_path 为 None。
    if final_target_path is None:
        # 这是常规流程，源文件就是原始文件
        target_path = source_path
        backup_path = target_path + BACKUP_EXTENSION
    else:
        # 这是特殊流程，源文件是备份文件，目标路径已经指定
        target_path = final_target_path
        backup_path = source_path # 源文件本身就是备份

    print(f"\n      检查通过！将对 '{source_path}' 应用补丁 '{patch_file}'")
    print()

    # --- 2. 备份原始文件 ---
    print("[2/4] 正在备份原始文件...")
    try:
        # 仅当源文件不是备份文件时才需要移动（备份）
        if source_path != backup_path:
            if os.path.exists(backup_path):
                 print(f"      警告: 备份文件 '{os.path.basename(backup_path)}' 已存在，将被覆盖。")
                 os.remove(backup_path)
            shutil.move(source_path, backup_path)
            print(f"      备份成功: {os.path.basename(source_path)} -> {os.path.basename(backup_path)}")
        else:
            print(f"      已使用现有备份 '{os.path.basename(backup_path)}' 作为源，无需重复备份。")
    except Exception as e:
        print(f"错误: 备份文件时发生严重错误: {e}")
        print("操作已中断。")
        pause_and_exit(1)
    print()

    # --- 3. 应用补丁 ---
    print("[3/4] 正在应用补丁，请稍候...")
    # 补丁命令的源文件始终是备份文件
    command = [
        PATCH_TOOL_NAME,
        'apply',
        backup_path,     # 源
        patch_file,      # 补丁
        target_path      # 目标
    ]

    try:
        # 执行外部命令
        # 使用 text=True 和 encoding='utf-8' 可以更好地处理来自子进程的中文输出
        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        print("      补丁应用成功！")
        if result.stdout:
            print("      " + result.stdout.strip().replace('\n', '\n      '))
        print()
    except FileNotFoundError:
        print(f"错误: 无法执行 '{PATCH_TOOL_NAME}'。请确保文件未损坏且路径正确。")
        # 尝试恢复
        shutil.move(backup_path, source_path)
        print("      已自动从备份恢复原始文件。")
        pause_and_exit(1)
    except subprocess.CalledProcessError as e:
        # 如果补丁工具返回错误码
        print("\n!!!!! 补丁应用失败 !!!!!")
        print("补丁工具返回了错误信息:")
        print("-" * 20 + " 错误详情 " + "-" * 20)
        # e.stdout 和 e.stderr 可能是空字符串，优先打印有内容的那一个
        error_output = e.stderr.strip() if e.stderr.strip() else e.stdout.strip()
        print(error_output)
        print("-" * 52)
        print("\n正在尝试自动恢复原始文件...")
        if os.path.exists(backup_path):
            if os.path.exists(target_path):
                os.remove(target_path) # 删除打补丁失败后产生的坏文件
            # 仅当源文件不是备份文件时才需要恢复，否则等于删除备份
            if source_path != backup_path:
                shutil.move(backup_path, source_path)
                print(f"      原始文件 '{os.path.basename(source_path)}' 已从备份中恢复。")
            else:
                print("      由于源文件本身就是备份，恢复操作已跳过。")
                print(f"      失败生成的文件 '{os.path.basename(target_path)}' 已被删除。")

        pause_and_exit(1)
    
    # --- 4. 显示成功信息 ---
    print("[4/4] 操作完成！")
    print_header("成功")
    print(f"补丁 '{patch_file}' 已成功应用到 '{target_path}'。")
    print(f"原始文件已备份为 '{backup_path}'。")
    print()
    print("-------------------- 如何恢复原始文件 --------------------")
    print("如果您想撤销补丁或游戏出现问题，请按以下步骤手动恢复:")
    print()
    # 动态生成恢复指南
    target_dir = os.path.dirname(target_path)
    # 如果目录是 '.', 显示为 '当前目录'
    display_dir = "当前目录" if target_dir == '.' else f"'{target_dir}' 文件夹"
    print(f"  1. 进入 {display_dir}。")
    print(f"  2. 删除当前的 '{os.path.basename(target_path)}' 文件。")
    print(f"  3. 将 '{os.path.basename(backup_path)}' 文件重命名为 '{os.path.basename(target_path)}'。")
    print()
    print("这样就恢复到打补丁之前的状态了。")
    print("=" * 60)
    
    pause_and_exit(0)


if __name__ == '__main__':
    try:
        # 切换工作目录到脚本所在目录，确保相对路径正确
        os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))
        main()
    except Exception:
        print("\n发生了一个未预料到的严重错误！")
        import traceback
        traceback.print_exc()
        pause_and_exit(1)
