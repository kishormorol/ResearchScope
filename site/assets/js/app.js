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

// ── Paper card (used in index) ─────────────────────────────────────────
function renderPaperCard(paper) {
  const authors = (paper.authors || []).slice(0, 3).join(', ');
  const extra   = (paper.authors || []).length > 3 ? ` +${paper.authors.length - 3}` : '';
  return `
  <div class="rs-card p-5 mb-4">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div class="flex-1 min-w-0">
        <a href="${escHtml(paper.url)}" target="_blank" rel="noopener"
           class="text-base font-semibold hover:text-indigo-600 transition-colors line-clamp-2">
          ${escHtml(paper.title)}
        </a>
        <p class="text-sm mt-1" style="color:var(--rs-muted)">
          ${escHtml(authors)}${escHtml(extra)} · ${escHtml(paper.venue || '')} · ${paper.year || ''}
        </p>
      </div>
      <div class="flex gap-2 flex-shrink-0">
        ${scoreBadge(paper.read_first_score)}
        ${difficultyBadge(paper.difficulty)}
      </div>
    </div>
    <p class="text-sm mt-3 leading-relaxed" style="color:var(--rs-muted)">
      ${escHtml(truncate(paper.abstract, 200))}
    </p>
    <div class="mt-3 flex flex-wrap gap-1">
      ${tagChips(paper.tags)}
    </div>
  </div>`;
}

// ── Stats bar ──────────────────────────────────────────────────────────
async function loadStats() {
  const stats = await fetchData('/data/stats.json');
  if (!stats) return;
  const map = {
    'stat-papers':  stats.total_papers,
    'stat-topics':  stats.total_topics,
    'stat-authors': stats.total_authors,
    'stat-gaps':    stats.total_gaps,
  };
  for (const [id, val] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (el) el.textContent = (val ?? 0).toLocaleString();
  }
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
