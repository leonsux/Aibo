# #!/bin/bash
# # ============================================================
# #  游戏搭子 AI — 一键创建虚拟环境并启动
# #  使用方法：把这个文件放到 gaming-buddy/ 目录里，然后运行：
# #    bash setup_and_run.sh
# # ============================================================

# set -e  # 任何命令失败就停止

# VENV_DIR="venv"
# PYTHON="python3"

# # Windows Git Bash / MSYS 兼容
# if command -v python &>/dev/null && ! command -v python3 &>/dev/null; then
#   PYTHON="python"
# fi

# echo ""
# echo "🎮  游戏搭子 AI — 环境初始化"
# echo "────────────────────────────────"

# # 1. 检查 Python
# echo "▶ 检查 Python 版本..."
# $PYTHON --version

# # 2. 创建虚拟环境（已存在则跳过）
# if [ ! -d "$VENV_DIR" ]; then
#   echo "▶ 创建虚拟环境 ($VENV_DIR)..."
#   $PYTHON -m venv $VENV_DIR
#   echo "  ✅ 虚拟环境创建完成"
# else
#   echo "  ⏭  虚拟环境已存在，跳过创建"
# fi

# # 3. 激活并安装依赖
# echo "▶ 安装依赖（anthropic, Pillow）..."
# if [ -f "$VENV_DIR/bin/activate" ]; then
#   # macOS / Linux
#   source $VENV_DIR/bin/activate
#   pip install --quiet --upgrade pip
#   pip install --quiet anthropic Pillow
# else
#   # Windows
#   source $VENV_DIR/Scripts/activate 2>/dev/null || \
#     $VENV_DIR/Scripts/pip install --quiet anthropic Pillow
# fi
# echo "  ✅ 依赖安装完成"

# # 4. 启动
# echo "▶ 启动游戏搭子..."
# echo "────────────────────────────────"
# $PYTHON buddy.py

#!/bin/bash
# ============================================================
#  游戏搭子 AI — macOS / Linux 一键启动
#  使用方法：在项目目录下运行 bash setup_and_run.sh
# ============================================================

set -e

VENV_DIR="venv"
PYTHON="python3"

echo ""
echo "🎮  游戏搭子 AI — 环境初始化"
echo "────────────────────────────────"

# 1. 检查 Python
echo "▶ 检查 Python 版本..."
if ! command -v $PYTHON &>/dev/null; then
  echo "❌ 未找到 Python3，请先安装：https://www.python.org/downloads/"
  exit 1
fi
$PYTHON --version

# 2. 创建虚拟环境
if [ ! -d "$VENV_DIR" ]; then
  echo "▶ 创建虚拟环境..."
  $PYTHON -m venv $VENV_DIR
  echo "  ✅ 虚拟环境创建完成"
else
  echo "  ⏭  虚拟环境已存在，跳过"
fi

# 3. 激活虚拟环境
source $VENV_DIR/bin/activate

# 4. 安装/更新依赖
echo "▶ 安装依赖..."
pip install --quiet --upgrade pip
pip install --quiet openai Pillow dashscope certifi
echo "  ✅ 依赖安装完成"

# 5. 修复 macOS SSL 证书（只在 macOS 且未配置时执行）
if [[ "$OSTYPE" == "darwin"* ]]; then
  ACTIVATE_FILE="$VENV_DIR/bin/activate"
  if ! grep -q "SSL_CERT_FILE" "$ACTIVATE_FILE"; then
    echo "▶ 修复 macOS SSL 证书..."
    CERT_PATH=$(python -c "import certifi; print(certifi.where())")
    echo "" >> "$ACTIVATE_FILE"
    echo "export SSL_CERT_FILE=$CERT_PATH" >> "$ACTIVATE_FILE"
    echo "export REQUESTS_CA_BUNDLE=$CERT_PATH" >> "$ACTIVATE_FILE"
    # 重新激活使证书生效
    source "$ACTIVATE_FILE"
    echo "  ✅ SSL 证书已修复"
  else
    echo "  ⏭  SSL 证书已配置，跳过"
  fi
fi

# 6. 启动
echo "▶ 启动游戏搭子..."
echo "────────────────────────────────"
echo "✅ 浏览器访问 http://localhost:7788 开始使用"
echo ""
python buddy.py