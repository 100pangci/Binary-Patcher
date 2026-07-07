import os
import shutil
import subprocess
import sys
from pathlib import Path


HDIFFZ_NAME = "hdiffz.exe" if os.name == "nt" else "hdiffz"
HPATCHZ_NAME = "hpatchz.exe" if os.name == "nt" else "hpatchz"
DEFAULT_HDIFFZ_THREADS = 4


def _bundled_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller uses _MEIPASS, while Nuitka onefile exposes bundled files
        # relative to module paths after extraction.
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return Path(__file__).resolve().parent.parent


def _candidate_dirs() -> list[Path]:
    candidates: list[Path] = []
    bundled_base = _bundled_base_dir()
    candidates.extend(
        [
            bundled_base,
            bundled_base / "bin",
            Path(sys.executable).resolve().parent,
            Path(sys.executable).resolve().parent / "bin",
            Path.cwd(),
            Path.cwd() / "bin",
            Path(__file__).resolve().parent,
            Path(__file__).resolve().parent.parent / "bin",
        ]
    )

    unique_candidates = []
    seen = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(resolved)
    return unique_candidates


def find_hdiffpatch_tool(executable_name: str) -> str:
    for directory in _candidate_dirs():
        candidate = directory / executable_name
        if candidate.exists():
            return str(candidate)

    path_executable = shutil.which(executable_name)
    if path_executable:
        return path_executable

    searched = "\n".join(f"- {path}" for path in _candidate_dirs())
    raise FileNotFoundError(
        f"未找到 {executable_name}。请先运行构建脚本下载 HDiffPatch，"
        f"或把它放到程序同目录 / bin 目录 / PATH 中。已搜索位置:\n{searched}"
    )


def get_recommended_thread_count() -> int:
    cpu_count = os.cpu_count() or DEFAULT_HDIFFZ_THREADS
    return max(1, cpu_count - 1)


def _run_subprocess(cmd: list[str], description: str) -> None:
    try:
        subprocess.run(cmd, check=True, timeout=300, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        print(f"错误: {description} 超时 (300s)", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"错误: {description} 失败 (返回码 {e.returncode})", file=sys.stderr)
        if e.stderr:
            print(e.stderr.strip(), file=sys.stderr)
        sys.exit(1)


def run_hdiffz(old_file_path, new_file_path, patch_file_path) -> int:
    executable = find_hdiffpatch_tool(HDIFFZ_NAME)
    thread_count = get_recommended_thread_count()
    _run_subprocess(
        [
            executable,
            f"-p-{thread_count}",
            str(old_file_path),
            str(new_file_path),
            str(patch_file_path),
        ],
        f"HDiffPatch ({Path(patch_file_path).name})",
    )
    return thread_count


def run_hpatchz(old_file_path, patch_file_path, output_file_path) -> None:
    executable = find_hdiffpatch_tool(HPATCHZ_NAME)
    _run_subprocess(
        [
            executable,
            "-f",
            str(old_file_path),
            str(patch_file_path),
            str(output_file_path),
        ],
        f"应用补丁 ({Path(patch_file_path).name})",
    )