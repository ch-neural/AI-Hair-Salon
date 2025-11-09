#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "Live Demo 觸控試髮系統啟動"
echo "使用模式: TWO-STAGE (精確髮型控制)"
echo "========================================"

# 切換到 live-demo 目錄
cd "$(dirname "$0")"

# 檢查並啟動虛擬環境
if [ -d "venv_m4" ]; then
    echo "使用 venv_m4 虛擬環境"
    source venv_m4/bin/activate
elif [ -d ".venv" ]; then
    echo "使用 .venv 虛擬環境"
    source .venv/bin/activate
else
    echo "警告：未找到虛擬環境，使用系統 Python"
fi

# 檢查必要的依賴
echo "檢查依賴套件..."
python3 -c "import requests, jwt" 2>/dev/null || {
    echo "安裝缺少的依賴..."
    pip install requests PyJWT
}

# 確保必要目錄存在
mkdir -p static/inputs static/outputs static/garments data uploads

# 啟動應用
echo ""
echo "啟動 Live Demo 應用..."
echo "訪問 URL: http://localhost:6055"
echo "管理後台: http://localhost:6055/admin (帳號: admin / 密碼: storepi)"
echo ""
echo "🎯 TWO-STAGE 模式優點："
echo "  • Stage 1: LLM 理解指令 → 只改髮型"
echo "  • Stage 2: Image Model 精確生成 → 保護衣物"
echo "  • 適合換髮型等需要精確控制的任務"
echo ""
echo "按 Ctrl+C 停止服務器"
echo "========================================"

python3 app.py

