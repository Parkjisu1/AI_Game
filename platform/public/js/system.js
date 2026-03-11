// ============================================================
// GameForge Platform - System Tab
// ============================================================

let codeResults = [];
let codeResultIndex = 0;
let attachedFiles = [];
let uiRefImages = [];
let selectedCodeIds = new Set();
let codeDbItems = [];

// ---- Engine & Genre change ----
document.getElementById('sysGenreSelect')?.addEventListener('change', () => loadCodeDb());
document.getElementById('engineSelect')?.addEventListener('change', () => {
  // Show/hide resolution for playable
  const engine = document.getElementById('engineSelect').value;
  if (engine === 'playable') {
    document.getElementById('resolutionSelect').closest('div').classList.add('opacity-50');
  } else {
    document.getElementById('resolutionSelect').closest('div').classList.remove('opacity-50');
  }
});

// Custom resolution toggle
document.getElementById('resolutionSelect')?.addEventListener('change', (e) => {
  const custom = document.getElementById('customResolution');
  if (e.target.value === 'custom') {
    custom.classList.remove('hidden');
  } else {
    custom.classList.add('hidden');
  }
});

// ---- Layer Filter ----
document.querySelectorAll('#codeLayerFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#codeLayerFilters .filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    loadCodeDb();
  });
});

// Code search debounce
document.getElementById('codeSearchInput')?.addEventListener('input', debounce(() => loadCodeDb(), 400));

// Select all toggle
document.getElementById('selectAllCode')?.addEventListener('change', (e) => {
  if (e.target.checked) {
    codeDbItems.forEach(item => selectedCodeIds.add(item._id));
  } else {
    selectedCodeIds.clear();
  }
  renderCodeDbList();
  updateSelectedCount();
});

// ---- Load Code DB ----
async function loadCodeDb() {
  const container = document.getElementById('codeDbList');
  container.innerHTML = '<div class="text-center py-4"><div class="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full spinner mx-auto"></div></div>';

  const genre = document.getElementById('sysGenreSelect')?.value || 'Generic';
  const activeLayer = document.querySelector('#codeLayerFilters .filter-btn.active');
  const layer = activeLayer?.dataset.layer || 'all';
  const search = document.getElementById('codeSearchInput')?.value || '';

  try {
    const params = new URLSearchParams({ genre, layer, system: search, limit: 100 });
    const res = await fetch(`/api/code/search?${params}`);
    const data = await res.json();

    codeDbItems = data.results || [];

    // Auto-select all if selectAll is checked
    if (document.getElementById('selectAllCode')?.checked) {
      codeDbItems.forEach(item => selectedCodeIds.add(item._id));
    }

    renderCodeDbList();
    updateSelectedCount();
  } catch (err) {
    container.innerHTML = `<p class="text-xs text-red-400 text-center py-4">Error: ${err.message}</p>`;
  }
}

function renderCodeDbList() {
  const container = document.getElementById('codeDbList');

  if (codeDbItems.length === 0) {
    container.innerHTML = '<p class="text-xs text-gf-muted text-center py-8">No results found</p>';
    return;
  }

  const layerColors = { Core: 'text-amber-400', Domain: 'text-blue-400', Game: 'text-green-400' };
  const sourceColors = { expert: 'text-amber-400 bg-amber-400/10', base: 'text-zinc-400 bg-zinc-400/10' };

  container.innerHTML = codeDbItems.map(item => `
    <label class="flex items-start gap-2 p-2.5 rounded-lg border cursor-pointer transition-all
      ${selectedCodeIds.has(item._id) ? 'border-blue-500/50 bg-blue-500/5' : 'border-gf-border hover:border-zinc-600 bg-gf-surface/50'}">
      <input type="checkbox" ${selectedCodeIds.has(item._id) ? 'checked' : ''}
        onchange="toggleCodeSelect('${item._id}')" class="mt-0.5 rounded flex-shrink-0">
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-1.5 mb-1">
          <span class="text-[10px] px-1 py-0.5 rounded font-medium ${sourceColors[item._source] || sourceColors.base}">${item._source}</span>
          <span class="text-[10px] ${layerColors[item.layer] || 'text-zinc-400'}">${item.layer || '-'}</span>
          <span class="text-[10px] text-gf-muted">${item.role || ''}</span>
          <span class="text-[10px] text-gf-muted ml-auto">${item.score?.toFixed(2) || '0.40'}</span>
        </div>
        <div class="text-xs font-medium text-white truncate">${item.fileId || item.system || 'Untitled'}</div>
      </div>
    </label>
  `).join('');
}

function toggleCodeSelect(id) {
  if (selectedCodeIds.has(id)) {
    selectedCodeIds.delete(id);
  } else {
    selectedCodeIds.add(id);
  }

  // Update selectAll checkbox
  const selectAll = document.getElementById('selectAllCode');
  selectAll.checked = selectedCodeIds.size === codeDbItems.length;

  updateSelectedCount();
}

function updateSelectedCount() {
  document.getElementById('codeSelectedCount').textContent = `${selectedCodeIds.size} selected`;
}

// ---- File Attachment ----
setupDropZone('sysDropZone', handleDesignFiles);

document.getElementById('sysFileInput')?.addEventListener('change', (e) => {
  handleDesignFiles(e.target.files);
  e.target.value = '';
});

function handleDesignFiles(fileList) {
  for (const file of fileList) {
    const reader = new FileReader();
    reader.onload = () => {
      attachedFiles.push({
        name: file.name,
        size: file.size,
        content: reader.result,
        file
      });
      renderAttachedFiles();
    };
    reader.readAsText(file);
  }
}

function addUrlFile() {
  const url = document.getElementById('sysUrlInput')?.value.trim();
  if (!url) return;
  attachedFiles.push({ name: url.split('/').pop() || 'url_file', size: 0, content: '', url });
  document.getElementById('sysUrlInput').value = '';
  renderAttachedFiles();
  showToast('URL added', 'info');
}

function renderAttachedFiles() {
  const container = document.getElementById('sysAttachedFiles');
  if (attachedFiles.length === 0) {
    container.innerHTML = '<p class="text-[11px] text-gf-muted text-center py-2">No files attached</p>';
    return;
  }

  container.innerHTML = attachedFiles.map((f, i) => `
    <div class="flex items-center gap-2 p-2 rounded-lg bg-gf-surface/50 border border-gf-border">
      <i class="fa-solid ${f.url ? 'fa-link text-cyan-400' : 'fa-file-code text-gf-accent'} text-xs"></i>
      <div class="flex-1 min-w-0">
        <div class="text-[11px] text-white truncate">${f.name}</div>
        ${f.size ? `<div class="text-[10px] text-gf-muted">${formatSize(f.size)}</div>` : ''}
      </div>
      <button onclick="removeAttachedFile(${i})" class="text-gf-muted hover:text-gf-danger transition-colors text-xs flex-shrink-0">
        <i class="fa-solid fa-xmark"></i>
      </button>
    </div>
  `).join('');
}

function removeAttachedFile(index) {
  attachedFiles.splice(index, 1);
  renderAttachedFiles();
}

// ---- UI Reference Images ----
setupDropZone('uiRefDropZone', handleUiRefImages);

document.getElementById('uiRefInput')?.addEventListener('change', (e) => {
  handleUiRefImages(e.target.files);
  e.target.value = '';
});

function handleUiRefImages(fileList) {
  for (const file of fileList) {
    if (!file.type.startsWith('image/')) continue;
    const reader = new FileReader();
    reader.onload = () => {
      uiRefImages.push({ name: file.name, dataUrl: reader.result });
      renderUiRefImages();
    };
    reader.readAsDataURL(file);
  }
}

function renderUiRefImages() {
  const container = document.getElementById('uiRefList');
  container.innerHTML = uiRefImages.map((img, i) => `
    <div class="relative group">
      <img src="${img.dataUrl}" alt="${img.name}" class="w-16 h-16 object-cover rounded-lg border border-gf-border">
      <button onclick="uiRefImages.splice(${i},1);renderUiRefImages()"
        class="absolute -top-1 -right-1 w-4 h-4 bg-gf-danger rounded-full text-white text-[8px] flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
        <i class="fa-solid fa-xmark"></i>
      </button>
    </div>
  `).join('');
}

// ---- Generate Code ----
async function generateCode() {
  const btn = document.getElementById('codeGenerateBtn');
  btn.disabled = true;
  btn.innerHTML = '<div class="w-4 h-4 border-2 border-white border-t-transparent rounded-full spinner inline-block mr-2"></div>Generating...';

  document.getElementById('codeProgress').classList.remove('hidden');
  document.getElementById('codeResults').classList.add('hidden');

  try {
    const formData = new FormData();
    formData.append('genre', document.getElementById('sysGenreSelect').value);
    formData.append('engine', document.getElementById('engineSelect').value);
    formData.append('resolution', document.getElementById('resolutionSelect').value === 'custom'
      ? document.getElementById('customResInput').value
      : document.getElementById('resolutionSelect').value);
    formData.append('selectedDbIds', JSON.stringify([...selectedCodeIds]));
    formData.append('prompt', '');

    // Attach design files
    for (const f of attachedFiles) {
      if (f.file) formData.append('designFiles', f.file);
    }

    const res = await fetch('/api/code/generate', { method: 'POST', body: formData });
    const data = await res.json();

    if (data.success) {
      showToast('Code generation task queued', 'success');
      codeResults = [{
        name: 'task_info.json',
        content: JSON.stringify({ taskId: data.taskId, message: data.message, status: 'queued' }, null, 2)
      }];
      codeResultIndex = 0;
      renderCodeResult();
      document.getElementById('codeResults').classList.remove('hidden');
    } else {
      showToast(data.error || 'Generation failed', 'error');
    }
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  } finally {
    document.getElementById('codeProgress').classList.add('hidden');
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-terminal mr-1.5"></i>Generate Code';
  }
}

// ---- Result Navigation ----
function renderCodeResult() {
  if (codeResults.length === 0) return;
  const result = codeResults[codeResultIndex];
  document.getElementById('codeResultTitle').textContent = result.name;
  const codeEl = document.getElementById('codeResultContent').querySelector('code');
  codeEl.textContent = result.content;
  codeEl.className = result.name.endsWith('.cs') ? 'language-csharp' : 'language-json';
  hljs.highlightElement(codeEl);
  document.getElementById('codeResultIndex').textContent = `${codeResultIndex + 1} / ${codeResults.length}`;
}

function prevCodeResult() {
  if (codeResultIndex > 0) { codeResultIndex--; renderCodeResult(); }
}

function nextCodeResult() {
  if (codeResultIndex < codeResults.length - 1) { codeResultIndex++; renderCodeResult(); }
}

function downloadCodeZip() {
  if (codeResults.length === 0) {
    showToast('No results to download', 'warning');
    return;
  }
  downloadZip(codeResults, 'code_output');
}

// ---- Init ----
loadCodeDb();
