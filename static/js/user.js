(() => {
  const garmentGrid = document.querySelector('#garment-grid');
  const filterBar = document.querySelector('#category-filter');
  const uploadTrigger = document.querySelector('#trigger-upload');
  const uploadInput = document.querySelector('#user-photo-input');
  const previewCard = document.querySelector('#user-photo-preview');
  const resetButton = document.querySelector('#reset-session');
  const fullscreenToggle = document.querySelector('#fullscreen-toggle');
  const resultArea = document.querySelector('#result-area');
  const resultStatus = document.querySelector('#result-status');
  const resultImage = document.querySelector('#result-image');
  const toast = document.querySelector('#toast');
  const startTryOnButton = document.querySelector('#start-tryon');
  const viewSwitcher = document.querySelector('#view-switcher');
  const btnViewBefore = document.querySelector('#btn-view-before');
  const btnViewAfter = document.querySelector('#btn-view-after');
  const btnViewComparison = document.querySelector('#btn-view-comparison');
  const rotatePhotoButton = document.querySelector('#rotate-photo');

  let garments = [];
  let activeFilter = 'all';
  let pollingTimer = null;
  let selectedGarmentId = null;
  let videoEnabled = false;
  let lastTryOnResult = null;
  let currentVideoTaskId = null;
  let wasFullscreenBeforeUpload = false;
  let hasTryOnSuccess = false; // 追蹤是否已成功換髮型
  let imageUrls = {
    before: null,
    after: null,
    comparison: null
  };
  let currentRotation = 0; // 當前旋轉角度 (0, 90, 180, 270)
  let currentPhotoBlob = null; // 當前照片的 Blob

  function init() {
    parseInitialGarments();
    renderFilterChips();
    renderGarmentCards();
    bindEvents();
    fetchGarments();
    checkVideoEnabled();
    updateFullscreenButton();
  }

  function toggleFullscreen() {
    if (!document.fullscreenElement && 
        !document.webkitFullscreenElement && 
        !document.msFullscreenElement) {
      // 進入全屏
      const elem = document.documentElement;
      if (elem.requestFullscreen) {
        elem.requestFullscreen().catch(err => {
          console.log('無法進入全屏模式:', err);
          showToast('無法進入全屏模式');
        });
      } else if (elem.webkitRequestFullscreen) { /* Safari */
        elem.webkitRequestFullscreen();
      } else if (elem.msRequestFullscreen) { /* IE11 */
        elem.msRequestFullscreen();
      }
    } else {
      // 退出全屏
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(err => {
          console.log('無法退出全屏模式:', err);
        });
      } else if (document.webkitExitFullscreen) { /* Safari */
        document.webkitExitFullscreen();
      } else if (document.msExitFullscreen) { /* IE11 */
        document.msExitFullscreen();
      }
    }
  }

  function updateFullscreenButton() {
    if (!fullscreenToggle) return;
    
    const isFullscreen = !!(document.fullscreenElement || 
                           document.webkitFullscreenElement || 
                           document.msFullscreenElement);
    
    fullscreenToggle.textContent = isFullscreen ? '📱 退出全屏' : '🖥️ 全屏';
  }

  function scrollToSection(sectionSelector) {
    // 平滑滾動到指定區域
    const section = document.querySelector(sectionSelector);
    if (section) {
      section.scrollIntoView({ 
        behavior: 'smooth', 
        block: 'start'
      });
    }
  }

  function parseInitialGarments() {
    try {
      const initial = garmentGrid.dataset.initial;
      if (initial) {
        garments = JSON.parse(initial);
      }
    } catch (error) {
      console.warn('無法解析初始髮型資料', error);
    }
  }

  function bindEvents() {
    uploadTrigger.addEventListener('click', () => {
      // 記錄當前是否為全屏狀態
      wasFullscreenBeforeUpload = !!(document.fullscreenElement || 
                                     document.webkitFullscreenElement || 
                                     document.msFullscreenElement);
      uploadInput.click();
    });
    uploadInput.addEventListener('change', handlePhotoUpload);
    resetButton.addEventListener('click', resetSession);
    startTryOnButton.addEventListener('click', startTryOnSelected);
    
    // 全屏切換按鈕
    if (fullscreenToggle) {
      fullscreenToggle.addEventListener('click', toggleFullscreen);
    }
    
    // 監聽全屏狀態變更，更新按鈕文字
    document.addEventListener('fullscreenchange', updateFullscreenButton);
    document.addEventListener('webkitfullscreenchange', updateFullscreenButton);
    document.addEventListener('msfullscreenchange', updateFullscreenButton);
    
    // 圖片切換按鈕
    if (btnViewBefore) {
      btnViewBefore.addEventListener('click', () => switchView('before'));
    }
    if (btnViewAfter) {
      btnViewAfter.addEventListener('click', () => switchView('after'));
    }
    if (btnViewComparison) {
      btnViewComparison.addEventListener('click', () => switchView('comparison'));
    }
    
    // 旋轉照片按鈕
    if (rotatePhotoButton) {
      rotatePhotoButton.addEventListener('click', rotatePhoto);
    }
  }

  function renderFilterChips() {
    const categories = window.LIVE_DEMO_DATA?.categories || [];
    const chips = document.createDocumentFragment();

    const allChip = buildFilterChip('all', '全部');
    chips.appendChild(allChip);

    categories.forEach((category) => {
      chips.appendChild(buildFilterChip(category, category));
    });

    filterBar.innerHTML = '';
    filterBar.appendChild(chips);
  }

  function buildFilterChip(value, label) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'filter-badge' + (value === activeFilter ? ' filter-badge--active' : '');
    chip.textContent = label;
    chip.addEventListener('click', () => {
      activeFilter = value;
      document.querySelectorAll('.filter-badge').forEach((el) => {
        el.classList.toggle('filter-badge--active', el === chip);
      });
      renderGarmentCards();
    });
    return chip;
  }

  function renderGarmentCards() {
    garmentGrid.innerHTML = '';
    const filtered = garments.filter((item) => {
      if (activeFilter === 'all') {
        return true;
      }
      return item.category === activeFilter;
    });

    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = '尚未有此分類的髮型，請稍後再試。';
      garmentGrid.appendChild(empty);
      return;
    }

    filtered.forEach((item) => {
      const card = document.createElement('article');
      card.className = 'garment-card';
      card.dataset.id = item.garment_id;
      if (item.garment_id === selectedGarmentId) {
        card.classList.add('garment-card--active');
      }
      const img = document.createElement('img');
      img.className = 'garment-card__image';
      const imgSrc = item.image_url || item.image_path || '';
      img.src = `/${imgSrc}`.replace(/\/+/, '/');
      img.alt = item.name;
      card.appendChild(img);

      const body = document.createElement('div');
      body.className = 'garment-card__body';
      const title = document.createElement('h3');
      title.className = 'garment-card__title';
      title.textContent = item.name;
      body.appendChild(title);

      const category = document.createElement('div');
      category.className = 'garment-card__category';
      category.textContent = item.category;
      body.appendChild(category);

      if (item.description) {
        const desc = document.createElement('p');
        desc.textContent = item.description;
        body.appendChild(desc);
      }
      card.appendChild(body);
      card.addEventListener('click', () => selectGarment(item.garment_id));
      garmentGrid.appendChild(card);
    });
  }

  function handlePhotoUpload(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    currentRotation = 0; // 重置旋轉角度

    const formData = new FormData();
    formData.append('photo', file);

    displayStatus('上傳中，請稍候...');

    fetch('/api/upload-user-photo', {
      method: 'POST',
      body: formData,
    })
      .then(handleResponse)
      .then((data) => {
        if (data.error) {
          throw new Error(data.error);
        }
        updateUserPreview(data.photo_url);
        
        // 從服務器返回的 URL 加載處理後的圖片，並保存為 Blob
        // 這樣可以確保旋轉時使用的是正確處理過 EXIF 的圖片
        return fetch(data.photo_url)
          .then(response => response.blob())
          .then(blob => {
            currentPhotoBlob = blob;
            
            // 顯示旋轉按鈕
            if (rotatePhotoButton) {
              rotatePhotoButton.classList.remove('hidden');
            }
            
            showToast('照片已更新，可選擇髮型換髮型');
            displayStatus('請選擇想試換的髮型');
            // 自動滾動到服飾選擇區域
            setTimeout(() => {
              scrollToSection('#step-garment');
            }, 600);
            
            // 如果上傳前是全屏狀態，重新進入全屏
            if (wasFullscreenBeforeUpload) {
              setTimeout(() => {
                const elem = document.documentElement;
                if (elem.requestFullscreen) {
                  elem.requestFullscreen().catch(err => {
                    console.log('無法重新進入全屏:', err);
                  });
                } else if (elem.webkitRequestFullscreen) {
                  elem.webkitRequestFullscreen();
                } else if (elem.msRequestFullscreen) {
                  elem.msRequestFullscreen();
                }
                wasFullscreenBeforeUpload = false;
              }, 800);
            }
          });
      })
      .catch((error) => {
        showToast(error.message || '上傳失敗，請重試');
        displayStatus('上傳失敗，請重新拍攝');
        wasFullscreenBeforeUpload = false;
      })
      .finally(() => {
        event.target.value = '';
      });
  }

  function updateUserPreview(photoUrl) {
    previewCard.innerHTML = '';
    const image = document.createElement('img');
    image.src = photoUrl;
    image.alt = '個人照片預覽';
    previewCard.appendChild(image);
  }

  function startTryOnSelected() {
    if (!selectedGarmentId) {
      showToast('請先選擇想試換的髮型');
      return;
    }
    startTryOnButton.disabled = true;
    requestTryOn(selectedGarmentId);
  }

  function requestTryOn(garmentId) {
    displayStatus('生成換髮型結果中，請稍候...');
    resultImage.classList.add('hidden');
    
    // 隱藏影片生成按鈕和視圖切換按鈕（開始新的換髮型）
    hideVideoButton();
    if (viewSwitcher) {
      viewSwitcher.classList.add('hidden');
    }
    
    // 重置換髮型成功狀態
    hasTryOnSuccess = false;

    fetch('/api/try-on', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ garment_id: garmentId }),
    })
      .then(handleResponse)
      .then((data) => {
        if (data.error) {
          throw new Error(data.error);
        }
        if (data.status === 'processing') {
          startTryOnButton.disabled = false;
        }
        if (data.preview) {
          updatePreviewWithDataUrl(data.preview);
        }
        if (data.session_id) {
          pollTryOnResult(data.session_id);
        }
      })
      .catch((error) => {
        showToast(error.message || '換髮型服務暫時無法使用');
        displayStatus('生成失敗，請稍後重試');
        startTryOnButton.disabled = false;
      });
  }

  function updatePreviewWithDataUrl(dataUrl) {
    previewCard.innerHTML = '';
    const image = document.createElement('img');
    image.src = dataUrl;
    image.alt = '上傳照片預覽';
    previewCard.appendChild(image);
  }

  function pollTryOnResult(sessionId) {
    if (pollingTimer) {
      clearTimeout(pollingTimer);
    }

    const poll = () => {
      fetch(`/api/try-on/${encodeURIComponent(sessionId)}`)
        .then(handleResponse)
        .then((data) => {
          if (data.status === 'ok' && data.result_url) {
            // 保存三個圖片 URL
            imageUrls.after = data.result_url;
            imageUrls.before = data.before_url || null;
            imageUrls.comparison = data.comparison_url || null;
            
            // 調試信息
            console.log('換髮型完成，圖片 URLs:', {
              before: imageUrls.before,
              after: imageUrls.after,
              comparison: imageUrls.comparison
            });
            
            // 顯示試髮後的圖片（默認）
            resultImage.src = imageUrls.after;
            resultImage.classList.remove('hidden');
            lastTryOnResult = imageUrls.after;
            
            // 顯示切換按鈕組
            if (viewSwitcher) {
              viewSwitcher.classList.remove('hidden');
            }
            
            // 默認選中「試髮後」按鈕
            switchView('after');
            
            // 標記換髮型成功
            hasTryOnSuccess = true;
            
            displayStatus('換髮型完成！可繼續挑選其他髮型');
            showToast('換髮型結果已更新');
            startTryOnButton.disabled = false;
            
            // 只有在換髮型成功後才顯示影片生成按鈕
            showVideoButtonIfEnabled();
            // 自動滾動到結果顯示區域
            setTimeout(() => {
              resultImage.scrollIntoView({ 
                behavior: 'smooth', 
                block: 'center'
              });
            }, 300);
            return;
          }
          if (data.status === 'error') {
            throw new Error(data.message || '換衣過程發生錯誤');
          }
          pollingTimer = setTimeout(poll, 1800);
          displayStatus('持續生成中，稍待片刻...');
        })
        .catch((error) => {
          showToast(error.message || '換髮型過程發生錯誤');
          displayStatus('換髮型失敗，請重新選擇髮型或拍照');
          startTryOnButton.disabled = false;
        });
    };

    poll();
  }

  function switchView(viewType) {
    console.log('切換視圖:', viewType);
    
    // 更新按鈕狀態
    [btnViewBefore, btnViewAfter, btnViewComparison].forEach(btn => {
      if (btn) {
        btn.classList.remove('active', 'btn--primary');
        btn.classList.add('btn--ghost');
      }
    });
    
    let targetUrl = null;
    let activeButton = null;
    
    switch(viewType) {
      case 'before':
        targetUrl = imageUrls.before;
        activeButton = btnViewBefore;
        break;
      case 'after':
        targetUrl = imageUrls.after;
        activeButton = btnViewAfter;
        break;
      case 'comparison':
        targetUrl = imageUrls.comparison;
        activeButton = btnViewComparison;
        break;
    }
    
    console.log('目標 URL:', targetUrl);
    
    if (activeButton) {
      activeButton.classList.remove('btn--ghost');
      activeButton.classList.add('btn--primary', 'active');
    }
    
    if (targetUrl && resultImage) {
      resultImage.src = targetUrl;
      console.log('圖片已更新為:', targetUrl);
    } else if (!targetUrl) {
      console.warn('目標 URL 為空，無法切換圖片');
      showToast('此圖片暫時無法顯示');
    }
  }

  function rotatePhoto() {
    if (!currentPhotoBlob) {
      showToast('請先上傳照片');
      return;
    }

    // 更新旋轉角度 (0 -> 90 -> 180 -> 270 -> 0)
    currentRotation = (currentRotation + 90) % 360;
    
    displayStatus('旋轉照片中，請稍候...');
    rotatePhotoButton.disabled = true;

    // 讀取圖片並旋轉
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        // 創建 Canvas
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');

        // 每次固定旋轉 90 度（順時針），而不是旋轉到累積角度
        // 因為 currentPhotoBlob 已經是上次旋轉後的照片
        canvas.width = img.height;  // 寬度變成原來的高度
        canvas.height = img.width;  // 高度變成原來的寬度

        // 旋轉 90 度（順時針）
        ctx.save();
        ctx.translate(canvas.width, 0);
        ctx.rotate(Math.PI / 2);
        ctx.drawImage(img, 0, 0);
        ctx.restore();

        // 轉換為 Blob 並上傳
        canvas.toBlob((blob) => {
          if (!blob) {
            showToast('旋轉失敗，請重試');
            rotatePhotoButton.disabled = false;
            return;
          }

          // 更新當前照片 Blob
          currentPhotoBlob = blob;

          // 上傳旋轉後的照片
          const formData = new FormData();
          formData.append('photo', blob, 'rotated_photo.jpg');

          fetch('/api/upload-user-photo', {
            method: 'POST',
            body: formData,
          })
            .then(handleResponse)
            .then((data) => {
              if (data.error) {
                throw new Error(data.error);
              }
              updateUserPreview(data.photo_url);
              
              // 從服務器返回的 URL 重新加載圖片，確保與服務器保持一致
              return fetch(data.photo_url)
                .then(response => response.blob())
                .then(serverBlob => {
                  currentPhotoBlob = serverBlob;
                  showToast(`照片已旋轉 ${currentRotation}°`);
                  displayStatus('請選擇想試換的髮型');
                });
            })
            .catch((error) => {
              showToast(error.message || '旋轉失敗');
              displayStatus('旋轉失敗，請重試');
            })
            .finally(() => {
              rotatePhotoButton.disabled = false;
            });
        }, 'image/jpeg', 0.92);
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(currentPhotoBlob);
  }

  function resetSession() {
    fetch('/api/reset-user-photo', { method: 'POST' }).finally(() => {
      previewCard.innerHTML = '<div class="preview-card__placeholder">尚未選擇照片</div>';
      resultStatus.textContent = '等待開始換髮型';
      resultImage.classList.add('hidden');
      
      // 隱藏切換按鈕組
      if (viewSwitcher) {
        viewSwitcher.classList.add('hidden');
      }
      
      // 隱藏影片生成按鈕和旋轉按鈕
      hideVideoButton();
      if (rotatePhotoButton) {
        rotatePhotoButton.classList.add('hidden');
      }
      
      // 清空圖片 URL
      imageUrls.before = null;
      imageUrls.after = null;
      imageUrls.comparison = null;
      
      // 重置換髮型成功狀態
      hasTryOnSuccess = false;
      lastTryOnResult = null;
      
      // 重置旋轉狀態
      currentRotation = 0;
      currentPhotoBlob = null;
      
      showToast('已重新開始，請再次拍攝');
    });
  }

  function displayStatus(message) {
    resultStatus.textContent = message;
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add('toast--visible');
    setTimeout(() => {
      toast.classList.remove('toast--visible');
    }, 2600);
  }

  function handleResponse(response) {
    if (!response.ok) {
      return response.json().catch(() => ({})).then((data) => {
        if (data.error) {
          throw new Error(data.error);
        }
        throw new Error('系統繁忙，請稍後再試');
      });
    }
    return response.json();
  }

  function fetchGarments() {
    fetch('/api/garments')
      .then(handleResponse)
      .then((data) => {
        if (Array.isArray(data.garments)) {
          garments = data.garments;
          if (!garments.find((item) => item.garment_id === selectedGarmentId)) {
            selectedGarmentId = null;
            startTryOnButton.disabled = true;
          }
          renderGarmentCards();
        }
      })
      .catch((error) => console.warn('無法更新髮型資料', error));
  }

  function selectGarment(garmentId) {
    selectedGarmentId = garmentId;
    startTryOnButton.disabled = false;
    document.querySelectorAll('.garment-card').forEach((card) => {
      card.classList.toggle('garment-card--active', card.dataset.id === garmentId);
    });
    showToast('已選擇髮型，可按「立即換髮型」');
    // 自動滾動到試衣按鈕區域
    setTimeout(() => {
      scrollToSection('#step-result');
    }, 600);
  }

  // --- Video Generation Functions ---

  function checkVideoEnabled() {
    fetch('/api/video/enabled')
      .then(handleResponse)
      .then((data) => {
        videoEnabled = data.enabled || false;
        console.log('[Video] Enabled:', videoEnabled);
      })
      .catch((error) => {
        console.warn('無法檢查影片功能', error);
        videoEnabled = false;
      });
  }

  function showVideoButtonIfEnabled() {
    // 只有在換髮型成功後才顯示影片生成按鈕
    if (!videoEnabled || !lastTryOnResult || !hasTryOnSuccess) {
      return;
    }
    const videoBtn = document.getElementById('generate-video-btn');
    if (videoBtn) {
      videoBtn.style.display = 'block';
      console.log('[Video] 顯示影片生成按鈕（換髮型已成功）');
    }
  }

  function hideVideoButton() {
    const videoBtn = document.getElementById('generate-video-btn');
    if (videoBtn) {
      videoBtn.style.display = 'none';
    }
  }

  function startVideoGeneration() {
    if (!lastTryOnResult) {
      showToast('請先完成換髮型');
      return;
    }

    const prompt = '身體旋轉一圈';
    displayStatus('AI 正在生成動態影片，請稍候...');
    hideVideoButton();

    fetch('/api/video/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        image_path: lastTryOnResult,
        prompt: prompt,
        duration: 5,
      }),
    })
      .then(handleResponse)
      .then((data) => {
        if (data.error) {
          throw new Error(data.error);
        }
        currentVideoTaskId = data.task_id;
        if (currentVideoTaskId) {
          pollVideoResult();
        } else {
          throw new Error('未收到影片任務 ID');
        }
      })
      .catch((error) => {
        showToast(error.message || '影片生成失敗');
        displayStatus('影片生成失敗，請重試');
        showVideoButtonIfEnabled();
      });
  }

  function pollVideoResult() {
    if (!currentVideoTaskId) {
      return;
    }

    fetch(`/api/video/${encodeURIComponent(currentVideoTaskId)}`)
      .then(handleResponse)
      .then((data) => {
        if (data.status === 'completed' && data.output_path) {
          displayVideoResult(data.output_path);
          showToast('影片生成完成！');
          displayStatus('影片已生成，可繼續試換其他髮型');
          return;
        }
        if (data.status === 'failed' || data.status === 'error') {
          throw new Error(data.message || '影片生成失敗');
        }
        // Still processing, poll again
        setTimeout(pollVideoResult, 3000);
        displayStatus('影片生成中，請稍候...');
      })
      .catch((error) => {
        showToast(error.message || '影片生成過程出錯');
        displayStatus('影片生成失敗，請重試');
        showVideoButtonIfEnabled();
      });
  }

  function displayVideoResult(videoPath) {
    const videoContainer = document.getElementById('video-result');
    const videoElement = document.getElementById('result-video');
    
    if (videoContainer && videoElement) {
      videoElement.src = videoPath;
      videoContainer.style.display = 'block';
      // 自動滾動到影片區域
      setTimeout(() => {
        videoContainer.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'center'
        });
      }, 300);
    }
    
    showVideoButtonIfEnabled();
  }

  // Bind video button event
  document.addEventListener('DOMContentLoaded', () => {
    const videoBtn = document.getElementById('generate-video-btn');
    if (videoBtn) {
      videoBtn.addEventListener('click', startVideoGeneration);
    }
  });

  // ========== 全屏圖片查看器 ==========
  const fullscreenViewer = {
    viewer: null,
    container: null,
    closeBtn: null,
    prevBtn: null,
    nextBtn: null,
    label: null,
    indicators: [],
    wrappers: [],
    images: [],
    currentIndex: 1, // 默認顯示「試髮後」
    labels: ['試髮前', '試髮後', '前後比較'],
    touchStartX: 0,
    touchEndX: 0,
    minSwipeDistance: 50,

    init() {
      this.viewer = document.getElementById('fullscreen-viewer');
      this.container = document.getElementById('fullscreen-container');
      this.closeBtn = this.viewer?.querySelector('.fullscreen-viewer__close');
      this.prevBtn = this.viewer?.querySelector('.fullscreen-viewer__nav--prev');
      this.nextBtn = this.viewer?.querySelector('.fullscreen-viewer__nav--next');
      this.label = document.getElementById('fullscreen-label');
      this.indicators = Array.from(this.viewer?.querySelectorAll('.fullscreen-viewer__indicator') || []);
      this.wrappers = Array.from(this.viewer?.querySelectorAll('.fullscreen-viewer__image-wrapper') || []);
      this.images = [
        document.getElementById('fullscreen-img-0'),
        document.getElementById('fullscreen-img-1'),
        document.getElementById('fullscreen-img-2')
      ];

      if (!this.viewer) return;

      // 綁定關閉按鈕
      this.closeBtn?.addEventListener('click', () => this.close());

      // 綁定導航按鈕
      this.prevBtn?.addEventListener('click', () => this.navigate(-1));
      this.nextBtn?.addEventListener('click', () => this.navigate(1));

      // 綁定指示器點擊
      this.indicators.forEach((indicator, index) => {
        indicator.addEventListener('click', () => this.goTo(index));
      });

      // 綁定觸摸滑動手勢
      this.container?.addEventListener('touchstart', (e) => {
        this.touchStartX = e.changedTouches[0].screenX;
      }, { passive: true });

      this.container?.addEventListener('touchend', (e) => {
        this.touchEndX = e.changedTouches[0].screenX;
        this.handleSwipe();
      }, { passive: true });

      // 綁定鍵盤導航
      document.addEventListener('keydown', (e) => {
        if (!this.viewer?.classList.contains('active')) return;
        
        if (e.key === 'Escape') {
          this.close();
        } else if (e.key === 'ArrowLeft') {
          this.navigate(-1);
        } else if (e.key === 'ArrowRight') {
          this.navigate(1);
        }
      });

      // 綁定三個按鈕的點擊事件
      document.getElementById('btn-view-before')?.addEventListener('click', () => {
        this.open(0);
      });
      document.getElementById('btn-view-after')?.addEventListener('click', () => {
        this.open(1);
      });
      document.getElementById('btn-view-comparison')?.addEventListener('click', () => {
        this.open(2);
      });

      // 也可以點擊結果圖片打開全屏查看
      resultImage?.addEventListener('click', () => {
        if (!resultImage.classList.contains('hidden') && imageUrls.after) {
          // 根據當前顯示的圖片決定打開哪一張
          const currentSrc = resultImage.src;
          let index = 1; // 默認試髮後
          if (currentSrc.includes(imageUrls.before)) {
            index = 0;
          } else if (currentSrc.includes(imageUrls.comparison)) {
            index = 2;
          }
          this.open(index);
        }
      });
    },

    open(index = 1) {
      if (!this.viewer || !imageUrls.after) return;

      // 設置三張圖片的 src
      if (this.images[0] && imageUrls.before) {
        this.images[0].src = imageUrls.before;
      }
      if (this.images[1] && imageUrls.after) {
        this.images[1].src = imageUrls.after;
      }
      if (this.images[2] && imageUrls.comparison) {
        this.images[2].src = imageUrls.comparison;
      }

      this.currentIndex = index;
      this.updateView();
      this.viewer.classList.add('active');
      document.body.style.overflow = 'hidden'; // 防止背景滾動
    },

    close() {
      if (!this.viewer) return;
      this.viewer.classList.remove('active');
      document.body.style.overflow = ''; // 恢復滾動
    },

    navigate(direction) {
      const newIndex = this.currentIndex + direction;
      if (newIndex >= 0 && newIndex < this.images.length) {
        this.currentIndex = newIndex;
        this.updateView();
      }
    },

    goTo(index) {
      if (index >= 0 && index < this.images.length) {
        this.currentIndex = index;
        this.updateView();
      }
    },

    handleSwipe() {
      const swipeDistance = this.touchStartX - this.touchEndX;
      
      if (Math.abs(swipeDistance) > this.minSwipeDistance) {
        if (swipeDistance > 0) {
          // 向左滑動 - 下一張
          this.navigate(1);
        } else {
          // 向右滑動 - 上一張
          this.navigate(-1);
        }
      }
    },

    updateView() {
      // 更新圖片顯示
      this.wrappers.forEach((wrapper, index) => {
        if (index === this.currentIndex) {
          wrapper.classList.add('active');
        } else {
          wrapper.classList.remove('active');
        }
      });

      // 更新指示器
      this.indicators.forEach((indicator, index) => {
        if (index === this.currentIndex) {
          indicator.classList.add('active');
        } else {
          indicator.classList.remove('active');
        }
      });

      // 更新標籤
      if (this.label) {
        this.label.textContent = this.labels[this.currentIndex];
      }
    }
  };

  // 初始化全屏查看器
  document.addEventListener('DOMContentLoaded', () => {
    fullscreenViewer.init();
  });

  document.addEventListener('DOMContentLoaded', init);
})();

