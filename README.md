# Binary Patcher

![CI](https://github.com/100pangci/binary_patcher/actions/workflows/ci.yml/badge.svg)
![Build](https://github.com/100pangci/binary_patcher/actions/workflows/build.yml/badge.svg)

这是一个用于生成和应用二进制补丁项目，并支持整目录补丁工作流。项目现已统一通过 HDiffPatch (`hdiffz` / `hpatchz`) 处理补丁生成与应用。

该项目因架构问题已不再维护。体验最新请看：[Rust重构版](https://github.com/100pangci/binary_patcher_rs)

支持：

- 生成整目录补丁
- 应用整目录补丁
- 一键回滚已经应用的补丁

项目底层统一使用 **HDiffPatch**（`hdiffz` / `hpatchz`）。

## 目录结构

```text
.
├─ .github/workflows/
│   ├─ ci.yml          # 每次 push/PR: ruff lint + pytest (3.10/3.11/3.12)
│   └─ build.yml       # tag v*: lint → test → Nuitka 构建 → Release
├─ scripts/
│   ├─ build.py        # Nuitka 打包 + HDiffPatch 自动下载
│   └─ build.bat       # Windows 一键构建入口
├─ src/
│   ├─ binary_patcher.py     # 核心命令行工具 (补丁生成)
│   ├─ apply_patch.py        # 自动补丁应用脚本
│   ├─ rollback_patch.py     # 自动补丁回滚脚本
│   ├─ hdiffpatch_utils.py   # HDiffPatch 工具查找与调用封装
│   └─ legacy/               # 旧版实现 (bsdiff4)
├─ tests/
│   ├─ test_binary_patcher.py  # 45 个单元测试
│   └─ test_integration.py     # 10 个全流程闭环集成测试
├─ .gitignore
├─ pyproject.toml            # 项目元数据 + ruff/pytest 配置
├─ requirements.txt
├─ requirements-build.txt    # Nuitka 构建依赖
└─ requirements-test.txt     # pytest 测试依赖
```

## 主要文件说明

- `src/binary_patcher.py`：核心命令行工具
- `src/apply_patch.py`：面向最终用户的自动补丁脚本
- `src/rollback_patch.py`：面向最终用户的自动回滚脚本
- `src/hdiffpatch_utils.py`：HDiffPatch 工具查找封装、线程数推荐、subprocess 超时控制、`is_bundled()` 运行时检测（兼容 PyInstaller / Nuitka）
- `scripts/build.py`：统一构建与发布整理脚本
- `scripts/build.bat`：Windows 下一键构建入口

## 安全特性

- **路径穿越防护**: 所有 manifest 中的路径均经过 `resolve_safe_path()` 校验，拒绝 `../` 逃逸
- **Manifest 校验**: 加载时验证字段完整性和类型，拒绝格式错误的恶意清单；校验 `format` 版本号，拒绝不兼容的未来格式
- **备份安全**: 多次打补丁时备份文件使用**时间戳后缀**，不再静默覆盖
- **SHA256 校验**: 补丁应用前后均校验文件完整性，失败自动回滚并恢复备份

## 下载什么？

请直接下载发布页里的：

- `binary_patcher_toolkit.zip`

压缩包内包含 3 个工具：

- `binary_patcher.exe`：生成补丁
- `apply_patch.exe`：应用补丁
- `rollback_patch.exe`：回滚补丁

---

## 一、生成整目录补丁

### 第一次运行

双击运行：

- `binary_patcher.exe`

程序会自动创建以下目录：

- `Old/`
- `New/`
- `Patch/`

### 准备文件

然后你只需要：

1. 把**旧版本完整目录**放进 `Old/`
2. 把**新版本/汉化后完整目录**放进 `New/`
3. 再次双击运行 `binary_patcher.exe`

### 生成结果

程序会先计算 SHA256，再按相同相对路径找出变更、新增、删除文件，并在 `Patch/` 中生成：

- `manifest.json`
- 与原目录结构一致的 `*.patch`
- 对新增文件生成 `*.new`
- `README.txt`（使用说明）

> `Patch/` 目录仅包含补丁相关文件，不嵌入 `hdiffz.exe` / `hpatchz.exe`。应用补丁时使用单独的 `apply_patch.exe`（已内嵌二进制）或 `--copy-scripts` 释放的脚本 + 二进制文件。
> 生成补丁时，程序会自动读取当前电脑的 CPU 线程数，默认会预留 1 个线程给系统，其余线程用于 HDiffPatch 多线程加速；如果机器只有 1 个线程，则仍至少使用 1 个线程运行。

### CLI 参考

`binary_patcher.exe` 支持以下用法：

| 命令 | 说明 |
|------|------|
| `(无参数)` | 默认 workspace 模式，在当前目录自动创建 `Old/` / `New/` / `Patch/` 并生成补丁 |
| `create <old> <new> <patch>` | 对两个单文件生成一个 `.patch` 补丁 |
| `apply <old> <patch> <new>` | 对单文件应用补丁，输出新文件 |
| `bundle [--base-dir .]` | 显式 workspace 模式，指定工作目录 |
| `--copy-scripts` | 额外释放 `apply_patch.py` / `rollback_patch.py` 到工作目录根 |

短选项仅需双击运行 `binary_patcher.exe` 即可开始 workspace 流程。

### --copy-scripts 参数

默认情况下不会释放 Python 脚本。如果你希望 Patch 包同时附带 `.py` 脚本（方便有 Python 的用户直接运行），可在运行时加参数：

```powershell
binary_patcher.exe --copy-scripts                # 默认 workspace 模式
binary_patcher.exe bundle --copy-scripts --base-dir .   # 显式 bundle 模式
```

启用后，工作目录根会额外生成 `apply_patch.py`、`rollback_patch.py`、`hdiffpatch_utils.py`，以及 `hdiffz.exe` / `hpatchz.exe` 二进制文件，用户可直接 `python apply_patch.py` 运行。**不推荐在正式发布中使用**，建议仅发布 `.exe`。

---

## 二、应用整包补丁

### Release 用户（推荐）

把以下内容复制到**旧版本程序根目录**：

- 整个 `Patch/` 文件夹
- `apply_patch.exe`

然后双击运行 `apply_patch.exe`。

### Python 用户

如果补丁包附带 `.py` 脚本（生成时使用了 `--copy-scripts`），把以下内容复制到**旧版本程序根目录**：

- 整个 `Patch/` 文件夹
- `apply_patch.py`、`rollback_patch.py`、`hdiffpatch_utils.py`

然后执行：

```bash
python apply_patch.py
```

程序会按照 `manifest.json` 自动：

- 校验旧文件 SHA256
- 对变更文件打补丁
- 复制新增文件
- 删除新版中已不存在的旧文件
- 为原文件生成 `*.backup_before_patch` 备份

---

## 三、回滚已经应用的补丁

### Release 用户（推荐）

如果你需要撤销已经打过的补丁，请在**旧版本程序根目录**准备：

- 整个 `Patch/` 文件夹
- `rollback_patch.exe`

然后双击运行 `rollback_patch.exe`。

### Python 用户

如果补丁包附带 `.py` 脚本，请在**旧版本程序根目录**准备：

- 整个 `Patch/` 文件夹
- `rollback_patch.py`

然后执行：

```bash
python rollback_patch.py
```

程序会按 `manifest.json` 自动：

- 恢复变更文件对应的 `*.backup_before_patch`
- 恢复被删除文件对应的 `*.backup_before_patch`
- 删除补丁新增出来的文件
- 保持原有目录结构不乱

回滚完成后，已恢复成功的 `*.backup_before_patch` 备份文件会被自动删除。

---

## 四、发布包中包含什么？

GitHub Release / GitHub Actions 产物中会提供：

- `binary_patcher.exe`
- `apply_patch.exe`
- `rollback_patch.exe`
- `binary_patcher_toolkit.zip`

其中推荐最终用户直接下载：

- `binary_patcher_toolkit.zip`

这样可以一次性拿到全部工具。

### 构建 exe

```powershell
scripts\build.bat
```

构建脚本始终从 GitHub 拉取 HDiffPatch 最新版 Windows 64 位发行包到 `bin/`（不依赖本地缓存），并在使用 **Nuitka** 打包 `binary_patcher.exe` / `apply_patch.exe` / `rollback_patch.exe` 时一并嵌入。

构建后的工具包包含：

- `binary_patcher.exe`
- `apply_patch.exe`
- `rollback_patch.exe`
- `binary_patcher_toolkit.zip`（包含以上三个 exe，便于整包分发）

构建后会输出：

- `Releases/`：Nuitka 构建后整理好的 exe 发布目录

---

## 五、CI / CD

项目使用 GitHub Actions 自动执行持续集成与发布构建。

### CI 流水线 (`ci.yml`)

每次 push 到任意分支 或 PR 到 `main` 时触发：

| Job | 环境 | 内容 |
|-----|------|------|
| **lint** | ubuntu | `ruff check src/ tests/` |
| **test (3.10, 3.11, 3.12)** | ubuntu | `pytest tests/ -v`（55 项测试） |

### 发布流水线 (`build.yml`)

推送 tag `v*` 或手动触发时执行：

```
lint → test (3.10/3.11/3.12) → Nuitka 构建 (Windows) → GitHub Release
```

### 本地运行测试

```bash
pip install -r requirements-test.txt
pytest tests/ -v
```

### 本地代码检查

```bash
pip install ruff
ruff check src/ tests/
```

---

## 六、技术栈

| 领域 | 选型 |
|------|------|
| 语言 | Python ≥ 3.10 |
| 打包工具 | Nuitka (单文件 exe) |
| 补丁引擎 | HDiffPatch (hdiffz / hpatchz) |
| 测试框架 | pytest |
| 代码检查 | ruff |
| CI/CD | GitHub Actions |
