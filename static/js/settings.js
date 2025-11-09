/**
 * Live Demo 系統設定管理
 */

// ========== Toast 通知 ==========
function showToast(message, type = 'info') {
  const toast = document.getElementById('toast');
  if (!toast) return;
  
  toast.textContent = message;
  toast.className = `toast toast--${type} toast--show`;
  
  setTimeout(() => {
    toast.classList.remove('toast--show');
  }, 3000);
}

// ========== 載入設定 ==========
async function loadSettings() {
  try {
    const response = await fetch('/admin/settings/data');
    const data = await response.json();
    
    if (data.status === 'ok' && data.settings) {
      populateForm(data.settings);
    } else {
      showToast(data.message || '載入設定失敗', 'error');
    }
  } catch (error) {
    console.error('載入設定錯誤:', error);
    showToast('載入設定時發生錯誤', 'error');
  }
}

// ========== 填充表單 ==========
function populateForm(settings) {
  const form = document.getElementById('settings-form');
  if (!form) return;
  
  Object.entries(settings).forEach(([key, value]) => {
    const input = form.querySelector(`[name="${key}"]`);
    if (input) {
      input.value = value || '';
    }
  });
}

// ========== 取得表單資料 ==========
function getFormData() {
  const form = document.getElementById('settings-form');
  if (!form) return {};
  
  const formData = new FormData(form);
  const settings = {};
  
  for (const [key, value] of formData.entries()) {
    settings[key] = value;
  }
  
  return settings;
}

// ========== 儲存設定 ==========
async function saveSettings(event) {
  event.preventDefault();
  
  const settings = getFormData();
  
  // 基本驗證
  if (!settings.GEMINI_API_KEY && !settings.KLINGAI_VIDEO_ACCESS_KEY) {
    showToast('請至少填寫 Gemini API Key 或 KlingAI Access Key', 'warning');
    return;
  }
  
  try {
    const response = await fetch('/admin/settings/data', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ settings }),
    });
    
    const data = await response.json();
    
    if (data.status === 'ok') {
      showToast('設定已儲存成功！請重新啟動服務以套用變更', 'success');
    } else {
      showToast(data.message || '儲存失敗', 'error');
    }
  } catch (error) {
    console.error('儲存設定錯誤:', error);
    showToast('儲存設定時發生錯誤', 'error');
  }
}

// ========== 重設為預設值 ==========
function resetToDefaults() {
  if (!confirm('確定要重設為預設值嗎？此操作不會儲存到檔案，除非您點選「儲存設定」按鈕。')) {
    return;
  }
  
  const defaultSettings = {
    GEMINI_API_KEY: '',
    GEMINI_MODEL: 'gemini-2.5-flash-image',
    GEMINI_LLM: 'gemini-2.5-flash',
    GEMINI_SAFETY_SETTINGS: 'BLOCK_ONLY_HIGH',
    KLINGAI_VIDEO_ACCESS_KEY: '',
    KLINGAI_VIDEO_SECRET_KEY: '',
    KLINGAI_VIDEO_MODEL: 'kling-v2-5-turbo',
    KLINGAI_VIDEO_MODE: 'std',
    KLINGAI_VIDEO_DURATION: '5',
    VENDOR_TRYON: 'Gemini',
  };
  
  populateForm(defaultSettings);
  showToast('已重設為預設值，請記得儲存', 'info');
}

// ========== 修改密碼 ==========
async function changePassword(event) {
  event.preventDefault();
  
  const form = document.getElementById('change-password-form');
  if (!form) return;
  
  const submitButton = form.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  submitButton.textContent = '處理中...';
  
  const formData = new FormData(form);
  const payload = {
    current_password: formData.get('current_password'),
    new_password: formData.get('new_password'),
    confirm_password: formData.get('confirm_password'),
  };
  
  try {
    const response = await fetch('/admin/change-password', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    
    const data = await response.json();
    
    if (data.status === 'ok') {
      showToast('密碼已成功修改', 'success');
      form.reset();
    } else {
      showToast(data.message || '修改密碼失敗', 'error');
    }
  } catch (error) {
    console.error('修改密碼錯誤:', error);
    showToast('修改密碼時發生錯誤', 'error');
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = '修改密碼';
  }
}

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
  // 載入現有設定
  loadSettings();
  
  // 綁定表單提交事件
  const form = document.getElementById('settings-form');
  if (form) {
    form.addEventListener('submit', saveSettings);
  }
  
  // 綁定重設按鈕
  const resetBtn = document.getElementById('btn-reset');
  if (resetBtn) {
    resetBtn.addEventListener('click', resetToDefaults);
  }
  
  // 綁定修改密碼表單
  const passwordForm = document.getElementById('change-password-form');
  if (passwordForm) {
    passwordForm.addEventListener('submit', changePassword);
  }
});

