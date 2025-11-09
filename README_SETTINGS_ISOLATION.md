# Live Demo 設定檔隔離確認

## 確認事項 ✅

### 1. 設定檔案位置
- **寫入位置**：`live-demo/data/settings.json` ✅
- **讀取位置**：**僅** `live-demo/data/settings.json` ✅
- **不會讀取**：上層的 `data/settings.json` 或其他來源 ✅

### 2. 實作細節

#### 2.1 自動創建預設設定檔 (`config.py`)
```python
# 在 LiveDemoConfig.load() 中：
if not config.settings_file.exists():
    default_settings = {
        "GEMINI_API_KEY": "",
        "GEMINI_MODEL": "gemini-2.5-flash-image",
        "GEMINI_LLM": "gemini-2.5-flash",
        "GEMINI_SAFETY_SETTINGS": "BLOCK_ONLY_HIGH",
        "KLINGAI_VIDEO_ACCESS_KEY": "",
        "KLINGAI_VIDEO_SECRET_KEY": "",
        "KLINGAI_VIDEO_MODEL": "kling-v2-5-turbo",
        "KLINGAI_VIDEO_MODE": "std",
        "KLINGAI_VIDEO_DURATION": "5",
        "VENDOR_TRYON": "Gemini"
    }
    config.settings_file.write_text(...)
```

**效果**：
- 首次啟動時自動創建預設設定檔
- 確保 live-demo 始終有自己的設定檔
- 不依賴上層的設定檔

#### 2.2 明確指定設定檔路徑 (`services/tryon_provider.py`)
```python
def __init__(self, project_root: Path, demo_root: Path) -> None:
    # 只使用 live-demo 本地的設定檔，不使用上層的設定
    settings_path = demo_root / "data" / "settings.json"
    self._service = TryOnService(
        base_dir=str(project_root),
        settings_json_path=str(settings_path)  # 明確指定
    )
```

**效果**：
- TryOnService、GeminiService、KlingAIService 都會使用指定的設定檔
- 不會 fallback 到其他位置

#### 2.3 移除 Fallback 機制 (`services/tryon_provider.py`)
```python
def _apply_local_settings(self, project_root: Path, demo_root: Path) -> None:
    # 只讀取 live-demo 本地的設定檔，不 fallback 到上層
    local_path = demo_root / "data" / "settings.json"
    settings = self._load_settings(local_path)
    if not settings:
        print(f"[LiveDemoTryOnProvider] 未找到設定檔或設定為空: {local_path}")
        return
    # 移除了原來的 parent_path fallback
```

**效果**：
- 不會嘗試讀取上層的設定檔
- 保持完全獨立

#### 2.4 後台 API 讀寫 (`routes/admin.py`)
```python
@admin_bp.get("/settings/data")
def get_settings():
    config = _config()
    settings_file = config.data_dir / "settings.json"
    # 讀取 live-demo/data/settings.json

@admin_bp.post("/settings/data")
def update_settings():
    config = _config()
    settings_file = config.data_dir / "settings.json"
    # 寫入 live-demo/data/settings.json
```

**效果**：
- 所有後台操作都針對 live-demo 本地的設定檔

### 3. 測試驗證

#### 3.1 自動創建測試
```bash
# 刪除設定檔
rm live-demo/data/settings.json

# 啟動服務器
python app.py
# 輸出：[LiveDemoConfig] 已創建預設設定檔: .../live-demo/data/settings.json ✅
```

#### 3.2 隔離性測試
```bash
# 檢查設定檔內容
cat live-demo/data/settings.json
# 確認包含所有預設設定 ✅

# 修改上層設定檔（如果存在）
# live-demo 不會受影響 ✅
```

### 4. 設定檔結構

```json
{
  "GEMINI_API_KEY": "",
  "GEMINI_MODEL": "gemini-2.5-flash-image",
  "GEMINI_LLM": "gemini-2.5-flash",
  "GEMINI_SAFETY_SETTINGS": "BLOCK_ONLY_HIGH",
  "KLINGAI_VIDEO_ACCESS_KEY": "",
  "KLINGAI_VIDEO_SECRET_KEY": "",
  "KLINGAI_VIDEO_MODEL": "kling-v2-5-turbo",
  "KLINGAI_VIDEO_MODE": "std",
  "KLINGAI_VIDEO_DURATION": "5",
  "VENDOR_TRYON": "Gemini"
}
```

### 5. 使用流程

1. **首次啟動**
   ```bash
   cd live-demo
   python app.py
   ```
   - 自動創建 `data/settings.json` 與預設值

2. **透過後台設定**
   - 訪問 `http://127.0.0.1:5055/admin/login`
   - 登入後點選「系統設定」
   - 修改設定並儲存
   - 重啟服務以套用變更

3. **手動編輯**
   ```bash
   vim live-demo/data/settings.json
   ```
   - 直接編輯設定檔也可以

### 6. 關鍵特性

✅ **完全獨立**：live-demo 有自己的 settings.json
✅ **不會 Fallback**：不讀取上層或其他來源的設定
✅ **自動初始化**：首次啟動自動創建預設設定
✅ **後台管理**：可透過 Web 介面編輯所有設定
✅ **包含 Safety Settings**：可設定 Gemini 安全等級

### 7. 注意事項

⚠️ **修改設定後需要重啟服務**
```bash
# 重啟方式
lsof -ti:5055 | xargs kill -9
cd live-demo && python app.py
```

⚠️ **API Keys 安全性**
- settings.json 包含敏感資訊
- 建議加入 .gitignore
- 定期備份

⚠️ **預設值**
- 如果刪除 settings.json，會重新創建預設值
- API Keys 預設為空，需要手動設定

## 總結

Live demo 現在是**完全獨立**的應用程式：
- ✅ 有自己的設定檔 (`live-demo/data/settings.json`)
- ✅ 不依賴上層專案的設定
- ✅ 可透過後台完整管理所有設定
- ✅ 包含 Safety Settings 等進階設定

