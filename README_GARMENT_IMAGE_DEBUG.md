# 髮型照片未傳遞問題 - 調試指南

## 🔍 問題描述

從日志中發現：
```
[GeminiService] TWO-STAGE: Stage 1 - No hairstyle photo provided
[GeminiService] TWO-STAGE: Stage 2 - No hairstyle photo provided (garment_image_abs=None)
```

**現象**：
- ✅ 換髮型功能可以執行
- ❌ 但沒有使用您選擇的髮型照片
- ❌ LLM 自己"想象"了一個髮型（例如：long, wavy auburn hair）

**根本原因**：
髮型照片的路徑在 `tryon_service.py` 中沒有被正確找到或複製。

---

## 🛠️ 已添加的調試日志

我已經在 `tryon_service.py` 中添加了詳細的調試日志，位置在第 583-625 行：

```python
print(f"[TryOn] DEBUG: garment_image_url={garment_image_url}")
print(f"[TryOn] DEBUG: norm_url={norm_url}")
print(f"[TryOn] DEBUG: rel={rel}")
print(f"[TryOn] DEBUG: Trying source path: {candidate}, exists={candidate.exists()}")
```

這些日志會幫助我們找出：
1. 髮型照片的 URL 是什麼
2. 系統嘗試從哪些路徑讀取文件
3. 為什麼找不到文件

---

## 🚀 測試步驟

### 1. 重啟服務器

```bash
# 按 Ctrl+C 停止當前服務器
# 然後重新啟動
./start.sh
```

### 2. 執行換髮型

1. 上傳個人照片
2. **選擇一個髮型**（這是關鍵步驟！）
3. 點擊「立即換髮型」
4. 等待處理完成

### 3. 檢查終端日志

在終端中應該會看到類似這樣的調試信息：

```
[TryOn] DEBUG: garment_image_url=/static/garments/garment_xxxxx.jpg
[TryOn] DEBUG: norm_url=/static/garments/garment_xxxxx.jpg
[TryOn] DEBUG: rel=garments/garment_xxxxx.jpg
[TryOn] DEBUG: Trying source path: .../apps/web/static/garments/garment_xxxxx.jpg, exists=False
[TryOn] DEBUG: Trying source path: .../live_tryHair/static/garments/garment_xxxxx.jpg, exists=True
[TryOn] garment copied src=.../live_tryHair/static/garments/garment_xxxxx.jpg -> ...
```

### 4. 將調試信息發給我

請複製並發送以下日志部分：
- 所有包含 `[TryOn] DEBUG:` 的行
- 如果有 `[TryOn] ERROR:` 的行也請包含

---

## 🔧 代碼修改說明

### 問題根源

原代碼假設文件在這個路徑：
```
{base_dir}/apps/web/static/garments/
```

但在 live-demo 中，文件實際在：
```
{cwd}/static/garments/
```

### 修復方案

添加了多個可能的源路徑檢查：

```python
possible_sources = [
    self.base_dir / "apps" / "web" / "static" / rel,  # 原路徑（storeTryon）
    Path.cwd() / "static" / rel,                       # live-demo 路徑 ✅
    self.base_dir / "static" / rel,                    # base_dir 下的 static
]
```

系統會依次嘗試這些路徑，直到找到存在的文件。

---

## 📊 預期結果

### 成功的情況

調試日志應該顯示：
```
[TryOn] DEBUG: garment_image_url=/static/garments/garment_xxxxx.jpg
[TryOn] DEBUG: norm_url=/static/garments/garment_xxxxx.jpg
[TryOn] DEBUG: rel=garments/garment_xxxxx.jpg
[TryOn] DEBUG: Trying source path: .../apps/web/static/garments/garment_xxxxx.jpg, exists=False
[TryOn] DEBUG: Trying source path: .../live_tryHair/static/garments/garment_xxxxx.jpg, exists=True
[TryOn] garment copied src=.../live_tryHair/static/garments/garment_xxxxx.jpg -> ...
```

然後在 Gemini 日志中看到：
```
[GeminiService] TWO-STAGE: Stage 1 - Added hairstyle photo (Image 2) - path=..., mime_type=image/jpeg, size=... bytes
[GeminiService] TWO-STAGE: Calling Gemini LLM for text description with 3 parts (1 text + 2 images)
```

注意：`3 parts (1 text + 2 images)` 表示包含了髮型照片！

### 失敗的情況

如果仍然看到：
```
[TryOn] DEBUG: garment_image_url=None
```
或
```
[TryOn] ERROR: garment image not found in any source path! rel=...
```

這說明問題在更早的階段（API 路由沒有正確傳遞髮型照片）。

---

## 🎯 可能的問題情況

### 情況 1：garment_image_url 是 None

**原因**：前端沒有正確發送髮型選擇

**檢查**：
1. 確認您確實**點擊了髮型卡片**（卡片應該有高亮邊框）
2. 查看瀏覽器控制台（F12）是否有錯誤

### 情況 2：文件路徑找不到

**原因**：髮型照片文件實際不存在

**檢查**：
```bash
ls -la static/garments/
```

應該看到類似這樣的文件：
```
garment_100003756270_xxl_3a71eb84.jpg
garment_9609be5626aa1c3e_2f5c92b1.jpg
```

### 情況 3：路徑格式不對

**原因**：URL 格式不符合預期

**例如**：
- 期望：`/static/garments/garment_xxxxx.jpg`
- 實際：`http://localhost:6055/static/garments/garment_xxxxx.jpg`

---

## 📝 測試後的下一步

測試完成後，根據日志情況：

### 如果日志顯示找到了文件
→ 問題已解決！生成的髮型應該與您選擇的一致

### 如果日志顯示 garment_image_url 是 None
→ 需要檢查前端和 API 路由的數據傳遞

### 如果日志顯示路徑都不存在
→ 需要檢查髮型照片文件是否存在於 static/garments/ 目錄

---

## 🆘 如何提供反饋

請提供以下信息：

1. **完整的調試日志**（從 `[TryOn] DEBUG:` 開始的所有行）
2. **生成的髮型描述**（日志中 Stage 1 生成的描述）
3. **您選擇的髮型照片文件名**
4. **髮型照片是否存在**：
   ```bash
   ls -la static/garments/
   ```

這樣我就能準確定位問題並提供解決方案！

