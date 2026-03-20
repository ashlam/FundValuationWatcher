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
   - 常用页面：
     - `/`：估值主页
      - `/rank`：全市场盘中估值 Top10
     - `/upload-portfolio`：个人持仓
     - `/favorites`：自选基金

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
  - 数据库（`funds.sqlite`、`users.sqlite`）首次运行会自动生成。
    - 用户库（`users.sqlite`）默认写入系统用户数据目录，可通过环境变量 `FUNDWATCHER_USERS_DB_PATH` 指定到任意路径；如检测到旧版路径 `fundwatcher/users.sqlite` 已存在，会优先沿用以避免数据丢失。
    - 用户库 schema/版本迁移由 `fundwatcher/users_db_migrations.py` 维护，启动时会基于 SQLite `PRAGMA user_version` 自动创建/升级。
    - 如需“预置空库”，建议通过运行一次程序自动生成，而不是提交任何真实数据库文件到仓库。
  - 打包产物目录（`dist/`、`build/`）可能包含运行时生成的数据库文件，建议不要提交到 GitHub；如此前已被 git 跟踪，需要手动从索引移除后再推送。
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
