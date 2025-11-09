#!/bin/bash
# AI-Hair-Salon - 清理用户数据，准备上传到 GitHub

echo "=========================================="
echo "AI-Hair-Salon - 清理用户数据"
echo "=========================================="

# 切换到项目目录
cd "$(dirname "$0")"

echo ""
echo "⚠️  警告：此脚本将删除以下内容："
echo "  - static/inputs/ 中的所有用户照片"
echo "  - static/outputs/ 中的所有生成结果"
echo "  - uploads/ 中的所有上传文件"
echo "  - data/tryon_history.json 的历史记录"
echo "  - data/garments.json 的髮型数据"
echo ""
echo "  保留："
echo "  + .gitkeep 文件（目录占位符）"
echo "  + data/settings.json.example（配置示例）"
echo ""
read -p "确认清理？(输入 'YES' 继续): " confirm

if [ "$confirm" != "YES" ]; then
    echo "已取消。"
    exit 0
fi

echo ""
echo "=========================================="
echo "开始清理..."
echo "=========================================="

# 备份当前数据（可选）
BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
echo ""
echo "步骤 1/8: 创建备份到 ../$BACKUP_DIR"
mkdir -p "../$BACKUP_DIR"
cp -r static/inputs "../$BACKUP_DIR/" 2>/dev/null || true
cp -r static/outputs "../$BACKUP_DIR/" 2>/dev/null || true
cp -r uploads "../$BACKUP_DIR/" 2>/dev/null || true
cp data/garments.json "../$BACKUP_DIR/" 2>/dev/null || true
cp data/tryon_history.json "../$BACKUP_DIR/" 2>/dev/null || true
cp data/settings.json "../$BACKUP_DIR/" 2>/dev/null || true
echo "✅ 备份完成（位置：../$BACKUP_DIR）"

# 清理 static/inputs/
echo ""
echo "步骤 2/8: 清理 static/inputs/"
find static/inputs/ -type f ! -name '.gitkeep' -delete 2>/dev/null || true
echo "✅ 已清理 static/inputs/（保留 .gitkeep）"

# 清理 static/outputs/
echo ""
echo "步骤 3/8: 清理 static/outputs/"
find static/outputs/ -type f ! -name '.gitkeep' -delete 2>/dev/null || true
echo "✅ 已清理 static/outputs/（保留 .gitkeep）"

# 清理 uploads/
echo ""
echo "步骤 4/8: 清理 uploads/"
find uploads/ -type f ! -name '.gitkeep' -delete 2>/dev/null || true
echo "✅ 已清理 uploads/（保留 .gitkeep）"

# 重置 data/garments.json
echo ""
echo "步骤 5/8: 重置 data/garments.json"
if [ -f "data/garments.json.init" ]; then
    cp data/garments.json.init data/garments.json.clean
    echo "✅ 已创建 data/garments.json.clean（从 .init 模板）"
else
    echo '{
  "garments": [],
  "metadata": {
    "version": "1.0",
    "created_at": "2025-01-01T00:00:00Z",
    "description": "AI-Hair-Salon hairstyle library"
  }
}' > data/garments.json.clean
    echo "✅ 已创建 data/garments.json.clean（空数据）"
fi

# 重置 data/tryon_history.json
echo ""
echo "步骤 6/8: 重置 data/tryon_history.json"
if [ -f "data/tryon_history.json.init" ]; then
    cp data/tryon_history.json.init data/tryon_history.json.clean
    echo "✅ 已创建 data/tryon_history.json.clean（从 .init 模板）"
else
    echo '{
  "history": [],
  "metadata": {
    "version": "1.0",
    "created_at": "2025-01-01T00:00:00Z",
    "description": "AI-Hair-Salon try-on history"
  }
}' > data/tryon_history.json.clean
    echo "✅ 已创建 data/tryon_history.json.clean（空历史）"
fi

# 检查 .gitignore
echo ""
echo "步骤 7/8: 检查 .gitignore"
if grep -q "data/settings.json" .gitignore 2>/dev/null; then
    echo "✅ data/settings.json 已在 .gitignore 中"
else
    echo "⚠️  警告：data/settings.json 未在 .gitignore 中！"
fi

# 验证清理结果
echo ""
echo "步骤 8/8: 验证清理结果"
echo "----------------------------------------"
echo "static/inputs/ 文件数: $(find static/inputs/ -type f | wc -l | xargs)"
echo "static/outputs/ 文件数: $(find static/outputs/ -type f | wc -l | xargs)"
echo "uploads/ 文件数: $(find uploads/ -type f | wc -l | xargs)"
echo "----------------------------------------"

echo ""
echo "=========================================="
echo "✅ 清理完成！"
echo "=========================================="
echo ""
echo "📋 下一步："
echo "1. 检查 data/garments.json.clean 和 data/tryon_history.json.clean"
echo "2. 如果满意，将它们重命名为正式文件："
echo "   mv data/garments.json.clean data/garments.json"
echo "   mv data/tryon_history.json.clean data/tryon_history.json"
echo ""
echo "3. 或者更新 .gitignore，排除原始文件，使用 .clean 文件："
echo "   # 在 .gitignore 中添加："
echo "   data/garments.json"
echo "   data/tryon_history.json"
echo ""
echo "   # 然后提交时使用 .clean 文件："
echo "   git add -f data/garments.json.clean"
echo "   git add -f data/tryon_history.json.clean"
echo ""
echo "4. 然后运行 ./UPLOAD_TO_GITHUB.sh 上传代码"
echo ""
echo "📦 备份位置：../$BACKUP_DIR"
echo ""

