# Live Demo 全屏與自動導航功能說明

## 功能概述

Live Demo 現已支援自動全屏顯示和智能導航功能，提供更流暢的觸控試衣體驗。

## 功能特色

### 1. 自動全屏模式

- **觸發時機**：當使用者首次點擊「📸 拍攝 / 選擇照片」按鈕時自動進入全屏
- **瀏覽器相容**：支援現代瀏覽器的 Fullscreen API
  - Chrome / Edge: `requestFullscreen()`
  - Safari: `webkitRequestFullscreen()`
  - IE11: `msRequestFullscreen()`
- **安全考量**：遵循瀏覽器安全策略，必須由使用者手勢觸發

### 2. 智能自動導航

系統會在使用者完成每個步驟後，自動平滑滾動到下一個功能區域：

#### 流程一：上傳個人照片
- **觸發動作**：成功上傳個人照片
- **自動導航**：600ms 後滾動至「步驟二：選擇想試穿的服飾」
- **視覺提示**：Toast 顯示「照片已更新，可選擇服飾換衣」

#### 流程二：選擇服飾
- **觸發動作**：點擊服飾卡片
- **自動導航**：600ms 後滾動至「步驟三：即時預覽換衣結果」
- **視覺反饋**：
  - 選中的服飾卡片顯示藍色高亮邊框
  - 「立即試衣」按鈕啟用
  - Toast 顯示「已選擇服飾，可按『立即試衣』」

#### 流程三：試衣完成
- **觸發動作**：試衣結果生成完成
- **自動導航**：300ms 後滾動至試衣結果圖片（居中顯示）
- **視覺提示**：Toast 顯示「換衣結果已更新」

#### 流程四：影片生成（選用）
- **觸發動作**：動態影片生成完成
- **自動導航**：300ms 後滾動至影片播放區域（居中顯示）
- **視覺提示**：Toast 顯示「影片生成完成！」

## 技術實現

### CSS 優化

```css
/* 平滑滾動行為 */
body.layout {
  scroll-behavior: smooth;
}

/* 全屏模式支援 */
body.layout:fullscreen {
  width: 100%;
  height: 100%;
}

/* 滾動定位優化 */
.panel {
  scroll-margin-top: 20px;
}
```

### JavaScript 功能

```javascript
// 全屏請求（需要使用者手勢觸發）
function requestFullScreen() {
  const elem = document.documentElement;
  elem.requestFullscreen();
}

// 平滑滾動到指定區域
function scrollToSection(sectionSelector) {
  const section = document.querySelector(sectionSelector);
  section.scrollIntoView({ 
    behavior: 'smooth', 
    block: 'start'
  });
}
```

## 觸控裝置優化

- 更大的按鈕尺寸（觸控裝置）
- 增強的視覺反饋
- 優化的滾動邊距
- 響應式字體大小調整

## 使用建議

### 樹莓派觸控螢幕
1. 啟動應用後，點擊「拍攝 / 選擇照片」按鈕
2. 系統自動進入全屏模式
3. 依照步驟操作，系統會自動引導至下一步

### 桌面瀏覽器
1. 按 F11 或使用瀏覽器全屏功能
2. 或讓系統在首次點擊時自動進入全屏

### 退出全屏
- 按 `ESC` 鍵退出全屏模式
- 或使用瀏覽器的退出全屏按鈕

## 瀏覽器相容性

| 瀏覽器 | 全屏模式 | 平滑滾動 |
|--------|---------|---------|
| Chrome 71+ | ✅ | ✅ |
| Firefox 64+ | ✅ | ✅ |
| Safari 13+ | ✅ | ✅ |
| Edge 79+ | ✅ | ✅ |
| iOS Safari | ⚠️ 受限 | ✅ |

**注意**：iOS Safari 由於系統限制，全屏 API 可能無法使用。

## 更新記錄

### 2025-11-08
- ✅ 新增自動全屏功能（使用者手勢觸發）
- ✅ 實現智能自動導航系統
- ✅ 優化平滑滾動體驗
- ✅ 新增觸控裝置優化樣式
- ✅ 改進視覺反饋機制

## 故障排除

### 全屏無法啟動
- **原因**：瀏覽器安全策略要求使用者手勢觸發
- **解決**：點擊任何按鈕後即可進入全屏

### 自動滾動不流暢
- **檢查**：確認瀏覽器支援 CSS `scroll-behavior: smooth`
- **備選**：系統會自動降級為即時跳轉

### 在 Raspberry Pi 上測試
```bash
cd live-demo
bash start.sh
# 在瀏覽器開啟 http://localhost:5055
```

## 相關文件

- [Live Demo README](./README.md)
- [部署指南](../DEPLOYMENT_GUIDE.md)
- [專案架構](../specs/001-unify-platform/README.md)

