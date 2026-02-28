# 构建发行版（dist）

本文档说明如何在 macOS/Linux 与 Windows 上将本工程打包为可分发的 dist 目录（基于 PyInstaller 的 one-folder 方案）。

## 目录结构与入口
- 入口脚本：`run_server.py`（调用 `fundwatcher.server.run`）
- 打包规格：`FundValuationWatcher.spec`
- 输出目录：`dist/FundValuationWatcher/`
- 运行方式：`./dist/FundValuationWatcher/FundValuationWatcher`

## macOS / Linux
1. 确保已安装 Python 3.8+（建议 3.9/3.10 也可）
2. 执行打包脚本：
   ```bash
   chmod +x scripts/build_dist.sh
   ./scripts/build_dist.sh
   ```
3. 运行：
   ```bash
   ./dist/FundValuationWatcher/FundValuationWatcher
   # 启动后访问：http://localhost:8000/
   ```

## Windows（可选）
1. 安装 Python 3.8+，并在命令提示符或 PowerShell 中执行：
   ```bat
   py -m pip install --upgrade pip setuptools wheel
   py -m pip install pyinstaller
   py -m PyInstaller -y FundValuationWatcher.spec
   ```
2. 运行：
   ```bat
   .\dist\FundValuationWatcher\FundValuationWatcher.exe
   ```

## 说明与常见问题
- 跨平台构建
  - PyInstaller 不支持从 macOS 直接产出 Windows 可执行文件（需目标平台环境）。
  - 推荐方案：在 Windows 环境（实体机/虚拟机/CI）执行打包，或使用本文提供的 GitHub Actions 工作流。
- 数据文件
  - `fundwatcher/config.json` 已在 `.spec` 中作为数据文件打包。
  - 数据库（`funds.sqlite`、`users.sqlite`）首次运行会按代码中的路径自动生成；如需预置，可在打包后手动放置到 `dist/FundValuationWatcher/_internal/fundwatcher/`。
- one-folder 与 one-file
  - 当前使用 one-folder（目录收集）方式，启动更快、排障更方便。
  - 如需 one-file，可改用 `--onefile`，但需额外测试数据文件路径解析。
- 压缩发布（可选）
  ```bash
  cd dist
  zip -r FundValuationWatcher.zip FundValuationWatcher
  ```

## 运行参数
默认绑定端口 `8000`。如需改端口，可临时修改 `run_server.py` 或之后扩展为读取环境变量/配置文件。

## 在 macOS 上触发 Windows 构建（GitHub Actions）
1. 将仓库推送到 GitHub（分支 main 或 master）
2. 工作流文件：`.github/workflows/windows-dist.yml`
3. 触发方式：
   - 推送变更后自动触发（路径匹配）
   - 或在 GitHub Actions 页手动使用 workflow_dispatch
4. 产物下载：
   - 在该工作流的构建结果页面，Artifacts 中下载 `FundValuationWatcher-windows`

## Windows 本地一键脚本
在 Windows 上可使用 PowerShell 脚本：
```powershell
scripts\build_dist_windows.ps1
```
该脚本会安装 PyInstaller 并输出 `dist\FundValuationWatcher\FundValuationWatcher.exe`。
