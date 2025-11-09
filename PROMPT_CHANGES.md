# AI Prompt 修改說明 - 從換衣到換髮型

## 修改概述

將系統的所有 AI prompt 從「虛擬試衣」改為「虛擬換髮型」，確保 AI 正確理解任務是更換髮型而非更換服飾。

## 修改的文件

### 1. `/storeTryon/common/services/tryon_analysis.py`

#### 修改 1: 髮型分析 Prompt
**位置**: `analyze_garment()` 函數

**修改前**:
```python
"你是一位服飾標註專家，請分析提供的服飾照片..."
"- garment_description：用中文精確描述衣物外觀、材質、圖樣。"
```

**修改後**:
```python
"你是一位髮型設計專家，請分析提供的髮型照片..."
"- garment_description：用中文精確描述髮型的長度、顏色、質感、捲度、層次等特徵。"
```

#### 修改 2: 使用者分析 Prompt
**位置**: `analyze_user()` 函數

**修改前**:
```python
"請描述人物的性別表現、身形特徵、髮型、面部朝向、姿勢、燈光氛圍與可用於換裝提示的重點。"
```

**修改後**:
```python
"請描述人物的性別表現、臉型特徵、當前髮型、面部朝向、姿勢、燈光氛圍與可用於換髮型提示的重點。"
```

#### 修改 3: 生成提示文字
**位置**: `compose_note()` 函數

**修改前**:
```python
"Completely remove the user's current outfit; dress the user in the garment described..."
```

**修改後**:
```python
"Change the user's hairstyle to match the hairstyle shown in the provided hair style reference image. Keep all other aspects (face, body, clothing, background) identical."
```

#### 修改 4: 模特處理說明
**修改前**:
```python
"Ensure the final image replaces any reference model with the user's appearance..."
```

**修改後**:
```python
"Ensure the final image uses only the hairstyle from the reference, not the person's face or body. Apply the hairstyle to the user's appearance."
```

#### 修改 5: 分析輸出標籤
**修改前**:
```python
"Garment analysis:"
"- On-body styling:"
```

**修改後**:
```python
"Hairstyle analysis:"
"- Styling notes:"
```

---

### 2. `/storeTryon/common/services/gemini_service.py`

#### 修改 1: Stage 1 描述生成 Prompt
**位置**: `_build_description_prompt()` 函數

**修改前**:
```python
"You are creating a description for a fashion product visualization."
"- Image 2: A product garment to be showcased"
"Task: Describe the FINAL RESULT - what the scene looks like with the person wearing ONLY the product garment from Image 2."
"3. THE NEW GARMENT ONLY: Describe the product garment from Image 2 in detail..."
```

**修改後**:
```python
"You are creating a description for a professional hairstyle visualization for a hair salon service."
"- Image 2: A reference hairstyle to be applied"
"Task: Describe the FINAL RESULT - what the scene looks like with the person having the new hairstyle from Image 2."
"5. THE NEW HAIRSTYLE ONLY: Describe the hairstyle from Image 2 in detail (color, length, texture, style, cut, volume)"
```

#### 修改 2: Stage 2 圖片生成 Prompt
**位置**: `_build_image_from_description_prompt()` 函數

**修改前**:
```python
"CONTEXT: This is a legitimate e-commerce virtual try-on service for fashion retail..."
"TASK: Generate a photorealistic product demonstration image showing the person wearing the described garment."
"Replace the user's existing outfit with the garment described..."
"GARMENT DESCRIPTION:"
```

**修改後**:
```python
"CONTEXT: This is a professional virtual hairstyle try-on service for hair salons and beauty services..."
"TASK: Generate a photorealistic image showing the person with the described hairstyle."
"Change ONLY the hairstyle to match the hair reference image..."
"HAIRSTYLE DESCRIPTION:"
```

#### 修改 3: 風格指南
**修改前**:
```python
"STYLE GUIDELINES (Commercial Fashion Photography Standards):"
"- Render as professional e-commerce/catalog product photography"
"- Remove all parts of the user's original clothing so only the new garment remains visible"
```

**修改後**:
```python
"STYLE GUIDELINES (Professional Hair Salon Photography Standards):"
"- Render as professional hair salon catalog/portfolio photography"
"- Change ONLY the hairstyle - keep the person's face, facial features, skin tone, body, and clothing exactly the same"
"- Do NOT change the person's clothing, accessories, makeup, or facial features"
```

#### 修改 4: 技術要求
**修改前**:
```python
"- Only replace the clothing as specified in the description"
"- Ensure the new clothing fits naturally and realistically"
```

**修改後**:
```python
"- Only change the hairstyle as specified in the description"
"- Ensure the new hairstyle fits naturally and realistically on the person's head"
"- Generate a high-quality, photorealistic result showing the person with their new hairstyle"
```

#### 修改 5: 場景上下文
**位置**: `two_stage_tryon()` 函數中的 context_prefix

**修改前**:
```python
"Context: The person is changing outfit for a lawful, normal commercial scenario — a fashion catalog/DM or e-commerce product photoshoot..."
```

**修改後**:
```python
"Context: The person is trying a new hairstyle for a professional hair salon portfolio or hairstyle demonstration..."
```

---

## 修改重點總結

### 關鍵變更

1. **任務定義**: 從「更換服飾」改為「更換髮型」
2. **保持不變項目**: 強調保持臉部、身體、服飾、背景不變，只改變髮型
3. **描述重點**: 從描述衣物材質、款式改為描述髮型長度、顏色、質感、捲度
4. **專業標準**: 從時尚電商攝影標準改為專業髮廊攝影標準
5. **分析對象**: 從分析服飾改為分析髮型特徵

### AI 理解重點

修改後的 prompt 明確告訴 AI：
- ✅ **只改變髮型**，不要動其他任何部分
- ✅ 保持人物的**臉部特徵、膚色、身體、服飾**完全相同
- ✅ 將參考圖片中的**髮型風格**應用到使用者身上
- ✅ 使用**髮廊專業攝影**的標準和風格
- ✅ 確保新髮型**自然地**貼合使用者的頭型

### 測試建議

1. 使用明顯不同髮型的參考圖片測試
2. 確認 AI 只改變髮型，保持其他部分不變
3. 檢查髮型是否自然地應用到使用者頭上
4. 驗證髮色、長度、質感是否正確遷移

---

## 相關文件

- 主要 README: `/live_tryHair/README.md`
- 系統說明: `/live_tryHair/README_HAIR_SYSTEM.md`
- 原始共用服務: `/storeTryon/common/services/`

---

**修改日期**: 2025-11-08  
**版本**: 2.0.0  
**狀態**: ✅ 已完成

