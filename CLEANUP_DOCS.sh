#!/bin/bash
# 整理文档：移动有价值的文档到 docs/ 目录，删除临时文档

cd "$(dirname "$0")"

echo "=========================================="
echo "整理项目文档"
echo "=========================================="

# 创建 docs 目录
mkdir -p docs

echo ""
echo "步骤 1: 移动有价值的文档到 docs/ 目录..."

# 移动值得保留的文档
mv README_TWO_STAGE_MODE.md docs/ 2>/dev/null && echo "✅ 移动 README_TWO_STAGE_MODE.md"

echo ""
echo "步骤 2: 删除开发过程的临时文档..."

# 删除开发过程的临时文档
rm -f PHOTO_ROTATION_FEATURE.md && echo "✅ 删除 PHOTO_ROTATION_FEATURE.md"
rm -f PROMPT_CHANGES.md && echo "✅ 删除 PROMPT_CHANGES.md"
rm -f README_FULLSCREEN_NAVIGATION.md && echo "✅ 删除 README_FULLSCREEN_NAVIGATION.md"
rm -f README_FULLSCREEN_VIEWER.md && echo "✅ 删除 README_FULLSCREEN_VIEWER.md"
rm -f README_GARMENT_IMAGE_DEBUG.md && echo "✅ 删除 README_GARMENT_IMAGE_DEBUG.md"
rm -f README_HAIR_IMAGE_PATH_FIX.md && echo "✅ 删除 README_HAIR_IMAGE_PATH_FIX.md"
rm -f README_HAIR_SYSTEM.md && echo "✅ 删除 README_HAIR_SYSTEM.md"
rm -f README_HISTORY_PASSWORD.md && echo "✅ 删除 README_HISTORY_PASSWORD.md"
rm -f README_LLM_WARNING_FIX.md && echo "✅ 删除 README_LLM_WARNING_FIX.md"
rm -f README_SETTINGS.md && echo "✅ 删除 README_SETTINGS.md"
rm -f README_SETTINGS_ISOLATION.md && echo "✅ 删除 README_SETTINGS_ISOLATION.md"
rm -f README_VIEW_SWITCHER.md && echo "✅ 删除 README_VIEW_SWITCHER.md"
rm -f VIDEO_FEATURE_UPDATE.md && echo "✅ 删除 VIDEO_FEATURE_UPDATE.md"

echo ""
echo "步骤 3: 删除上传脚本（已完成使命）..."
rm -f UPLOAD_TO_GITHUB.sh && echo "✅ 删除 UPLOAD_TO_GITHUB.sh"
rm -f CLEAN_FOR_GITHUB.sh && echo "✅ 删除 CLEAN_FOR_GITHUB.sh"

echo ""
echo "步骤 4: 查看整理后的根目录文件..."
echo "=========================================="
ls -1 *.md *.sh 2>/dev/null || echo "（没有多余的文档文件）"
echo "=========================================="

echo ""
echo "✅ 整理完成！"
echo ""
echo "保留的文件："
echo "  • README.md（主文档）"
echo "  • LICENSE（许可证）"
echo "  • docs/README_TWO_STAGE_MODE.md（技术说明）"
echo ""
echo "下一步："
echo "  1. 检查 docs/ 目录：ls -la docs/"
echo "  2. 提交更改："
echo "     git add ."
echo "     git commit -m 'docs: Clean up redundant documentation files'"
echo "     git push"
echo ""

