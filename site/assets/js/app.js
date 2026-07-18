/**
 * ResearchScope – shared JS utilities
 */

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
  return `<span class="badge badge-score score-badge-tip" title="Paper score (0–10): weighted by citation impact, recency, venue rank, acceptance tier (oral/spotlight), topic relevance, and content quality">${(+score || 0).toFixed(1)}</span>`;
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

function paperWorkspaceUrl(paper) {
  return paper?.paper_url || paper?.url || paper?.pdf_url || '#';
}
window.paperWorkspaceUrl = paperWorkspaceUrl;

function toggleDisclosure(button, targetId) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const opening = target.classList.contains('hidden');
  target.classList.toggle('hidden', !opening);
  button?.setAttribute('aria-expanded', String(opening));
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

// ── Acceptance-tier badge (oral / spotlight) ───────────────────────────
// Only oral & spotlight are shown — they mark the top decile of accepted
// work. Posters are the default tier and get no badge to avoid clutter.
function presentationBadge(type) {
  const t = (type || '').toLowerCase();
  if (t === 'oral')      return `<span class="badge badge-oral" title="Oral presentation — top accepted tier">Oral</span>`;
  if (t === 'spotlight') return `<span class="badge badge-spotlight" title="Spotlight — highlighted accepted paper">Spotlight</span>`;
  return '';
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
  const m = url.match(/arxiv\.org\/(?:abs|pdf)\/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)(?![0-9])/);
  return m ? m[1] : null;
}

// ── CiteLens link for a paper (only when arXiv ID is available) ─────────
function citelensBtn(paper) {
  const arxivId = extractArxivId(paper.paper_url || paper.url || '');
  if (!arxivId) return '';
  const href = `https://kishormorol.github.io/CiteLens/?q=${encodeURIComponent(arxivId)}`;
  return `<a href="${escHtml(href)}" target="_blank" rel="noopener"
    class="mt-3 inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-md border"
    style="color:var(--rs-primary);border-color:var(--rs-primary)"
    title="See who cited this paper — powered by CiteLens">
    Analyze citations
  </a>`;
}

// ── Paper card (used in homepage & topics) ─────────────────────────────
function renderPaperCard(paper, opts = {}) {
  const url = paperWorkspaceUrl(paper);
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
           class="text-base font-semibold rs-table-title-link">
          ${escHtml(paper.title)}
        </a>
        <p class="text-xs mt-1" style="color:var(--rs-muted)">
          ${escHtml(authors)}${escHtml(extra)} &middot; ${escHtml(paper.venue || '')} ${paper.year || ''}
        </p>
      </div>
      <div class="flex gap-1 flex-shrink-0 flex-wrap">
        <span class="badge badge-score">${(+paper.paper_score || 0).toFixed(1)}</span>
        ${difficultyBadge(paper)}
        ${rankBadge(paper.conference_rank)}
        ${presentationBadge(paper.presentation_type)}
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
  // Hero tagline count + stats bar — seed from the snapshot, then override with
  // the live API total so the site always shows the real corpus size.
  const heroEl = document.getElementById('hero-paper-count');
  if (heroEl && stats.total_papers) {
    heroEl.textContent = stats.total_papers.toLocaleString();
  }
  if (window._rs_data?.fetchPaperCount) {
    window._rs_data.fetchPaperCount().then(total => {
      if (!Number.isFinite(total)) return;
      const live = total.toLocaleString();
      const papersEl = document.getElementById('stat-papers');
      if (papersEl) papersEl.textContent = live;
      if (heroEl) heroEl.textContent = live;
    });
  }
  const genEl = document.getElementById('stat-generated');
  if (genEl && stats.generated_at) {
    genEl.textContent = 'Updated ' + new Date(stats.generated_at).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' });
  }
}

// ── Paginator ──────────────────────────────────────────────────────────
function renderPaginator(containerId, current, total, onChange) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (total <= 1) { el.replaceChildren(); return; }
  const restoreFocus = el.contains(document.activeElement);
  let html = `<nav class="flex gap-1 flex-wrap justify-center mt-4" aria-label="Results pages">`;
  html += `<button class="pager-btn" aria-label="Previous page" onclick="(${onChange})(${current - 1})" ${current <= 1 ? 'disabled' : ''}>← Prev</button>`;
  const pages = Math.min(total, 7);
  let start = Math.max(1, current - 3);
  let end   = Math.min(total, start + pages - 1);
  start = Math.max(1, end - pages + 1);
  for (let p = start; p <= end; p++) {
    html += `<button class="pager-btn ${p === current ? 'active' : ''}" aria-label="Page ${p}"${p === current ? ' aria-current="page"' : ''} onclick="(${onChange})(${p})">${p}</button>`;
  }
  html += `<button class="pager-btn" aria-label="Next page" onclick="(${onChange})(${current + 1})" ${current >= total ? 'disabled' : ''}>Next →</button>`;
  html += `</nav>`;
  el.innerHTML = html;
  if (restoreFocus) el.querySelector('[aria-current="page"]')?.focus();
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
  // Authors and topics are small — always load from JSON.
  // Papers: use the Railway API if available (covers the full dataset), else
  // fall back to the static search index.
  const [authors, topics] = await Promise.all([
    fetch('data/authors.json').then(r => r.json()).catch(() => []),
    fetch('data/topics.json').then(r => r.json()).catch(() => []),
  ]);
  _searchData = { papers: [], authors, topics, _useApi: !!window._rs_data };
  return _searchData;
}

async function runSearch(query, data, limit = 5) {
  const q = query.toLowerCase().trim();
  if (!q) return { papers: [], authors: [], topics: [] };

  // Papers — prefer the Railway API (live, full dataset) over the static JSON index
  let papers = [];
  if (data._useApi) {
    papers = await window._rs_data.searchPapersQuick(q, limit);
  } else {
    papers = (data.papers || [])
      .filter(p => p.title?.toLowerCase().includes(q) ||
                   p.abstract?.toLowerCase().includes(q) ||
                   p.authors?.some(a => a.toLowerCase().includes(q)))
      .slice(0, limit);
  }

  const authors = (data.authors || [])
    .filter(a => a.name?.toLowerCase().includes(q))
    .slice(0, limit);

  const topics = (data.topics || [])
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
  let optionIndex = 0;

  if (papers.length) {
    html += `<div class="search-section-label">Papers</div>`;
    papers.forEach(p => {
      html += `<a id="rs-search-option-${optionIndex++}" class="search-result-item" role="option" href="papers.html?q=${encodeURIComponent(p.title)}">
        <div class="sr-title">${escHtml(p.title)}</div>
        <div class="sr-meta">${escHtml(p.venue || 'arXiv')} · ${p.year || ''}</div>
      </a>`;
    });
  }

  if (authors.length) {
    html += `<div class="search-section-label">Authors</div>`;
    authors.forEach(a => {
      html += `<a id="rs-search-option-${optionIndex++}" class="search-result-item" role="option" href="authors.html?q=${encodeURIComponent(a.name)}">
        <div class="sr-title">${escHtml(a.name)}</div>
        <div class="sr-meta">${a.paper_ids?.length || 0} papers</div>
      </a>`;
    });
  }

  if (topics.length) {
    html += `<div class="search-section-label">Topics</div>`;
    topics.forEach(t => {
      html += `<a id="rs-search-option-${optionIndex++}" class="search-result-item" role="option" href="topics.html#topic-${escHtml(t.id)}">
        <div class="sr-title">${escHtml(t.name)}</div>
        <div class="sr-meta">${t.paper_ids?.length || 0} papers</div>
      </a>`;
    });
  }

  html += `<a id="rs-search-option-${optionIndex}" class="search-see-all" role="option" href="search.html?q=${encodeURIComponent(query)}">See all results →</a>`;
  dropdown.innerHTML = html;
}

function initSearch() {
  const input    = document.getElementById('global-search');
  const dropdown = document.getElementById('search-dropdown');
  if (!input || !dropdown) return;

  let debounce;
  let requestId = 0;

  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-controls', dropdown.id);
  input.setAttribute('aria-expanded', 'false');
  dropdown.setAttribute('role', 'listbox');

  input.addEventListener('focus', () => loadSearchData());

  input.addEventListener('input', () => {
    clearTimeout(debounce);
    const currentRequest = ++requestId;
    const q = input.value.trim();
    if (!q) {
      dropdown.classList.add('hidden');
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
      return;
    }

    debounce = setTimeout(async () => {
      const data    = await loadSearchData();
      const results = await runSearch(q, data, 4);
      if (currentRequest !== requestId || input.value.trim() !== q) return;
      renderDropdown(results, q, dropdown);
      dropdown.classList.remove('hidden');
      input.setAttribute('aria-expanded', 'true');
    }, 180);
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' && !dropdown.classList.contains('hidden')) {
      e.preventDefault();
      dropdown.querySelector('[role="option"]')?.focus();
      return;
    }
    if (e.key === 'Enter' && input.value.trim()) {
      window.location.href = `search.html?q=${encodeURIComponent(input.value.trim())}`;
    }
    if (e.key === 'Escape') {
      dropdown.classList.add('hidden');
      input.setAttribute('aria-expanded', 'false');
      input.blur();
    }
  });

  dropdown.addEventListener('keydown', event => {
    const items = Array.from(dropdown.querySelectorAll('[role="option"]'));
    const current = items.indexOf(document.activeElement);
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      items[(current + direction + items.length) % items.length]?.focus();
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      items[event.key === 'Home' ? 0 : items.length - 1]?.focus();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      dropdown.classList.add('hidden');
      input.setAttribute('aria-expanded', 'false');
      input.focus();
    }
  });

  document.addEventListener('click', e => {
    if (!input.closest('.search-wrap').contains(e.target)) {
      dropdown.classList.add('hidden');
      input.setAttribute('aria-expanded', 'false');
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
// Featured paper must be *current* — picked from the freshest publication
// date available in the data, not the all-time top scorers (which skew weeks
// or months old). We anchor on the most recent published_date present, widen
// the window only if that single day is sparse, then rotate daily for variety.
const DAY_MS = 86400000;

function pickPaperOfTheDay(papers, poolSize = 60) {
  if (!papers || !papers.length) return null;

  const dated = papers.filter(p => p.published_date);
  let pool;
  if (dated.length) {
    const latest = dated.reduce(
      (max, p) => (p.published_date > max ? p.published_date : max),
      dated[0].published_date
    ).slice(0, 10);
    const latestMs = new Date(latest).getTime();
    // Prefer the latest day; widen to a few recent days only if too few papers.
    for (const windowDays of [0, 2, 6]) {
      pool = dated.filter(p => {
        const d = new Date(p.published_date.slice(0, 10)).getTime();
        return d <= latestMs && latestMs - d <= windowDays * DAY_MS;
      });
      if (pool.length >= 5) break;
    }
  } else {
    pool = papers.slice();
  }

  pool = pool
    .sort((a, b) => (b.paper_score || 0) - (a.paper_score || 0))
    .slice(0, Math.min(poolSize, pool.length));
  if (!pool.length) return null;

  const today = new Date();
  const startOfYear = new Date(today.getFullYear(), 0, 1);
  const dayOfYear = Math.floor((today - startOfYear) / DAY_MS);
  return pool[dayOfYear % pool.length];
}

function tweetPaperUrl(paper) {
  const venue   = [paper.venue, paper.year].filter(Boolean).join(' ');
  const score   = paper.paper_score ? ` | ${(+paper.paper_score).toFixed(1)}/10` : '';
  const snippet = (paper.abstract || paper.summary || '').slice(0, 160);
  const pageUrl = `https://kishormorol.github.io/ResearchScope/papers.html?q=${encodeURIComponent(paper.title || '')}`;
  const text    = `${paper.title}\n${venue}${score}\n\n${snippet}…\n\nResearchScope\n${pageUrl}\n\n#AIResearch #MachineLearning #ResearchScope`;
  return `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}`;
}

function renderPotdCard(paper) {
  if (!paper) return '';
  const url     = paperWorkspaceUrl(paper);
  const externalUrl = paper.paper_url || paper.url || '#';
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
      Paper of the Day
      <span style="font-size:0.65rem;font-weight:400">${new Date().toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric'})}</span>
    </div>
    <div class="potd-title">
      <a href="${escHtml(url)}">${escHtml(paper.title)}</a>
    </div>
    <div class="potd-meta">
      ${venue ? escHtml(venue) + (authors ? ' · ' : '') : ''}${escHtml(authors)}${escHtml(extra)}
      ${paper.paper_score ? ` · ${(+paper.paper_score).toFixed(1)}/10` : ''}
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:0.3rem;margin-bottom:0.75rem">${tags}</div>
    <p class="potd-abstract">${escHtml((paper.abstract || paper.summary || '').slice(0, 300))}</p>
    <div class="potd-actions">
      <a href="${escHtml(url)}" target="_blank" rel="noopener" class="potd-btn potd-btn-primary">Read Paper →</a>
      ${(() => { const aid = extractArxivId(url); return aid ? `<a href="https://kishormorol.github.io/CiteLens/?q=${encodeURIComponent(aid)}" target="_blank" rel="noopener" class="potd-btn potd-btn-ghost" title="See who cited this paper">Analyze citations</a>` : ''; })()}
      <a href="${escHtml(tweetPaperUrl(paper))}" target="_blank" rel="noopener" class="potd-btn potd-btn-ghost">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.738-8.835L1.254 2.25H8.08l4.259 5.631zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
        Share
      </a>
      <button onclick="copyPotdLink('${escHtml(url)}',this)" class="potd-btn potd-btn-ghost">Copy Link</button>
      <span class="potd-next">${nextLabel}</span>
    </div>
  </div>`;
}

function copyPotdLink(url, btn) {
  navigator.clipboard.writeText(url).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 2000);
  });
}

// ── Nav builder ────────────────────────────────────────────────────────
function buildDropdownNav() {
  const linksDiv = document.getElementById('rs-nav-links');
  const mobLinks  = document.getElementById('rs-mob-links');
  if (!linksDiv && !mobLinks) return;

  const page = window.location.pathname.split('/').pop() || './';

  function navLink(href, label, aliases = []) {
    const isActive = href === page || aliases.includes(page);
    const cls = 'rs-nav-top-link' + (isActive ? ' active' : '');
    return `<a href="${href}" class="${cls}">${label}</a>`;
  }

  function dropdown(label, items) {
    const hasActive = items.some(([href]) => href && href === page);
    const menuId = `rs-nav-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-menu`;
    const rows = items.map(([href, lbl, divider]) => {
      if (divider) return `<div class="rs-nav-dd-divider"></div>`;
      return `<a href="${href}" role="menuitem"${href === page ? ' class="active"' : ''}>${lbl}</a>`;
    }).join('');
    return `<div class="rs-nav-dd">
      <button class="rs-nav-dd-btn${hasActive ? ' active' : ''}" type="button" aria-haspopup="menu" aria-expanded="false" aria-controls="${menuId}">${label}<span class="rs-nav-dd-arrow" aria-hidden="true">▾</span></button>
      <div id="${menuId}" class="rs-nav-dd-menu" role="menu" aria-label="${label}">${rows}</div>
    </div>`;
  }

  if (linksDiv) {
    linksDiv.innerHTML =
      navLink('papers.html', 'Papers') +
      navLink('chat-arxiv', '✦ Chat arXiv', ['chat-paper']) +
      dropdown('Venues', [
        ['conferences.html', 'Conferences'],
        ['journals.html',    'Journals'],
        [null, null, true],
        ['conference-recommender.html', 'Conference Recommender'],
        ['journal-recommender.html',    'Journal Recommender'],
      ]) +
      dropdown('Discover', [
        ['topics.html', 'Topics'],
        ['gaps.html',   'Research Gaps'],
        ['digest.html', 'Digest'],
      ]) +
      dropdown('People', [
        ['authors.html', 'Authors'],
        ['labs.html',    'Labs & Unis'],
      ]) +
      navLink('deadlines.html', 'Deadlines');
  }

  if (mobLinks) {
    const ml = (href, lbl, aliases = []) =>
      `<a href="${href}" class="mobile-nav-link${href === page || aliases.includes(page) ? ' active' : ''}">${lbl}</a>`;
    const sec = t => `<p class="mobile-nav-section">${t}</p>`;
    mobLinks.innerHTML =
      ml('./',  'Home') +
      ml('papers.html', 'Papers') +
      ml('chat-arxiv', '✦ Chat with arXiv', ['chat-paper']) +
      sec('Venues') +
      ml('conferences.html',           'Conferences') +
      ml('journals.html',              'Journals') +
      ml('conference-recommender.html','Conference Recommender') +
      ml('journal-recommender.html',   'Journal Recommender') +
      sec('Discover') +
      ml('topics.html', 'Topics') +
      ml('gaps.html',   'Research Gaps') +
      ml('digest.html', 'Digest') +
      sec('People') +
      ml('authors.html',    'Authors') +
      ml('labs.html',       'Labs & Unis') +
      ml('deadlines.html',  'Deadlines') +
      ml('favourites.html', 'My Favourites') +
      sec('Account') +
      ml('search.html', 'Search') +
      '<div id="rs-mobile-auth" class="rs-mobile-auth"></div>';
  }
}

// ── Init ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initStarCount();
  buildDropdownNav();

  // Highlight active nav link (desktop + mobile) — runs after buildDropdownNav
  const path = window.location.pathname.split('/').pop() || './';
  document.querySelectorAll('.rs-nav a[href], .mobile-nav-link').forEach(a => {
    if (a.getAttribute('href') === path) a.classList.add('active');
  });

  // Global search
  initSearch();

  // Mobile menu toggle (with t-panel + t-icon-swap transitions)
  const mobileBtn  = document.getElementById('mobile-menu-btn');
  const mobileMenu = document.getElementById('mobile-menu');
  const iconOpen   = document.getElementById('hamburger-icon');
  const iconClose  = document.getElementById('close-icon');

  if (mobileBtn && mobileMenu) {
    // Add t-panel + t-icon-swap class hooks. Tailwind's `hidden` keeps the
    // breakpoint hide (>1024px) intact; on mobile widths the t-panel classes
    // drive the open/close animation.
    mobileMenu.classList.add('t-panel');
    if (iconOpen && iconClose) {
      mobileBtn.classList.add('t-icon-swap');
      iconClose.classList.remove('hidden');
      iconClose.classList.add('is-leaving');
    }

    let menuClosingTimer = null;
    const dur = () => parseInt(getComputedStyle(mobileMenu).getPropertyValue('--panel-close-dur')) || 200;

    const setIcon = (showingClose) => {
      if (!iconOpen || !iconClose) return;
      const out  = showingClose ? iconOpen  : iconClose;
      const into = showingClose ? iconClose : iconOpen;
      out.classList.add('is-leaving');
      into.classList.remove('is-leaving');
    };

    mobileBtn.setAttribute('aria-controls', mobileMenu.id);

    const closeMobileMenu = (returnFocus = false) => {
      if (menuClosingTimer) { clearTimeout(menuClosingTimer); menuClosingTimer = null; }
      mobileMenu.classList.remove('is-open');
      mobileMenu.classList.add('is-closing');
      mobileBtn.setAttribute('aria-expanded', 'false');
      mobileBtn.setAttribute('aria-label', 'Open menu');
      setIcon(false);
      menuClosingTimer = setTimeout(() => {
        mobileMenu.classList.add('hidden');
        mobileMenu.classList.remove('is-closing');
        menuClosingTimer = null;
        if (returnFocus) mobileBtn.focus();
      }, dur());
    };

    const openMobileMenu = () => {
      if (menuClosingTimer) { clearTimeout(menuClosingTimer); menuClosingTimer = null; }
      mobileMenu.classList.remove('hidden');
      void mobileMenu.offsetWidth;
      mobileMenu.classList.remove('is-closing');
      mobileMenu.classList.add('is-open');
      mobileBtn.setAttribute('aria-expanded', 'true');
      mobileBtn.setAttribute('aria-label', 'Close menu');
      setIcon(true);
    };

    mobileBtn.addEventListener('click', () => {
      if (mobileMenu.classList.contains('is-open')) closeMobileMenu();
      else openMobileMenu();
    });

    // Close menu when a link is tapped
    mobileMenu.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', () => {
        closeMobileMenu();
      });
    });

    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && mobileMenu.classList.contains('is-open')) closeMobileMenu(true);
    });
    document.addEventListener('click', event => {
      if (!mobileMenu.classList.contains('is-open')) return;
      if (!mobileMenu.contains(event.target) && !mobileBtn.contains(event.target)) closeMobileMenu();
    });
  }
});

// ── transitions-dev: Dropdown (Venues / Discover / People nav dropdowns) ──
function initNavDropdowns() {
  document.querySelectorAll('.rs-nav-dd').forEach(dd => {
    const menu = dd.querySelector('.rs-nav-dd-menu');
    const button = dd.querySelector('.rs-nav-dd-btn');
    if (!menu || !button) return;
    menu.classList.add('t-dropdown-menu');
    let closeTimer = null;

    const open = () => {
      if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
      document.querySelectorAll('.rs-nav-dd.is-open').forEach(other => {
        if (other !== dd && typeof other._rsClose === 'function') other._rsClose();
      });
      dd.classList.add('is-open');
      menu.classList.remove('is-closing');
      menu.classList.add('is-open');
      button.setAttribute('aria-expanded', 'true');
    };
    const close = (returnFocus = false) => {
      if (!menu.classList.contains('is-open')) return;
      dd.classList.remove('is-open');
      menu.classList.remove('is-open');
      menu.classList.add('is-closing');
      button.setAttribute('aria-expanded', 'false');
      const dur = parseInt(getComputedStyle(menu).getPropertyValue('--dropdown-close-dur')) || 120;
      closeTimer = setTimeout(() => {
        menu.classList.remove('is-closing');
        closeTimer = null;
        if (returnFocus) button.focus();
      }, dur);
    };
    dd._rsClose = close;
    /* Hover bridge: extend the open state to BOTH the parent and the menu
       itself. Moving the mouse from button → menu now keeps `is-open`
       active even when the cursor briefly crosses the visual gap. */
    const enterMenu = () => { if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; } open(); };
    const leaveAll  = (e) => {
      // Only close when leaving the parent AND the menu simultaneously
      const to = e.relatedTarget;
      if (to && (dd.contains(to) || menu.contains(to))) return;
      close();
    };

    dd.addEventListener('mouseenter', open);
    dd.addEventListener('mouseleave', leaveAll);
    menu.addEventListener('mouseenter', enterMenu);
    menu.addEventListener('mouseleave', leaveAll);
    dd.addEventListener('focusin', open);
    dd.addEventListener('focusout', e => {
      if (!dd.contains(e.relatedTarget) && !menu.contains(e.relatedTarget)) close();
    });
    menu.addEventListener('focusin', enterMenu);

    button.addEventListener('click', event => {
      event.preventDefault();
      if (dd.classList.contains('is-open')) close();
      else open();
    });
    button.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        open();
        menu.querySelector('a')?.focus();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        close(true);
      }
    });
    menu.addEventListener('keydown', event => {
      const items = Array.from(menu.querySelectorAll('a'));
      const current = items.indexOf(document.activeElement);
      if (event.key === 'Escape') {
        event.preventDefault();
        close(true);
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const direction = event.key === 'ArrowDown' ? 1 : -1;
        items[(current + direction + items.length) % items.length]?.focus();
      } else if (event.key === 'Home' || event.key === 'End') {
        event.preventDefault();
        items[event.key === 'Home' ? 0 : items.length - 1]?.focus();
      }
    });
  });

  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const open = document.querySelector('.rs-nav-dd.is-open');
    if (open && typeof open._rsClose === 'function') open._rsClose(true);
  });
  document.addEventListener('click', event => {
    document.querySelectorAll('.rs-nav-dd.is-open').forEach(dd => {
      if (!dd.contains(event.target) && typeof dd._rsClose === 'function') dd._rsClose();
    });
  });
}

// ── transitions-dev: Notification badge pulse on GitHub star count update ──
function pulseStarBadge() {
  document.querySelectorAll('.github-star-btn').forEach(btn => {
    if (btn.querySelector('.t-badge__pulse')) return;
    const dot = document.createElement('span');
    dot.className = 't-badge__pulse';
    dot.setAttribute('aria-hidden', 'true');
    btn.classList.add('t-badge');
    btn.appendChild(dot);
  });
}

// ── transitions-dev: Text states swap helper ───────────────────────────
// Usage: textSwap(el, 'new value')
function textSwap(el, nextText) {
  if (!el || el.textContent === nextText) return;
  el.classList.add('is-leaving');
  setTimeout(() => {
    el.textContent = nextText;
    el.classList.remove('is-leaving');
    el.classList.add('is-entering');
    void el.offsetWidth;
    el.classList.remove('is-entering');
  }, 180);
}

// ── Review comparison bridge ───────────────────────────────────────────
function initReviewCompareBridge() {
  const params = new URLSearchParams(location.search);
  if (!params.has('compare')) return;

  const parentOrigins = new Set(['http://127.0.0.1:8789', 'http://localhost:8789']);
  const ownOrigin = location.origin;
  let applyingRemoteScroll = false;
  let remoteScrollTimer = 0;
  let lastPostedRatio = -1;

  const normalizePath = url => {
    let path = url.pathname || '/';
    if (path === '/index.html') path = '/';
    return `${path}${url.search}${url.hash}`;
  };

  const scrollRatio = () => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    return max > 0 ? window.scrollY / max : 0;
  };

  const post = message => {
    if (window.parent === window) return;
    for (const origin of parentOrigins) {
      window.parent.postMessage({ ...message, rsOrigin: ownOrigin }, origin);
    }
  };

  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link || link.target === '_blank' || link.hasAttribute('download')) return;
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    const url = new URL(link.getAttribute('href'), location.href);
    if (url.origin !== location.origin) return;

    event.preventDefault();
    post({ type: 'researchscope:compare-route', path: normalizePath(url) });
  });

  window.addEventListener('scroll', () => {
    if (applyingRemoteScroll) return;
    const ratio = scrollRatio();
    if (Math.abs(ratio - lastPostedRatio) < 0.003) return;
    lastPostedRatio = ratio;
    post({ type: 'researchscope:compare-scroll', ratio });
  }, { passive: true });

  window.addEventListener('message', event => {
    if (!parentOrigins.has(event.origin)) return;
    if (event.data?.type !== 'researchscope:apply-scroll') return;

    const max = document.documentElement.scrollHeight - window.innerHeight;
    const ratio = Number(event.data.ratio || 0);
    window.clearTimeout(remoteScrollTimer);
    applyingRemoteScroll = true;
    lastPostedRatio = ratio;
    window.scrollTo({ top: Math.max(0, max) * ratio, behavior: 'auto' });
    remoteScrollTimer = window.setTimeout(() => { applyingRemoteScroll = false; }, 220);
  });

  window.addEventListener('load', () => {
    post({ type: 'researchscope:compare-ready', path: normalizePath(location), ratio: scrollRatio() });
  });
}

// ── Bootstrap transitions ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initNavDropdowns();
  pulseStarBadge();
  initReviewCompareBridge();
});

// ── Theme system bootstrap ──────────────────────────────────────────────
(function loadThemeSystem() {
  if (document.getElementById('rs-theme-switcher-script')) return;
  const script = document.createElement('script');
  script.id = 'rs-theme-switcher-script';
  script.src = 'assets/js/theme-switcher.js?v=ui-integrity-18';
  script.defer = true;
  document.head.appendChild(script);
})();
