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
  return `<span class="badge badge-score score-badge-tip" title="Paper score (0–10): weighted by citation impact, recency, venue rank, topic relevance, and content quality">⭐ ${(+score || 0).toFixed(1)}</span>`;
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

// ── Extract arXiv ID from a paper URL ──────────────────────────────────
function extractArxivId(url) {
  if (!url) return null;
  const m = url.match(/arxiv\.org\/(?:abs|pdf)\/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)/);
  return m ? m[1] : null;
}

// ── CiteLens link for a paper (only when arXiv ID is available) ─────────
function citelensBtn(paper) {
  const arxivId = extractArxivId(paper.paper_url || paper.url || '');
  if (!arxivId) return '';
  const href = `https://kishormorol.github.io/CiteLens/?q=${encodeURIComponent(arxivId)}`;
  return `<a href="${escHtml(href)}" target="_blank" rel="noopener"
    class="mt-3 inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-md border"
    style="color:var(--rs-primary);border-color:var(--rs-primary);opacity:0.85"
    title="See who cited this paper — powered by CiteLens">
    🔍 Analyze citations
  </a>`;
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
    ${citelensBtn(paper)}
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

// ── Global Search ─────────────────────────────────────────────────────
let _searchData = null;

async function loadSearchData() {
  if (_searchData) return _searchData;
  const [papers, authors, topics] = await Promise.all([
    fetch('data/search_index.json').then(r => r.json()).catch(() => []),
    fetch('data/authors.json').then(r => r.json()).catch(() => []),
    fetch('data/topics.json').then(r => r.json()).catch(() => []),
  ]);
  _searchData = { papers, authors, topics };
  return _searchData;
}

function runSearch(query, data, limit = 5) {
  const q = query.toLowerCase().trim();
  if (!q) return { papers: [], authors: [], topics: [] };

  const papers = data.papers
    .filter(p => p.title?.toLowerCase().includes(q) ||
                 p.abstract?.toLowerCase().includes(q) ||
                 p.authors?.some(a => a.toLowerCase().includes(q)))
    .slice(0, limit);

  const authors = data.authors
    .filter(a => a.name?.toLowerCase().includes(q))
    .slice(0, limit);

  const topics = data.topics
    .filter(t => t.name?.toLowerCase().includes(q) ||
                 t.keywords?.some(k => k.toLowerCase().includes(q)))
    .slice(0, limit);

  return { papers, authors, topics };
}

function renderDropdown(results, query, dropdown) {
  const { papers, authors, topics } = results;
  const total = papers.length + authors.length + topics.length;

  if (total === 0) {
    dropdown.innerHTML = `<p class="search-empty">No results for "<strong>${escHtml(query)}</strong>"</p>`;
    return;
  }

  let html = '';

  if (papers.length) {
    html += `<div class="search-section-label">Papers</div>`;
    papers.forEach(p => {
      html += `<a class="search-result-item" href="papers.html?q=${encodeURIComponent(p.title)}">
        <div class="sr-title">${escHtml(p.title)}</div>
        <div class="sr-meta">${escHtml(p.venue || 'arXiv')} · ${p.year || ''}</div>
      </a>`;
    });
  }

  if (authors.length) {
    html += `<div class="search-section-label">Authors</div>`;
    authors.forEach(a => {
      html += `<a class="search-result-item" href="authors.html?q=${encodeURIComponent(a.name)}">
        <div class="sr-title">${escHtml(a.name)}</div>
        <div class="sr-meta">${a.paper_ids?.length || 0} papers</div>
      </a>`;
    });
  }

  if (topics.length) {
    html += `<div class="search-section-label">Topics</div>`;
    topics.forEach(t => {
      html += `<a class="search-result-item" href="topics.html#${escHtml(t.id)}">
        <div class="sr-title">${escHtml(t.name)}</div>
        <div class="sr-meta">${t.paper_ids?.length || 0} papers</div>
      </a>`;
    });
  }

  html += `<a class="search-see-all" href="search.html?q=${encodeURIComponent(query)}">See all results →</a>`;
  dropdown.innerHTML = html;
}

function initSearch() {
  const input    = document.getElementById('global-search');
  const dropdown = document.getElementById('search-dropdown');
  if (!input || !dropdown) return;

  let debounce;

  input.addEventListener('focus', () => loadSearchData());

  input.addEventListener('input', () => {
    clearTimeout(debounce);
    const q = input.value.trim();
    if (!q) { dropdown.classList.add('hidden'); return; }

    debounce = setTimeout(async () => {
      const data = await loadSearchData();
      const results = runSearch(q, data, 4);
      renderDropdown(results, q, dropdown);
      dropdown.classList.remove('hidden');
    }, 180);
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && input.value.trim()) {
      window.location.href = `search.html?q=${encodeURIComponent(input.value.trim())}`;
    }
    if (e.key === 'Escape') {
      dropdown.classList.add('hidden');
      input.blur();
    }
  });

  document.addEventListener('click', e => {
    if (!input.closest('.search-wrap').contains(e.target)) {
      dropdown.classList.add('hidden');
    }
  });
}

// ── GitHub Star count ─────────────────────────────────────────────────
async function initStarCount() {
  try {
    const res = await fetch('https://api.github.com/repos/kishormorol/ResearchScope');
    if (!res.ok) return;
    const data = await res.json();
    const count = data.stargazers_count ?? 0;
    const label = count >= 1000
      ? (count / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
      : String(count);
    document.querySelectorAll('.github-star-count').forEach(el => {
      el.textContent = label;
    });
  } catch (_) { /* silently fail — button still works without count */ }
}

// ── Paper of the Day ──────────────────────────────────────────────────
function pickPaperOfTheDay(papers, poolSize = 150) {
  if (!papers || !papers.length) return null;
  const pool = papers.slice(0, Math.min(poolSize, papers.length));
  const today  = new Date();
  const startOfYear = new Date(today.getFullYear(), 0, 1);
  const dayOfYear = Math.floor((today - startOfYear) / 86400000);
  return pool[dayOfYear % pool.length];
}

function tweetPaperUrl(paper) {
  const venue   = [paper.venue, paper.year].filter(Boolean).join(' ');
  const score   = paper.paper_score ? ` | ⭐ ${(+paper.paper_score).toFixed(1)}/10` : '';
  const snippet = (paper.abstract || paper.summary || '').slice(0, 160);
  const pageUrl = `https://kishormorol.github.io/ResearchScope/papers.html?q=${encodeURIComponent(paper.title || '')}`;
  const text    = `📄 ${paper.title}\n${venue}${score}\n\n${snippet}…\n\n🔭 ResearchScope\n${pageUrl}\n\n#AIResearch #MachineLearning #ResearchScope`;
  return `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}`;
}

function weekLabel() {
  const now = new Date();
  const dow = now.getDay();
  const mon = new Date(now); mon.setDate(now.getDate() - ((dow + 6) % 7));
  const sun = new Date(mon); sun.setDate(mon.getDate() + 6);
  const fmt = d => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  return `${fmt(mon)} – ${fmt(sun)}, ${now.getFullYear()}`;
}

function renderPotdCard(paper) {
  if (!paper) return '';
  const url     = paper.paper_url || paper.url || '#';
  const venue   = [paper.venue, paper.year].filter(Boolean).join(' · ');
  const authors = (paper.authors || []).slice(0, 3).join(', ');
  const extra   = (paper.authors || []).length > 3 ? ` +${paper.authors.length - 3}` : '';
  const tags    = (paper.tags || []).slice(0, 3).map(t =>
    `<span style="background:rgba(255,255,255,0.2);color:#fff;padding:2px 8px;border-radius:99px;font-size:0.7rem;font-weight:600">${escHtml(t)}</span>`
  ).join('');

  const tomorrowMs = new Date(new Date().setHours(24,0,0,0)) - Date.now();
  const hoursLeft = Math.floor(tomorrowMs / 3600000);
  const minsLeft  = Math.floor((tomorrowMs % 3600000) / 60000);
  const nextLabel = hoursLeft > 0 ? `New paper in ${hoursLeft}h ${minsLeft}m` : `New paper in ${minsLeft}m`;

  return `
  <div class="potd-wrap">
    <div class="potd-label">
      ✨ Paper of the Day
      <span style="font-size:0.65rem;opacity:0.6;font-weight:400">${new Date().toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric'})}</span>
    </div>
    <div class="potd-title">
      <a href="${escHtml(url)}" target="_blank" rel="noopener">${escHtml(paper.title)}</a>
    </div>
    <div class="potd-meta">
      ${venue ? escHtml(venue) + (authors ? ' · ' : '') : ''}${escHtml(authors)}${escHtml(extra)}
      ${paper.paper_score ? ` · ⭐ ${(+paper.paper_score).toFixed(1)}/10` : ''}
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:0.3rem;margin-bottom:0.75rem">${tags}</div>
    <p class="potd-abstract">${escHtml((paper.abstract || paper.summary || '').slice(0, 300))}</p>
    <div class="potd-actions">
      <a href="${escHtml(url)}" target="_blank" rel="noopener" class="potd-btn potd-btn-primary">Read Paper →</a>
      ${(() => { const aid = extractArxivId(url); return aid ? `<a href="https://kishormorol.github.io/CiteLens/?q=${encodeURIComponent(aid)}" target="_blank" rel="noopener" class="potd-btn potd-btn-ghost" title="See who cited this paper">🔍 Analyze citations</a>` : ''; })()}
      <a href="${escHtml(tweetPaperUrl(paper))}" target="_blank" rel="noopener" class="potd-btn potd-btn-ghost">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.738-8.835L1.254 2.25H8.08l4.259 5.631zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
        Share
      </a>
      <button onclick="copyPotdLink('${escHtml(url)}',this)" class="potd-btn potd-btn-ghost">📋 Copy Link</button>
      <span class="potd-next">${nextLabel}</span>
    </div>
  </div>`;
}

function copyPotdLink(url, btn) {
  navigator.clipboard.writeText(url).then(() => {
    const orig = btn.textContent;
    btn.textContent = '✓ Copied!';
    setTimeout(() => btn.textContent = orig, 2000);
  });
}

// ── Init ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initStarCount();
  const toggle = document.getElementById('theme-toggle');
  if (toggle) toggle.addEventListener('click', toggleTheme);

  // Highlight active nav link (desktop + mobile)
  const path = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.rs-nav a[href], .mobile-nav-link').forEach(a => {
    if (a.getAttribute('href') === path) a.classList.add('active');
  });

  // Global search
  initSearch();

  // Mobile menu toggle
  const mobileBtn  = document.getElementById('mobile-menu-btn');
  const mobileMenu = document.getElementById('mobile-menu');
  const iconOpen   = document.getElementById('hamburger-icon');
  const iconClose  = document.getElementById('close-icon');

  if (mobileBtn && mobileMenu) {
    mobileBtn.addEventListener('click', () => {
      const isOpen = !mobileMenu.classList.contains('hidden');
      mobileMenu.classList.toggle('hidden');
      iconOpen.classList.toggle('hidden', !isOpen);
      iconClose.classList.toggle('hidden', isOpen);
      mobileBtn.setAttribute('aria-expanded', String(!isOpen));
    });

    // Close menu when a link is tapped
    mobileMenu.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', () => {
        mobileMenu.classList.add('hidden');
        iconOpen.classList.remove('hidden');
        iconClose.classList.add('hidden');
        mobileBtn.setAttribute('aria-expanded', 'false');
      });
    });
  }
});
