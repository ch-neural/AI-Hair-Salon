(() => {
  const historyList = document.querySelector('#history-list');
  const emptyState = document.querySelector('#history-empty');
  const pagination = document.querySelector('#pagination');
  const statsDiv = document.querySelector('#history-stats');
  const toast = document.querySelector('#toast');
  const changePasswordForm = document.querySelector('#change-password-form');

  let currentPage = 1;
  let totalPages = 0;
  let totalRecords = 0;

  function init() {
    fetchHistory(1);
    bindEvents();
  }

  function bindEvents() {
    if (changePasswordForm) {
      changePasswordForm.addEventListener('submit', handleChangePassword);
    }
  }

  function fetchHistory(page = 1) {
    currentPage = page;
    fetch(`/api/admin/history?page=${page}&per_page=20`)
      .then(handleResponse)
      .then((data) => {
        if (data.status === 'ok') {
          totalRecords = data.total || 0;
          totalPages = data.total_pages || 0;
          renderHistory(data.records || []);
          renderPagination();
          updateStats();
        }
      })
      .catch((error) => {
        console.error('載入換髮型記錄失敗', error);
        showToast('載入記錄失敗，請重新整理頁面');
      });
  }

  function renderHistory(records) {
    historyList.innerHTML = '';

    if (!records.length) {
      emptyState.classList.remove('hidden');
      return;
    }

    emptyState.classList.add('hidden');

    records.forEach((record) => {
      const card = createHistoryCard(record);
      historyList.appendChild(card);
    });
  }

  function createHistoryCard(record) {
    const card = document.createElement('div');
    card.className = 'history-card';

    // 標題和時間
    const header = document.createElement('div');
    header.className = 'history-card__header';
    
    const title = document.createElement('h3');
    title.className = 'history-card__title';
    title.textContent = record.garment_name || '未知髮型';
    header.appendChild(title);

    const time = document.createElement('div');
    time.className = 'history-card__time';
    time.textContent = record.timestamp || '';
    header.appendChild(time);

    card.appendChild(header);

    // 圖片區域
    const images = document.createElement('div');
    images.className = 'history-card__images';

    // 人物照
    if (record.user_photo_url) {
      const userImgWrapper = document.createElement('div');
      userImgWrapper.className = 'history-card__image-wrapper';
      
      const userLabel = document.createElement('div');
      userLabel.className = 'history-card__image-label';
      userLabel.textContent = '人物照';
      userImgWrapper.appendChild(userLabel);

      const userImg = document.createElement('img');
      userImg.src = record.user_photo_url;
      userImg.alt = '人物照';
      userImg.className = 'history-card__image';
      userImgWrapper.appendChild(userImg);

      const userDownload = document.createElement('a');
      userDownload.href = record.user_photo_url;
      userDownload.download = `user_${record.record_id}.jpg`;
      userDownload.className = 'history-card__download';
      userDownload.textContent = '下載';
      userImgWrapper.appendChild(userDownload);

      images.appendChild(userImgWrapper);
    }

    // 髮型照
    if (record.garment_photo_url) {
      const garmentImgWrapper = document.createElement('div');
      garmentImgWrapper.className = 'history-card__image-wrapper';
      
      const garmentLabel = document.createElement('div');
      garmentLabel.className = 'history-card__image-label';
      garmentLabel.textContent = '髮型照';
      garmentImgWrapper.appendChild(garmentLabel);

      const garmentImg = document.createElement('img');
      garmentImg.src = record.garment_photo_url;
      garmentImg.alt = '髮型照';
      garmentImg.className = 'history-card__image';
      garmentImgWrapper.appendChild(garmentImg);

      const garmentDownload = document.createElement('a');
      garmentDownload.href = record.garment_photo_url;
      garmentDownload.download = `garment_${record.record_id}.jpg`;
      garmentDownload.className = 'history-card__download';
      garmentDownload.textContent = '下載';
      garmentImgWrapper.appendChild(garmentDownload);

      images.appendChild(garmentImgWrapper);
    }

    // 換髮型結果照
    if (record.result_photo_url && record.status === 'success') {
      const resultImgWrapper = document.createElement('div');
      resultImgWrapper.className = 'history-card__image-wrapper';
      
      const resultLabel = document.createElement('div');
      resultLabel.className = 'history-card__image-label';
      resultLabel.textContent = '換髮型結果';
      resultImgWrapper.appendChild(resultLabel);

      const resultImg = document.createElement('img');
      resultImg.src = record.result_photo_url;
      resultImg.alt = '換髮型結果';
      resultImg.className = 'history-card__image';
      resultImgWrapper.appendChild(resultImg);

      const resultDownload = document.createElement('a');
      resultDownload.href = record.result_photo_url;
      resultDownload.download = `result_${record.record_id}.jpg`;
      resultDownload.className = 'history-card__download';
      resultDownload.textContent = '下載';
      resultImgWrapper.appendChild(resultDownload);

      images.appendChild(resultImgWrapper);
    }

    // 影片
    if (record.video_url && record.status === 'success') {
      const videoWrapper = document.createElement('div');
      videoWrapper.className = 'history-card__image-wrapper';
      
      const videoLabel = document.createElement('div');
      videoLabel.className = 'history-card__image-label';
      videoLabel.textContent = '生成影片';
      videoWrapper.appendChild(videoLabel);

      const video = document.createElement('video');
      video.src = record.video_url;
      video.controls = true;
      video.className = 'history-card__image';
      videoWrapper.appendChild(video);

      const videoDownload = document.createElement('a');
      videoDownload.href = record.video_url;
      videoDownload.download = `video_${record.record_id}.mp4`;
      videoDownload.className = 'history-card__download';
      videoDownload.textContent = '下載';
      videoWrapper.appendChild(videoDownload);

      images.appendChild(videoWrapper);
    }

    card.appendChild(images);

    // 狀態
    const footer = document.createElement('div');
    footer.className = 'history-card__footer';

    const status = document.createElement('div');
    status.className = `history-card__status history-card__status--${record.status}`;
    
    if (record.status === 'success') {
      status.textContent = '✓ 換髮型成功';
    } else if (record.status === 'failed') {
      status.textContent = '✗ 換髮型失敗';
      if (record.error_message) {
        const errorMsg = document.createElement('div');
        errorMsg.className = 'history-card__error';
        errorMsg.textContent = record.error_message;
        footer.appendChild(errorMsg);
      }
    } else if (record.status === 'processing') {
      status.textContent = '⏳ 處理中';
    }

    footer.appendChild(status);

    // 刪除按鈕
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'btn btn--ghost btn--small';
    deleteBtn.textContent = '刪除';
    deleteBtn.addEventListener('click', () => deleteRecord(record.record_id));
    footer.appendChild(deleteBtn);

    card.appendChild(footer);

    return card;
  }

  function renderPagination() {
    if (totalPages <= 1) {
      pagination.classList.add('hidden');
      return;
    }

    pagination.classList.remove('hidden');
    pagination.innerHTML = '';

    // 上一頁
    if (currentPage > 1) {
      const prevBtn = document.createElement('button');
      prevBtn.type = 'button';
      prevBtn.className = 'btn btn--ghost btn--small';
      prevBtn.textContent = '← 上一頁';
      prevBtn.addEventListener('click', () => fetchHistory(currentPage - 1));
      pagination.appendChild(prevBtn);
    }

    // 頁碼
    const pageInfo = document.createElement('span');
    pageInfo.style.margin = '0 1rem';
    pageInfo.textContent = `第 ${currentPage} / ${totalPages} 頁`;
    pagination.appendChild(pageInfo);

    // 下一頁
    if (currentPage < totalPages) {
      const nextBtn = document.createElement('button');
      nextBtn.type = 'button';
      nextBtn.className = 'btn btn--ghost btn--small';
      nextBtn.textContent = '下一頁 →';
      nextBtn.addEventListener('click', () => fetchHistory(currentPage + 1));
      pagination.appendChild(nextBtn);
    }
  }

  function updateStats() {
    if (statsDiv) {
      statsDiv.textContent = `共 ${totalRecords} 筆記錄`;
    }
  }

  function deleteRecord(recordId) {
    if (!confirm('確定要刪除此記錄嗎？')) {
      return;
    }

    fetch(`/api/admin/history/${encodeURIComponent(recordId)}`, { method: 'DELETE' })
      .then(handleResponse)
      .then((data) => {
        if (data.status === 'ok') {
          showToast('記錄已刪除');
          fetchHistory(currentPage);
        }
      })
      .catch((error) => {
        console.error('刪除記錄失敗', error);
        showToast('刪除失敗，請稍後再試');
      });
  }

  function handleChangePassword(event) {
    event.preventDefault();
    const submitButton = changePasswordForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.textContent = '處理中...';

    const formData = new FormData(changePasswordForm);
    const payload = {
      current_password: formData.get('current_password'),
      new_password: formData.get('new_password'),
      confirm_password: formData.get('confirm_password'),
    };

    fetch('/admin/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(handleResponse)
      .then((data) => {
        if (data.status === 'ok') {
          showToast('密碼已成功修改');
          changePasswordForm.reset();
        } else {
          throw new Error(data.message || '修改密碼失敗');
        }
      })
      .catch((error) => {
        showToast(error.message || '修改密碼失敗，請稍後再試');
      })
      .finally(() => {
        submitButton.disabled = false;
        submitButton.textContent = '修改密碼';
      });
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add('toast--visible');
    setTimeout(() => toast.classList.remove('toast--visible'), 2600);
  }

  function handleResponse(response) {
    if (!response.ok) {
      return response.json().catch(() => ({})).then((data) => {
        if (data.error) {
          throw new Error(data.error);
        }
        if (data.message) {
          throw new Error(data.message);
        }
        throw new Error('系統繁忙，請稍後再試');
      });
    }
    return response.json();
  }

  document.addEventListener('DOMContentLoaded', init);
})();

