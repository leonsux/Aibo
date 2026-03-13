@echo off
REM ============================================================
REM  游戏搭子 AI — Windows 一键启动
REM  双击此文件即可运行
REM ============================================================

echo.
echo  🎮  游戏搭子 AI — 环境初始化
echo  ────────────────────────────────

REM 1. 检查 Python
python --version >nul 2>&1
IF ERRORLEVEL 1 (
  echo  ❌ 未找到 Python，请先安装：https://www.python.org/downloads/
  echo     安装时记得勾选 "Add Python to PATH"
  pause
  exit /b 1
)
echo  ✅ Python 已找到

REM 2. 创建虚拟环境
IF NOT EXIST "venv\" (
  echo  ▶ 创建虚拟环境...
  python -m venv venv
  echo  ✅ 虚拟环境创建完成
) ELSE (
  echo  ⏭  虚拟环境已存在，跳过
)

REM 3. 安装依赖
echo  ▶ 安装依赖...
venv\Scripts\pip install --quiet --upgrade pip
venv\Scripts\pip install --quiet openai Pillow dashscope certifi
echo  ✅ 依赖安装完成

REM 4. 启动
echo  ▶ 启动游戏搭子...
echo  ────────────────────────────────
echo  ✅ 浏览器访问 http://localhost:7788 开始使用
echo.
venv\Scripts\python buddy.py

pause