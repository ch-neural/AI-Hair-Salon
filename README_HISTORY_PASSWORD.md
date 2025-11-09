# 試衣記錄與密碼管理功能說明

本文檔說明 Live Demo 管理後台新增的試衣記錄和密碼管理功能。

## 新增功能

### 1. 試衣記錄管理

管理者可以在後台瀏覽所有試衣記錄，包含：

#### 功能特點

- **記錄列表顯示**：按時間倒序顯示所有試衣記錄
- **詳細資訊**：
  - 日期時間
  - 服飾名稱
  - 人物照片
  - 服飾照片
  - 試衣結果照片
  - 生成影片（如有）
  - 試衣狀態（成功/失敗/處理中）
  - 錯誤訊息（如有）

#### 功能操作

- **下載功能**：可下載所有相片和影片
- **刪除功能**：可刪除不需要的記錄
- **分頁瀏覽**：支援分頁，每頁顯示 20 筆記錄

#### 訪問路徑

- 路由：`/admin/history`
- 在管理後台各頁面的頂部導航都有「試衣記錄」入口

#### 資料儲存

- 記錄儲存於：`data/tryon_history.json`
- 圖片和影片儲存於：`static/inputs/` 和 `static/outputs/`

### 2. 管理員密碼修改

管理者可以修改登入密碼，提升安全性。

#### 功能特點

- **密碼驗證**：需要輸入當前密碼進行驗證
- **安全檢查**：
  - 新密碼至少 6 個字元
  - 需要確認新密碼（防止輸入錯誤）
- **持久化儲存**：密碼修改後會儲存到檔案，重啟後仍然有效

#### 訪問位置

修改密碼功能可在以下兩個地方使用：

1. **試衣記錄頁面** (`/admin/history`)
2. **系統設定頁面** (`/admin/settings`)

#### 密碼儲存

- 密碼儲存於：`data/admin.json`
- 格式：
  ```json
  {
    "username": "admin",
    "password": "your_password"
  }
  ```

#### 密碼優先順序

系統會按以下順序讀取密碼：

1. `data/admin.json` 檔案（如果存在）
2. 環境變數 `LIVE_DEMO_ADMIN_PASS`
3. 預設值 `storepi`

## 技術實現

### 後端 API

#### 試衣記錄 API

- `GET /api/admin/history?page=1&per_page=20` - 獲取試衣記錄列表
- `DELETE /api/admin/history/<record_id>` - 刪除指定記錄

#### 密碼管理 API

- `POST /admin/change-password` - 修改管理員密碼
  - Request Body:
    ```json
    {
      "current_password": "當前密碼",
      "new_password": "新密碼",
      "confirm_password": "確認新密碼"
    }
    ```

### 自動記錄機制

系統會在以下情況自動記錄試衣資訊：

1. **開始試衣**：創建記錄，狀態為 `processing`
2. **試衣成功**：更新記錄，添加結果圖片路徑，狀態改為 `success`
3. **試衣失敗**：更新記錄，添加錯誤訊息，狀態改為 `failed`
4. **生成影片**：更新記錄，添加影片路徑

### 資料庫結構

試衣記錄資料結構（`TryOnRecord`）：

```python
{
    "record_id": "唯一識別碼",
    "timestamp": "2025-11-08 12:34:56",
    "user_photo_path": "使用者照片路徑",
    "garment_photo_path": "服飾照片路徑",
    "result_photo_path": "結果照片路徑",
    "video_path": "影片路徑",
    "status": "success|failed|processing",
    "error_message": "錯誤訊息（如有）",
    "garment_name": "服飾名稱",
    "garment_id": "服飾ID"
}
```

## 檔案結構

新增和修改的檔案：

```
live_tryon/
├── services/
│   └── history_repository.py          # 試衣記錄儲存庫
├── routes/
│   ├── admin.py                        # 更新：新增密碼修改和歷史頁面路由
│   └── api.py                          # 更新：新增記錄 API 和自動記錄邏輯
├── templates/admin/
│   ├── history.html                    # 試衣記錄頁面
│   ├── dashboard.html                  # 更新：新增試衣記錄入口
│   └── settings.html                   # 更新：新增修改密碼區塊
├── static/
│   ├── js/
│   │   ├── history.js                  # 試衣記錄頁面 JS
│   │   └── settings.js                 # 更新：新增密碼修改邏輯
│   └── css/
│       └── theme.css                   # 更新：新增試衣記錄樣式
├── data/
│   ├── tryon_history.json             # 試衣記錄（自動生成）
│   └── admin.json                     # 管理員帳密（修改密碼後生成）
├── config.py                          # 更新：新增檔案路徑配置
└── app.py                             # 更新：注入歷史記錄服務
```

## 使用範例

### 查看試衣記錄

1. 登入管理後台
2. 點擊頂部導航的「試衣記錄」
3. 瀏覽所有試衣記錄
4. 點擊「下載」按鈕可下載圖片或影片
5. 點擊「刪除」按鈕可刪除不需要的記錄

### 修改密碼

1. 登入管理後台
2. 進入「系統設定」或「試衣記錄」頁面
3. 找到「修改管理員密碼」區塊
4. 輸入當前密碼
5. 輸入新密碼（至少 6 字元）
6. 確認新密碼
7. 點擊「修改密碼」按鈕
8. 修改成功後，下次登入需使用新密碼

## 注意事項

1. **密碼安全**：
   - 首次修改密碼後，建議立即重啟服務
   - 密碼會以明文儲存在 `data/admin.json`，請確保檔案權限正確

2. **記錄儲存**：
   - 試衣記錄會持續累積，建議定期清理舊記錄
   - 刪除記錄不會刪除實際的圖片和影片檔案

3. **備份建議**：
   - 定期備份 `data/` 目錄
   - 定期備份 `static/inputs/` 和 `static/outputs/` 目錄

## 未來改進方向

1. 密碼加密儲存（使用 bcrypt 或 scrypt）
2. 記錄搜尋和篩選功能
3. 記錄匯出功能（CSV 或 Excel）
4. 批次刪除功能
5. 儲存空間使用統計

