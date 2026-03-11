// ============================================================
// GameForge Platform - Common Utilities
// ============================================================

// Toast notification
function showToast(message, type = 'info') {
  const colors = {
    success: 'bg-emerald-600',
    error: 'bg-red-600',
    info: 'bg-blue-600',
    warning: 'bg-amber-600'
  };
  const icons = {
    success: 'fa-check-circle',
    error: 'fa-exclamation-circle',
    info: 'fa-info-circle',
    warning: 'fa-exclamation-triangle'
  };

  const toast = document.createElement('div');
  toast.className = `toast ${colors[type]} text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 text-sm`;
  toast.innerHTML = `<i class="fa-solid ${icons[type]}"></i><span>${message}</span>`;

  const container = document.getElementById('toastContainer');
  container.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add('show'));

  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// Format file size
function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Format date
function formatDate(dateStr) {
  return new Date(dateStr).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });
}

// Truncate text
function truncate(str, len = 50) {
  if (!str) return '';
  return str.length > len ? str.substring(0, len) + '...' : str;
}

// Debounce
function debounce(fn, delay = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

// Download as ZIP via API
async function downloadZip(files, zipName) {
  try {
    const res = await fetch('/api/download/zip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files, zipName })
    });

    if (!res.ok) throw new Error('Download failed');

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${zipName}.zip`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Download started', 'success');
  } catch (err) {
    showToast('Download failed: ' + err.message, 'error');
  }
}

// Setup drag-and-drop zone
function setupDropZone(elementId, onFiles) {
  const zone = document.getElementById(elementId);
  if (!zone) return;

  ['dragenter', 'dragover'].forEach(evt => {
    zone.addEventListener(evt, (e) => {
      e.preventDefault();
      zone.classList.add('drag-over');
    });
  });

  ['dragleave', 'drop'].forEach(evt => {
    zone.addEventListener(evt, (e) => {
      e.preventDefault();
      zone.classList.remove('drag-over');
    });
  });

  zone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) onFiles(files);
  });
}

// Highlight code blocks
function highlightAll() {
  document.querySelectorAll('pre code').forEach(block => {
    hljs.highlightElement(block);
  });
}

// Escape HTML
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
