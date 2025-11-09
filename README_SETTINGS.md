# Live Demo 系統設定功能

## 功能說明

現在您可以透過 Web 後台管理介面來設定所有系統參數，包括：

### Gemini 設定
- **GEMINI_API_KEY**: Gemini API 金鑰
- **GEMINI_MODEL**: 圖像生成模型（如 `gemini-2.5-flash-image`）
- **GEMINI_LLM**: 語言模型（如 `gemini-2.5-flash`）
- **GEMINI_SAFETY_SETTINGS**: 安全設定級別
  - `BLOCK_NONE` - 不封鎖任何內容
  - `BLOCK_ONLY_HIGH` - 僅封鎖高風險內容（推薦）
  - `BLOCK_MEDIUM_AND_ABOVE` - 封鎖中等以上風險
  - `BLOCK_LOW_AND_ABOVE` - 封鎖低風險以上內容（嚴格）

### 試衣服務供應商
- **VENDOR_TRYON**: 選擇使用的試衣服務
  - `Gemini` - Google Gemini AI
  - `KlingAI` - 快手 KlingAI

### KlingAI 影片設定
- **KLINGAI_VIDEO_ACCESS_KEY**: KlingAI API 存取金鑰
- **KLINGAI_VIDEO_SECRET_KEY**: KlingAI API 密鑰
- **KLINGAI_VIDEO_MODEL**: 模型版本（如 `kling-v2-5-turbo`）
- **KLINGAI_VIDEO_MODE**: 影片生成模式（`std` 或 `pro`）
- **KLINGAI_VIDEO_DURATION**: 影片長度（`5` 或 `10` 秒）

## 使用方式

1. 訪問 Live Demo 管理後台：
   ```
   http://127.0.0.1:5055/admin/login
   ```

2. 使用管理員帳號登入：
   - 預設帳號：`admin`
   - 預設密碼：`storepi`
   - （可透過環境變數 `LIVE_DEMO_ADMIN_USER` 和 `LIVE_DEMO_ADMIN_PASS` 修改）

3. 點選右上角的「系統設定」按鈕

4. 修改您需要的設定項目

5. 點選「儲存設定」按鈕

6. **重要：重新啟動服務以套用變更**
   ```bash
   cd live-demo
   ./start.sh
   ```

## 設定檔案位置

設定會儲存在：
```
live-demo/data/settings.json
```

您也可以直接編輯此檔案，但建議使用 Web 介面以確保格式正確。

## 關於 Safety Settings

`GEMINI_SAFETY_SETTINGS` 控制 Gemini 內容審查的嚴格程度：

- **BLOCK_ONLY_HIGH**（推薦）：允許泳裝、內衣等合法服飾的試衣，只封鎖明顯不當的內容
- **BLOCK_NONE**：完全不限制，適合內部測試
- **BLOCK_MEDIUM_AND_ABOVE**：較嚴格，可能會誤判某些正常服飾
- **BLOCK_LOW_AND_ABOVE**：非常嚴格，會封鎖大量正常內容，不建議使用

## 注意事項

1. 修改設定後需要重新啟動服務才會生效
2. API Key 等敏感資訊請妥善保管
3. 建議定期備份 `settings.json` 檔案
4. 如果設定錯誤導致服務無法啟動，可以刪除 `settings.json` 讓系統使用預設值

## 疑難排解

### 設定沒有生效
- 確認已重新啟動服務
- 檢查 `live-demo/data/settings.json` 檔案格式是否正確

### 無法訪問設定頁面
- 確認已登入管理後台
- 檢查瀏覽器 console 是否有 JavaScript 錯誤

### 儲存失敗
- 確認 `live-demo/data/` 目錄有寫入權限
- 檢查是否有必要欄位未填寫

