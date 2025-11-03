// Theme toggle (works with Bootstrap 5.3 data-bs-theme)
(function () {
  const root = document.documentElement;
  const key = 'us-theme';
  function apply(theme) { root.setAttribute('data-bs-theme', theme); }
  const saved = localStorage.getItem(key);
  apply(saved || 'light');
  const btn = document.getElementById('themeToggle');
  if (btn) {
    btn.addEventListener('click', function () {
      const current = root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
      apply(current);
      localStorage.setItem(key, current);
      this.innerHTML = current === 'dark' ? '<i class="bi bi-sun"></i>' : '<i class="bi bi-moon-stars"></i>';
    });
    btn.innerHTML = (saved === 'dark') ? '<i class="bi bi-sun"></i>' : '<i class="bi bi-moon-stars"></i>';
  }
})();

// Convert Flask flash messages into Bootstrap Toasts
(function () {
  const container = document.getElementById('toastContainer');
  const source = document.getElementById('_flash_messages');
  if (!container || !source) return;
  const items = Array.from(source.querySelectorAll('._msg')).map(el => el.textContent.trim()).filter(Boolean);
  items.forEach((text, idx) => {
    const toastEl = document.createElement('div');
    toastEl.className = 'toast align-items-center text-bg-info border-0';
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');
    toastEl.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">${text}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>`;
    container.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl, { delay: 3500 + idx * 200 });
    toast.show();
  });
})();

// Simple table filter: input[data-table-filter="#tableId"]
(function(){
  document.querySelectorAll('input[data-table-filter]').forEach(input => {
    const sel = input.getAttribute('data-table-filter');
    const table = document.querySelector(sel);
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    input.addEventListener('input', function(){
      const q = this.value.toLowerCase();
      tbody.querySelectorAll('tr').forEach(tr => {
        const text = tr.textContent.toLowerCase();
        tr.style.display = text.includes(q) ? '' : 'none';
      });
    });
  });
})();

