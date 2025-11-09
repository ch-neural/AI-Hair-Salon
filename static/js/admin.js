(() => {
  const form = document.querySelector('#create-garment-form');
  const grid = document.querySelector('#admin-garment-grid');
  const emptyState = document.querySelector('#garment-empty');
  const toast = document.querySelector('#toast');

  let garments = [];

  function init() {
    parseInitialGarments();
    renderGarments();
    bindEvents();
    fetchGarments();
  }

  function parseInitialGarments() {
    try {
      const initial = grid.dataset.initial;
      if (initial) {
        garments = JSON.parse(initial);
      }
    } catch (error) {
      console.warn('無法解析髮型資料', error);
      garments = [];
    }
  }

  function bindEvents() {
    form.addEventListener('submit', handleCreateGarment);
  }

  function handleCreateGarment(event) {
    event.preventDefault();
    const submitButton = form.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.textContent = '上傳中...';

    const formData = new FormData(form);

    fetch('/api/admin/garments', {
      method: 'POST',
      body: formData,
    })
      .then(handleResponse)
      .then((data) => {
        if (data.error) {
          throw new Error(data.error);
        }
        if (data.garment) {
          garments.push(data.garment);
          renderGarments();
          form.reset();
          showToast('新增髮型完成');
        }
      })
      .catch((error) => {
        showToast(error.message || '新增失敗，請稍後再試');
      })
      .finally(() => {
        submitButton.disabled = false;
        submitButton.textContent = '新增髮型';
      });
  }

  function renderGarments() {
    grid.innerHTML = '';
    if (!garments.length) {
      emptyState.classList.remove('hidden');
      return;
    }
    emptyState.classList.add('hidden');

    garments.forEach((item) => {
      const card = document.createElement('article');
      card.className = 'garment-card';
      const img = document.createElement('img');
      img.className = 'garment-card__image';
      const src = item.image_url || `/${item.image_path}`;
      img.src = src.replace(/\/+/, '/');
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

      const actions = document.createElement('div');
      actions.className = 'garment-card__actions';

      const renameBtn = document.createElement('button');
      renameBtn.type = 'button';
      renameBtn.className = 'btn btn--ghost';
      renameBtn.textContent = '重新命名';
      renameBtn.addEventListener('click', () => renameGarment(item.garment_id));
      actions.appendChild(renameBtn);

      const deleteBtn = document.createElement('button');
      deleteBtn.type = 'button';
      deleteBtn.className = 'btn btn--ghost';
      deleteBtn.textContent = '刪除';
      deleteBtn.addEventListener('click', () => deleteGarment(item.garment_id));
      actions.appendChild(deleteBtn);

      body.appendChild(actions);
      card.appendChild(body);
      grid.appendChild(card);
    });
  }

  function renameGarment(garmentId) {
    const target = garments.find((item) => item.garment_id === garmentId);
    if (!target) {
      showToast('找不到要更新的髮型');
      return;
    }
    const newName = prompt('請輸入新的髮型名稱', target.name);
    if (!newName || newName.trim() === target.name) {
      return;
    }
    fetch(`/api/admin/garments/${encodeURIComponent(garmentId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName.trim() }),
    })
      .then(handleResponse)
      .then((data) => {
        if (data.error) {
          throw new Error(data.error);
        }
        const updated = garments.map((item) =>
          item.garment_id === garmentId ? { ...item, ...data.garment } : item
        );
        garments = updated;
        renderGarments();
        showToast('髮型名稱已更新');
      })
      .catch((error) => showToast(error.message || '更新失敗'));
  }

  function deleteGarment(garmentId) {
    if (!confirm('確定要刪除此髮型嗎？')) {
      return;
    }
    fetch(`/api/admin/garments/${encodeURIComponent(garmentId)}`, { method: 'DELETE' })
      .then(handleResponse)
      .then((data) => {
        if (data.error) {
          throw new Error(data.error);
        }
        garments = garments.filter((item) => item.garment_id !== garmentId);
        renderGarments();
        showToast('已刪除髮型');
      })
      .catch((error) => showToast(error.message || '刪除失敗'));
  }

  function fetchGarments() {
    fetch('/api/garments')
      .then(handleResponse)
      .then((data) => {
        if (Array.isArray(data.garments)) {
          garments = data.garments;
          renderGarments();
        }
      })
      .catch((error) => console.warn('更新髮型清單失敗', error));
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
        throw new Error('系統繁忙，請稍後再試');
      });
    }
    return response.json();
  }

  document.addEventListener('DOMContentLoaded', init);
})();

