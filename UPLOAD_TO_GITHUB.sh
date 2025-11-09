#!/bin/bash
# AI-Hair-Salon - 上传到 GitHub 的脚本

echo "=========================================="
echo "AI-Hair-Salon - 上传到 GitHub"
echo "=========================================="

# 切换到项目目录
cd "$(dirname "$0")"

echo ""
echo "步骤 1/6: 初始化 Git 仓库..."
git init

echo ""
echo "步骤 2/6: 添加所有文件到 Git..."
git add .

echo ""
echo "步骤 3/6: 查看将要提交的文件..."
echo "=========================================="
git status
echo "=========================================="
echo ""
echo "⚠️  请检查以上文件列表，确认："
echo "  - ❌ 没有 data/settings.json"
echo "  - ❌ 没有 .env 文件"
echo "  - ❌ 没有 API keys"
echo "  - ❌ 没有用户上传的照片"
echo "  - ❌ 没有 venv_m4/ 目录"
echo ""
read -p "确认无误？按 Enter 继续，或按 Ctrl+C 取消..."

echo ""
echo "步骤 4/6: 创建第一次提交..."
git commit -m "Initial commit: AI-Hair-Salon virtual hair try-on system

Features:
- Gemini AI-powered hair try-on
- Two-stage precision generation
- Before/After comparison viewer
- Full-screen image browser
- Photo rotation support
- Video generation (KlingAI)
- Admin dashboard
- Touch-friendly UI"

echo ""
echo "步骤 5/6: 连接到 GitHub 远程仓库..."
git branch -M main
git remote add origin https://github.com/ch-neural/AI-Hair-Salon.git

echo ""
echo "步骤 6/6: 推送代码到 GitHub..."
git push -u origin main

echo ""
echo "=========================================="
echo "✅ 上传完成！"
echo "=========================================="
echo ""
echo "访问您的项目："
echo "https://github.com/ch-neural/AI-Hair-Salon"
echo ""

