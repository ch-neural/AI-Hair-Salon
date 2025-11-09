# 髮型照片路徑解析修復

## 🐛 問題描述

**現象**：
- ✅ 第一次換髮可能成功（運氣好）
- ❌ 第二次換髮時，生成的髮型與選擇的不一致
- ❌ 系統沒有使用用戶選擇的髮型照片

**日志證據**：
```
[TryOn] garment data-url saved /Users/.../live_tryHair/static/inputs/garment_tryon_1762666283515.jpg  ✅ 保存成功
[GeminiService] TWO-STAGE: Stage 1 - No hairstyle photo provided  ❌ 但找不到
[GeminiService] TWO-STAGE: No hairstyle photo provided (garment_image_abs=None)  ❌ 路徑為空
```

---

## 🔍 根本原因

### 數據流程

1. **前端** → 用戶點擊髮型卡片 → 發送 `garment_image_url` 到後端
2. **tryon_service.py** → 接收 data URL → 保存到 `{cwd}/static/inputs/garment_tryon_xxx.jpg`
3. **tryon_service.py** → 傳遞 `{"image_path": "static/inputs/garment_tryon_xxx.jpg"}` 給 Gemini
4. **gemini_service.py** → ❌ **路徑解析失敗**，找不到文件

### 路徑解析問題

`gemini_service.py` 原本只嘗試兩個位置：
```python
cand = self.static_dir / rel_clean           # storeTryon 的 static 目錄
cand2 = self.base_dir / "app" / "static" / rel_clean  # storeTryon app/static
```

但文件實際保存在：
```
{cwd}/static/inputs/garment_tryon_xxx.jpg   # live-demo 的 static 目錄 ❌ 沒有搜索這裡！
```

---

## 🛠️ 修復方案

### 修改 1：擴展路徑搜索範圍

在 `gemini_service.py` 的 `_resolve_static` 函數中，添加更多候選路徑：

```python
candidates = [
    self.static_dir / rel_clean,                    # 1. storeTryon static dir
    self.base_dir / "app" / "static" / rel_clean,  # 2. storeTryon app/static
    Path.cwd() / "static" / rel_clean,              # 3. live-demo static dir (NEW! ✅)
    self.base_dir / "static" / rel_clean,           # 4. base_dir/static
    Path(rel) if Path(rel).is_absolute() else None, # 5. 絕對路徑
]
```

**關鍵修復**：添加了 `Path.cwd() / "static" / rel_clean`，這會在當前工作目錄（live-demo）的 static 目錄中查找。

### 修改 2：添加詳細調試日志

```python
print(f"[GeminiService] DEBUG: Resolving garment image, rel={rel}, rel_clean={rel_clean}")
print(f"[GeminiService] DEBUG: Trying candidate {i+1}: {cand}, exists={cand.exists()}")
print(f"[GeminiService] DEBUG: Found garment image at: {cand}")
```

這樣可以清楚看到文件查找過程。

---

## 🚀 測試步驟

### 1. 重啟服務器

```bash
# 按 Ctrl+C 停止當前服務器
./start.sh
```

### 2. 第一次換髮

1. 上傳個人照片
2. **選擇髮型 A**
3. 點擊「立即換髮型」
4. 觀察終端日志

### 3. 第二次換髮（不刷新頁面）

1. **直接點擊髮型 B**（不需要重新上傳個人照）
2. 點擊「立即換髮型」
3. 觀察終端日志

### 4. 檢查日志

應該看到類似這樣的調試信息：

```
[TryOn] DEBUG: garment_image_url=data:image/jpeg;base64,...
[TryOn] garment data-url saved /Users/.../live_tryHair/static/inputs/garment_tryon_1762666283515.jpg

[GeminiService] DEBUG: garment image_path=static/inputs/garment_tryon_1762666283515.jpg
[GeminiService] DEBUG: Resolving garment image, rel=static/inputs/garment_tryon_1762666283515.jpg, rel_clean=inputs/garment_tryon_1762666283515.jpg
[GeminiService] DEBUG: Trying candidate 1: .../storeTryon/static/inputs/garment_tryon_1762666283515.jpg, exists=False
[GeminiService] DEBUG: Trying candidate 2: .../storeTryon/app/static/inputs/garment_tryon_1762666283515.jpg, exists=False
[GeminiService] DEBUG: Trying candidate 3: .../live_tryHair/static/inputs/garment_tryon_1762666283515.jpg, exists=True ✅
[GeminiService] DEBUG: Found garment image at: .../live_tryHair/static/inputs/garment_tryon_1762666283515.jpg ✅
[GeminiService] DEBUG: garment_image_abs set to: .../live_tryHair/static/inputs/garment_tryon_1762666283515.jpg ✅

[GeminiService] TWO-STAGE: Stage 1 - Added user photo (Image 1) - mime_type=image/jpeg, size=145736 bytes
[GeminiService] TWO-STAGE: Stage 1 - Added hairstyle photo (Image 2) - path=..., mime_type=image/jpeg, size=... bytes ✅
[GeminiService] TWO-STAGE: Calling Gemini LLM for text description with 3 parts (1 text + 2 images) ✅
```

**關鍵指標**：
- ✅ `exists=True` 出現在 candidate 3
- ✅ `Added hairstyle photo (Image 2)` 出現
- ✅ `3 parts (1 text + 2 images)` 表示包含了髮型照片

---

## 📊 預期結果

### 修復前（錯誤）

```
[GeminiService] TWO-STAGE: Stage 1 - No hairstyle photo provided ❌
[GeminiService] TWO-STAGE: Calling Gemini LLM for text description with 2 parts (1 text + 1 images) ❌
```

結果：LLM 自己"想象"一個髮型，與用戶選擇的不一致。

### 修復後（正確）

```
[GeminiService] DEBUG: Found garment image at: .../live_tryHair/static/inputs/garment_tryon_xxx.jpg ✅
[GeminiService] TWO-STAGE: Stage 1 - Added hairstyle photo (Image 2) ✅
[GeminiService] TWO-STAGE: Calling Gemini LLM for text description with 3 parts (1 text + 2 images) ✅
```

結果：生成的髮型與用戶選擇的髮型照片一致。

---

## 🔧 技術細節

### 為什麼需要多個候選路徑？

因為 `live_tryHair` 是一個獨立的應用，但它依賴 `storeTryon` 作為核心引擎：

```
storeTryon/
├── common/
│   └── services/
│       ├── gemini_service.py   ← 核心引擎（這裡被修改）
│       └── tryon_service.py    ← 核心引擎

live_tryHair/                     ← 獨立應用
├── static/
│   ├── garments/                ← 髮型照片庫
│   └── inputs/                  ← 臨時上傳的髮型照片（data URL 保存於此）
├── app.py                        ← 入口
└── start.sh                      ← 啟動腳本
```

當 `gemini_service.py`（位於 storeTryon）嘗試查找文件時，它的 `self.static_dir` 指向 storeTryon 的 static 目錄，而不是 live_tryHair 的。

**解決方案**：添加 `Path.cwd() / "static"` 作為候選路徑，這樣無論從哪裡啟動，都能找到當前工作目錄下的 static 文件。

---

## 🎯 相關文件

### 修改的文件

1. **`storeTryon/common/services/gemini_service.py`**
   - 修改 `_resolve_static` 函數
   - 添加調試日志
   - 擴展路徑搜索範圍

2. **`storeTryon/common/services/tryon_service.py`**
   - 已在之前添加 DEBUG 日志（用於追蹤 garment_image_url）

### 工作流程

```
用戶點擊髮型
    ↓
前端發送 data URL
    ↓
tryon_service.py 保存到 static/inputs/garment_tryon_xxx.jpg
    ↓
傳遞 {"image_path": "static/inputs/garment_tryon_xxx.jpg"}
    ↓
gemini_service.py 嘗試多個路徑查找文件
    ↓
✅ 找到：Path.cwd() / "static" / "inputs" / "garment_tryon_xxx.jpg"
    ↓
讀取髮型照片並發送給 Gemini
    ↓
生成與選擇一致的髮型
```

---

## 📝 測試後的下一步

測試完成後，請提供：

1. **完整的調試日志**（特別是 `[GeminiService] DEBUG:` 開頭的行）
2. **第二次換髮的結果**（是否與選擇的髮型一致）
3. **生成的髮型描述**（Stage 1 生成的文字描述）

如果仍有問題，日志會清楚顯示文件在哪個路徑被找到（或未找到），我可以進一步調整。

---

## ✅ 預期改進

### 修復前
- 第一次：可能成功（如果髮型來自 static/garments/）
- 第二次：失敗（髮型來自 data URL，路徑解析失敗）

### 修復後
- 第一次：成功 ✅
- 第二次：成功 ✅
- 第N次：成功 ✅

所有髮型來源（static/garments/ 或 data URL）都能正確找到！

