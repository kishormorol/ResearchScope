/**
 * ResearchScope – shared JS utilities
 */

// ── Theme ─────────────────────────────────────────────────────────────
const THEME_KEY = 'rs-theme';

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_KEY, theme);
  const icon = document.getElementById('theme-icon');
  if (icon) icon.textContent = theme === 'dark' ? '☀️' : '🌙';
}

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  const preferred = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  applyTheme(saved || preferred);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  applyTheme(current === 'dark' ? 'light' : 'dark');
}

// ── Data fetching ──────────────────────────────────────────────────────
async function fetchData(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`fetchData(${url}) failed:`, err.message);
    return null;
  }
}

// ── Debounce ───────────────────────────────────────────────────────────
function debounce(fn, delay = 250) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

// ── Render helpers ─────────────────────────────────────────────────────
function renderBadge(text, type = 'tag') {
  return `<span class="badge badge-${type}">${escHtml(text)}</span>`;
}

function difficultyBadge(d) {
  return renderBadge(d || 'intermediate', d || 'intermediate');
}

function scoreBadge(score) {
  return `<span class="badge badge-score">⭐ ${(+score || 0).toFixed(1)}</span>`;
}

function tagChips(tags) {
  if (!tags || !tags.length) return '';
  return tags.map(t => renderBadge(t, 'tag')).join(' ');
}

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function truncate(str, max = 120) {
  if (!str) return '';
  return str.length > max ? str.slice(0, max) + '…' : str;
}

// ── Difficulty badge ───────────────────────────────────────────────────
function difficultyBadge(paper) {
  const lvl = paper.difficulty_level || paper.difficulty || 'L2';
  const labels = { L1: 'L1 Beginner', L2: 'L2 Intermediate', L3: 'L3 Advanced', L4: 'L4 Frontier',
                   beginner: 'L1 Beginner', intermediate: 'L2 Intermediate', advanced: 'L3 Advanced', frontier: 'L4 Frontier' };
  const cls = { L1: 'badge-l1', L2: 'badge-l2', L3: 'badge-l3', L4: 'badge-l4',
                beginner: 'badge-l1', intermediate: 'badge-l2', advanced: 'badge-l3', frontier: 'badge-l4' };
  return `<span class="badge ${cls[lvl] || 'badge-l2'}">${labels[lvl] || lvl}</span>`;
}

// ── Conference rank badge ──────────────────────────────────────────────
function rankBadge(rank) {
  if (!rank) return '';
  const cls = rank === 'A*' ? 'rank-astar' : (rank === 'A' ? 'rank-a' : 'rank-b');
  return `<span class="badge ${cls}">${escHtml(rank)}</span>`;
}

// ── Source badge ───────────────────────────────────────────────────────
function sourceBadge(paper) {
  const src = paper.source || '';
  if (src === 'arxiv') return `<span class="badge badge-arxiv">arXiv</span>`;
  if (src.includes('acl')) return `<span class="badge badge-acl">ACL</span>`;
  return `<span class="badge badge-conf">${escHtml(paper.venue || src)}</span>`;
}

// ── Score bar ──────────────────────────────────────────────────────────
function scoreBar(label, score, max = 10) {
  const pct = Math.round((score || 0) / max * 100);
  return `<div class="score-bar-wrap">
    <span style="font-size:0.72rem;color:var(--rs-muted);min-width:9rem">${escHtml(label)}</span>
    <div class="score-bar-bg"><div class="score-bar-fill" style="width:${pct}%"></div></div>
    <span class="score-bar-label">${(+score || 0).toFixed(1)}</span>
  </div>`;
}

// ── Paper card (used in homepage & topics) ─────────────────────────────
function renderPaperCard(paper, opts = {}) {
  const url = paper.paper_url || paper.url || '#';
  const authors = (paper.authors || []).slice(0, 3).join(', ');
  const extra   = (paper.authors || []).length > 3 ? ` +${paper.authors.length - 3}` : '';
  const typeStr = paper.paper_type ? `<span class="badge badge-type">${escHtml(paper.paper_type)}</span>` : '';
  const whyStr  = paper.why_it_matters
    ? `<p class="text-xs mt-2 italic" style="color:var(--rs-primary)">${escHtml(truncate(paper.why_it_matters, 160))}</p>`
    : '';
  return `
  <div class="rs-card p-5 mb-4">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div class="flex-1 min-w-0">
        <a href="${escHtml(url)}" target="_blank" rel="noopener"
           class="text-base font-semibold hover:text-indigo-600 transition-colors">
          ${escHtml(paper.title)}
        </a>
        <p class="text-xs mt-1" style="color:var(--rs-muted)">
          ${escHtml(authors)}${escHtml(extra)} &middot; ${escHtml(paper.venue || '')} ${paper.year || ''}
        </p>
      </div>
      <div class="flex gap-1 flex-shrink-0 flex-wrap">
        <span class="badge badge-score">⭐ ${(+paper.paper_score || 0).toFixed(1)}</span>
        ${difficultyBadge(paper)}
        ${rankBadge(paper.conference_rank)}
        ${sourceBadge(paper)}
      </div>
    </div>
    ${whyStr}
    <p class="text-sm mt-3 leading-relaxed" style="color:var(--rs-muted)">
      ${escHtml(truncate(paper.summary || paper.abstract, 200))}
    </p>
    <div class="mt-3 flex flex-wrap gap-1">
      ${typeStr}
      ${tagChips(paper.tags)}
    </div>
    ${opts.showScoreBars ? `
    <div class="mt-3 border-t pt-3" style="border-color:var(--rs-border)">
      ${scoreBar('Paper Score', paper.paper_score)}
      ${scoreBar('Read First', paper.read_first_score)}
      ${scoreBar('Content Potential', paper.content_potential_score)}
    </div>` : ''}
  </div>`;
}

// ── Stats bar ──────────────────────────────────────────────────────────
async function loadStats() {
  const stats = await fetchData('data/stats.json');
  if (!stats) return;
  const map = {
    'stat-papers':  stats.total_papers,
    'stat-topics':  stats.total_topics,
    'stat-authors': stats.total_authors,
    'stat-gaps':    stats.total_gaps,
    'stat-labs':    stats.total_labs,
    'stat-unis':    stats.total_universities,
  };
  for (const [id, val] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (el) el.textContent = (val ?? 0).toLocaleString();
  }
  const genEl = document.getElementById('stat-generated');
  if (genEl && stats.generated_at) {
    genEl.textContent = 'Updated ' + new Date(stats.generated_at).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' });
  }
}

// ── Paginator ──────────────────────────────────────────────────────────
function renderPaginator(containerId, current, total, onChange) {
  const el = document.getElementById(containerId);
  if (!el || total <= 1) return;
  let html = `<div class="flex gap-1 flex-wrap justify-center mt-4">`;
  html += `<button class="pager-btn" onclick="(${onChange})(${current - 1})" ${current <= 1 ? 'disabled' : ''}>← Prev</button>`;
  const pages = Math.min(total, 7);
  let start = Math.max(1, current - 3);
  let end   = Math.min(total, start + pages - 1);
  start = Math.max(1, end - pages + 1);
  for (let p = start; p <= end; p++) {
    html += `<button class="pager-btn ${p === current ? 'active' : ''}" onclick="(${onChange})(${p})">${p}</button>`;
  }
  html += `<button class="pager-btn" onclick="(${onChange})(${current + 1})" ${current >= total ? 'disabled' : ''}>Next →</button>`;
  html += `</div>`;
  el.innerHTML = html;
}

// ── Search / filter ────────────────────────────────────────────────────
function buildSearchFilter(fields) {
  return (item, query) => {
    const q = query.toLowerCase();
    return fields.some(f => (item[f] || '').toString().toLowerCase().includes(q));
  };
}

// ── Spinner / empty ────────────────────────────────────────────────────
function showSpinner(containerId) {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = '<div class="spinner"></div>';
}

function showEmpty(containerId, msg = 'No data available') {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = `
    <div class="empty-state">
      <svg width="48" height="48" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
      </svg>
      <p class="text-lg font-medium">${escHtml(msg)}</p>
      <p class="text-sm mt-1">Run the pipeline to generate data, or check back later.</p>
    </div>`;
}

// ── Init ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  const toggle = document.getElementById('theme-toggle');
  if (toggle) toggle.addEventListener('click', toggleTheme);

  // Highlight active nav link
  const path = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.rs-nav a[href]').forEach(a => {
    if (a.getAttribute('href') === path) a.classList.add('active');
  });
});
