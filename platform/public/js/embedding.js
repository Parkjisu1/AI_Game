// ============================================================
// GameForge Platform - Embedding Tab
// ============================================================

let parsedFiles = [];

// ---- File Upload ----
setupDropZone('embDropZone', handleEmbFiles);

document.getElementById('embFileInput')?.addEventListener('change', (e) => {
  handleEmbFiles(e.target.files);
  e.target.value = '';
});

document.getElementById('embFileInputFiles')?.addEventListener('change', (e) => {
  handleEmbFiles(e.target.files);
  e.target.value = '';
});

async function handleEmbFiles(fileList) {
  const formData = new FormData();
  let count = 0;

  for (const file of fileList) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (['cs', 'yaml', 'yml', 'json', 'txt'].includes(ext)) {
      formData.append('files', file);
      count++;
    }
  }

  if (count === 0) {
    showToast('No supported files found (.cs, .yaml, .json, .txt)', 'warning');
    return;
  }

  showToast(`Parsing ${count} files...`, 'info');

  try {
    const res = await fetch('/api/embedding/parse', {
      method: 'POST',
      body: formData
    });

    const data = await res.json();
    parsedFiles = data.files || [];

    // Apply manual overrides
    applyManualOverrides();

    renderParsedFiles();
    document.getElementById('embCommitBtn').disabled = parsedFiles.length === 0;
    document.getElementById('embFileCount').textContent = `${parsedFiles.length} files`;

    showToast(`${parsedFiles.length} files parsed`, 'success');
  } catch (err) {
    showToast('Parse error: ' + err.message, 'error');
  }
}

function applyManualOverrides() {
  const targetDb = document.getElementById('embTargetDb').value;
  const layer = document.getElementById('embLayer').value;
  const genre = document.getElementById('embGenre').value;
  const role = document.getElementById('embRole').value;
  const domain = document.getElementById('embDomain').value;

  parsedFiles.forEach(f => {
    if (targetDb !== 'auto') f.targetDb = targetDb;
    if (layer !== 'auto') f.layer = layer;
    if (genre) f.genre = genre;
    if (role !== 'auto') f.role = role;
    if (domain !== 'auto') f.domain = domain;
  });
}

function renderParsedFiles() {
  const container = document.getElementById('embFileList');

  if (parsedFiles.length === 0) {
    container.innerHTML = '<p class="text-sm text-gf-muted text-center py-12">No files uploaded yet</p>';
    return;
  }

  const typeIcons = {
    'C# Source': 'fa-file-code text-blue-400',
    'Design Document': 'fa-file-lines text-purple-400',
    'JSON Data': 'fa-file-code text-amber-400',
    'Unknown': 'fa-file text-zinc-400'
  };

  container.innerHTML = parsedFiles.map((f, i) => `
    <div class="p-3 rounded-lg border border-gf-border bg-gf-surface/50 card-hover cursor-pointer"
      onclick="showParsePreview(${i})">
      <div class="flex items-start gap-3">
        <i class="fa-solid ${typeIcons[f.type] || typeIcons.Unknown} text-lg mt-0.5 flex-shrink-0"></i>
        <div class="flex-1 min-w-0">
          <div class="text-xs font-medium text-white truncate">${f.filename}</div>
          <div class="flex items-center gap-2 mt-1">
            <span class="text-[10px] text-gf-muted">${formatSize(f.size)}</span>
            <span class="text-[10px] px-1 py-0.5 rounded bg-gf-surface text-zinc-400">${f.type}</span>
            <span class="text-[10px] text-gf-muted">${f.targetDb}</span>
          </div>
          ${f.classes ? `<div class="text-[10px] text-zinc-500 mt-1">Classes: ${f.classes.join(', ')}</div>` : ''}
          <div class="flex items-center gap-1.5 mt-1.5">
            ${f.detectedLayer || f.layer ? `<span class="text-[10px] px-1 py-0.5 rounded bg-blue-500/10 text-blue-400">${f.layer || f.detectedLayer}</span>` : ''}
            ${f.detectedRole || f.role ? `<span class="text-[10px] px-1 py-0.5 rounded bg-green-500/10 text-green-400">${f.role || f.detectedRole}</span>` : ''}
            ${f.detectedDomain || f.domain ? `<span class="text-[10px] px-1 py-0.5 rounded bg-purple-500/10 text-purple-400">${f.domain || f.detectedDomain}</span>` : ''}
            <span class="text-[10px] px-1 py-0.5 rounded bg-gf-accent/10 text-gf-accent">${f.genre || f.detectedGenre || 'Generic'}</span>
          </div>
        </div>
        <button onclick="event.stopPropagation();parsedFiles.splice(${i},1);renderParsedFiles();document.getElementById('embFileCount').textContent=parsedFiles.length+' files';document.getElementById('embCommitBtn').disabled=parsedFiles.length===0"
          class="text-gf-muted hover:text-gf-danger transition-colors text-xs flex-shrink-0">
          <i class="fa-solid fa-trash-can"></i>
        </button>
      </div>
    </div>
  `).join('');
}

function showParsePreview(index) {
  const file = parsedFiles[index];
  const preview = document.getElementById('embParsePreview');
  const content = document.getElementById('embParseContent');

  const previewData = {
    filename: file.filename,
    targetDb: file.targetDb,
    layer: file.layer || file.detectedLayer,
    genre: file.genre || file.detectedGenre,
    role: file.role || file.detectedRole,
    domain: file.domain || file.detectedDomain,
    type: file.type,
    classes: file.classes,
    namespace: file.namespace,
    score: 0.4
  };

  content.textContent = JSON.stringify(previewData, null, 2);
  preview.classList.remove('hidden');
}

// ---- Commit to MongoDB ----
async function commitToMongo() {
  if (parsedFiles.length === 0) return;

  const btn = document.getElementById('embCommitBtn');
  btn.disabled = true;
  btn.innerHTML = '<div class="w-4 h-4 border-2 border-white border-t-transparent rounded-full spinner inline-block mr-2"></div>Uploading...';

  // Apply latest manual overrides
  applyManualOverrides();

  try {
    const res = await fetch('/api/embedding/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files: parsedFiles })
    });

    const data = await res.json();

    if (data.success) {
      const msg = data.pendingCount
        ? `${data.pendingCount} files submitted for admin review`
        : `Uploaded: ${data.codeCount} code + ${data.designCount} design files`;
      showToast(msg, 'success');
      parsedFiles = [];
      renderParsedFiles();
      document.getElementById('embFileCount').textContent = '0 files';
      document.getElementById('embParsePreview').classList.add('hidden');
    } else {
      showToast(data.error || 'Upload failed', 'error');
    }
  } catch (err) {
    showToast('Upload error: ' + err.message, 'error');
  } finally {
    btn.disabled = parsedFiles.length === 0;
    btn.innerHTML = '<i class="fa-solid fa-rocket mr-1.5"></i>Upload to MongoDB';
  }
}

// ---- Settings change → re-apply overrides ----
['embTargetDb', 'embLayer', 'embGenre', 'embRole', 'embDomain'].forEach(id => {
  document.getElementById(id)?.addEventListener('change', () => {
    if (parsedFiles.length > 0) {
      applyManualOverrides();
      renderParsedFiles();
    }
  });
});
