// ============================================================
// GameForge Platform - Design Tab
// ============================================================

let designResults = [];
let designResultIndex = 0;
let currentDesignGenre = 'all';
let currentDesignDomain = 'all';

// ---- Filter Buttons ----
document.querySelectorAll('#designGenreFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#designGenreFilters .filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentDesignGenre = btn.dataset.genre;
    loadDesignDb();
  });
});

document.querySelectorAll('#designDomainFilters .filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#designDomainFilters .filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentDesignDomain = btn.dataset.domain;
    loadDesignDb();
  });
});

// Search debounce
document.getElementById('designSearchInput')?.addEventListener('input', debounce(() => loadDesignDb(), 400));

// ---- Load Design DB ----
async function loadDesignDb() {
  const container = document.getElementById('designDbList');
  container.innerHTML = '<div class="text-center py-4"><div class="w-5 h-5 border-2 border-gf-accent border-t-transparent rounded-full spinner mx-auto"></div></div>';

  try {
    const params = new URLSearchParams({
      genre: currentDesignGenre,
      domain: currentDesignDomain,
      system: document.getElementById('designSearchInput')?.value || '',
      limit: 100
    });

    const res = await fetch(`/api/design/search?${params}`);
    const data = await res.json();

    if (!data.results || data.results.length === 0) {
      container.innerHTML = '<p class="text-xs text-gf-muted text-center py-8">No results found</p>';
      return;
    }

    container.innerHTML = data.results.map(item => {
      const sourceColor = item._source === 'expert' ? 'text-amber-400 bg-amber-400/10' : 'text-zinc-400 bg-zinc-400/10';
      const domainColors = {
        InGame: 'text-red-400', OutGame: 'text-blue-400', Balance: 'text-green-400',
        Content: 'text-purple-400', BM: 'text-amber-400', LiveOps: 'text-cyan-400',
        UX: 'text-pink-400', Social: 'text-indigo-400', Meta: 'text-teal-400'
      };

      return `
        <div class="p-3 rounded-lg border border-gf-border hover:border-zinc-600 bg-gf-surface/50 cursor-pointer transition-all card-hover"
          onclick="viewDesignDetail('${item._id}')">
          <div class="flex items-center gap-1.5 mb-1.5">
            <span class="text-[10px] px-1 py-0.5 rounded font-medium ${sourceColor}">${item._source}</span>
            <span class="text-[10px] ${domainColors[item.domain] || 'text-zinc-400'}">${item.domain || '-'}</span>
            <span class="text-[10px] text-gf-muted ml-auto">${item.score?.toFixed(2) || '0.40'}</span>
          </div>
          <div class="text-xs font-medium text-white truncate">${item.designId || item.system || 'Untitled'}</div>
          <div class="text-[10px] text-gf-muted mt-1 truncate">${item.system || item.data_type || ''}</div>
        </div>
      `;
    }).join('');

  } catch (err) {
    container.innerHTML = `<p class="text-xs text-red-400 text-center py-4">Error: ${err.message}</p>`;
  }
}

// ---- View Design Detail ----
async function viewDesignDetail(id) {
  try {
    const res = await fetch(`/api/design/${id}`);
    const data = await res.json();

    document.getElementById('designDetailTitle').textContent = data.designId || data.system || 'Detail';
    document.getElementById('designDetailContent').querySelector('pre').textContent = JSON.stringify(data, null, 2);
    document.getElementById('designDetailModal').classList.remove('hidden');
    document.getElementById('designResults').classList.add('hidden');
  } catch (err) {
    showToast('Failed to load detail', 'error');
  }
}

function closeDesignDetail() {
  document.getElementById('designDetailModal').classList.add('hidden');
}

// ---- Generate Design ----
async function generateDesign() {
  const prompt = document.getElementById('designPrompt').value.trim();
  if (!prompt) {
    showToast('Please enter a design concept', 'warning');
    return;
  }

  const btn = document.getElementById('designGenerateBtn');
  btn.disabled = true;
  btn.innerHTML = '<div class="w-4 h-4 border-2 border-white border-t-transparent rounded-full spinner inline-block mr-2"></div>Generating...';

  document.getElementById('designProgress').classList.remove('hidden');
  document.getElementById('designResults').classList.add('hidden');

  try {
    const res = await fetch('/api/design/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        genre: document.getElementById('designGenreSelect').value,
        stages: document.getElementById('designStageSelect').value,
        references: []
      })
    });

    const data = await res.json();

    if (data.success) {
      showToast('Design generation task queued', 'success');
      // Show placeholder results
      designResults = [{
        name: 'task_info.json',
        content: JSON.stringify({ taskId: data.taskId, message: data.message, status: 'queued' }, null, 2)
      }];
      designResultIndex = 0;
      renderDesignResult();
      document.getElementById('designResults').classList.remove('hidden');
    } else {
      showToast(data.error || 'Generation failed', 'error');
    }
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  } finally {
    document.getElementById('designProgress').classList.add('hidden');
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles mr-1.5"></i>Generate';
  }
}

// ---- Result Navigation ----
function renderDesignResult() {
  if (designResults.length === 0) return;
  const result = designResults[designResultIndex];
  document.getElementById('designResultTitle').textContent = result.name;
  document.getElementById('designResultContent').querySelector('pre').textContent = result.content;
  document.getElementById('designResultIndex').textContent = `${designResultIndex + 1} / ${designResults.length}`;
}

function prevDesignResult() {
  if (designResultIndex > 0) { designResultIndex--; renderDesignResult(); }
}

function nextDesignResult() {
  if (designResultIndex < designResults.length - 1) { designResultIndex++; renderDesignResult(); }
}

// ---- Download ZIP ----
function downloadDesignZip() {
  if (designResults.length === 0) {
    showToast('No results to download', 'warning');
    return;
  }
  downloadZip(designResults, 'design_output');
}

// ---- Templates ----
function loadTemplate(type) {
  const templates = {
    rpg: 'Medieval fantasy RPG with turn-based combat system.\n- 5 character classes (Warrior, Mage, Archer, Healer, Rogue)\n- Equipment system with rarity tiers\n- Stage-based progression with boss encounters\n- Gacha character recruitment',
    idle: 'Idle clicker game with factory production theme.\n- Tap to produce resources\n- Auto-production upgrades\n- Prestige system with permanent bonuses\n- Multiple production lines',
    puzzle: 'Match-3 puzzle game with level progression.\n- 8x8 grid with special pieces\n- Star rating system (1-3 stars)\n- Power-ups and boosters\n- Limited moves per level'
  };
  document.getElementById('designPrompt').value = templates[type] || '';
}

// ---- Init ----
loadDesignDb();
