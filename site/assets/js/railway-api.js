/**
 * ResearchScope — Railway API client
 *
 * Provides window._rs_data, the data client used by every page, plus auth
 * and favourites. Backed by the Railway FastAPI service.
 *
 * Fallback chain: Railway API → static JSON (site/data/*.json)
 * Sign-in is NEVER required for browsing — only for favourites.
 * Auth UI lives on dedicated signin / register pages.
 */

const RS_API = window.__RS_API_BASE__ ||
  ((location.hostname === '127.0.0.1' || location.hostname === 'localhost')
    ? 'http://127.0.0.1:8000'
    : 'https://researchscope-production.up.railway.app');

// Local browse pages read the public production /papers listing through the
// static dev server's same-origin proxy. All auth, chat, document preparation,
// favourites, and paper-specific endpoints continue to use RS_API above.
const RS_PAPERS_LIST_API = window.__RS_PAPERS_LIST_API_BASE__ ||
  ((location.hostname === '127.0.0.1' || location.hostname === 'localhost')
    ? `${location.origin}/api/production`
    : RS_API);

// Public site shows at most this many papers per section (arXiv / conference /
// journal) — 3 000 total. The full corpus stays available via the API and the
// Hugging Face dataset; this just bounds what the browse pages paginate through.
const SECTION_CAP = 1000;

// ── Auth state ────────────────────────────────────────────────────────────────

const _auth = {
  TOKEN_KEY: 'rs_jwt',
  USER_KEY:  'rs_user',

  token() { return localStorage.getItem(this.TOKEN_KEY); },
  user()  {
    try { return JSON.parse(localStorage.getItem(this.USER_KEY) || 'null'); }
    catch { return null; }
  },
  isLoggedIn() { return !!this.token(); },
  save(token, user) {
    localStorage.setItem(this.TOKEN_KEY, token);
    localStorage.setItem(this.USER_KEY, JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
  },
};

// ── Core fetch helper ─────────────────────────────────────────────────────────

async function _apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  const token = _auth.token();
  if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${RS_API}${path}`, { ...opts, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const expired = _expireStoredSession(res.status, headers.Authorization, token);
    const message = expired
      ? 'Your session has expired. Please sign in again.'
      : (err.detail || 'API error');
    throw Object.assign(new Error(message), { status: res.status, authExpired: expired });
  }
  return res.status === 204 ? null : res.json();
}

async function _papersListFetch(params) {
  const res = await fetch(`${RS_PAPERS_LIST_API}/papers?${params}`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw Object.assign(new Error(err.detail || 'Papers API error'), { status: res.status });
  }
  return res.json();
}

async function _apiFetchRaw(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  const token = _auth.token();
  if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${RS_API}${path}`, { ...opts, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const expired = _expireStoredSession(res.status, headers.Authorization, token);
    const message = expired
      ? 'Your session has expired. Please sign in again.'
      : (err.detail || 'API error');
    throw Object.assign(new Error(message), { status: res.status, authExpired: expired });
  }
  return res;
}

function _expireStoredSession(status, authorization, storedToken) {
  if (
    status !== 401 ||
    !storedToken ||
    authorization !== `Bearer ${storedToken}` ||
    _auth.token() !== storedToken
  ) return false;

  _auth.clear();
  _updateAuthNav();
  window.dispatchEvent?.(new CustomEvent('rs:auth-expired'));
  return true;
}

// ── Papers ────────────────────────────────────────────────────────────────────

async function _queryPapers({
  page = 1, pageSize = 25,
  search = '', tag = '', difficulty = '', type = '',
  source = '', year = '', sortBy = 'paper_score',
  rank = '', venue = '',
  tagNormalizeMap = {},
} = {}) {
  const params = new URLSearchParams({ page, page_size: pageSize });
  if (search) params.set('search', search);
  if (tag)    params.set('tag', tag);
  if (year)   params.set('year', year);
  if (rank)   params.set('rank', rank);
  if (venue)  params.set('venue', venue);
  if (source === 'arxiv')           params.set('source_type', 'preprint');
  else if (source === 'conference') params.set('source_type', 'conference');
  else if (source === 'journal')    params.set('source_type', 'journal');

  const start = (page - 1) * pageSize;

  // 1. Try Railway — clamp the reported count and trim rows past the cap so the
  // browse page paginates through at most SECTION_CAP papers for this section.
  try {
    const json = await _papersListFetch(params);
    if (json && Array.isArray(json.results)) {
      const count = Math.min(json.total ?? 0, SECTION_CAP);
      let data = json.results;
      if (start >= SECTION_CAP) data = [];
      else if (start + data.length > SECTION_CAP) data = data.slice(0, SECTION_CAP - start);
      return { data, count, error: null };
    }
  } catch (e) {
    console.warn('[railway] queryPapers failed, falling back to static JSON:', e.message);
  }

  // 2. Last resort — static JSON (already capped at 1 000 by the generator)
  try {
    const res = await fetch('data/papers.json');
    const all = await res.json();
    const filtered = search
      ? all.filter(p => (p.title||'').toLowerCase().includes(search.toLowerCase()) ||
                        (p.abstract||'').toLowerCase().includes(search.toLowerCase()))
      : all;
    const count = Math.min(filtered.length, SECTION_CAP);
    return { data: filtered.slice(start, Math.min(start + pageSize, SECTION_CAP)), count, error: null };
  } catch (e) {
    console.warn('[static] papers.json failed:', e.message);
  }

  return { data: [], count: 0, error: null };
}

async function _fetchTopPapers(limit = 500) {
  // arXiv preprints only — matches the data/papers.json static fallback below
  // (which is the arXiv section). Without source_type=preprint the global
  // /papers endpoint is ranked across all sources and is now dominated by
  // conference/journal papers, which starved arXiv-only consumers like the
  // weekly digest of any results.
  try {
    const PAGE = 100; // backend max page_size
    const results = [];
    for (let page = 1; results.length < limit; page++) {
      const need = Math.min(PAGE, limit - results.length);
      const params = new URLSearchParams({
        source_type: 'preprint', page_size: need, page,
      });
      const json = await _papersListFetch(params);
      if (!json?.results?.length) break;
      results.push(...json.results);
      if (json.results.length < need) break; // last page
    }
    if (results.length) return results;
  } catch { /* fall through */ }
  try {
    const res = await fetch('data/papers.json');
    const all = await res.json();
    return all.slice(0, limit);
  } catch { /* ignore */ }
  return [];
}

async function _fetchConferencePapers(limit = 1000) {
  try {
    const PAGE = 100;
    const results = [];
    for (let page = 1; results.length < limit; page++) {
      const need = Math.min(PAGE, limit - results.length);
      const json = await _apiFetch(`/papers/conferences?page_size=${need}&page=${page}&rank=A*`);
      if (!json?.results?.length) break;
      results.push(...json.results);
      if (json.results.length < need) break;
    }
    if (results.length) return results;
  } catch { /* fall through */ }
  try {
    const res = await fetch('data/conferences.json');
    const all = await res.json();
    return Array.isArray(all) ? all.slice(0, limit) : [];
  } catch { /* ignore */ }
  return [];
}

async function _fetchJournalPapers(limit = 2000) {
  try {
    const json = await _apiFetch(`/papers/journals?page_size=${Math.min(limit, 100)}&page=1`);
    if (json?.results?.length) return json.results;
  } catch { /* fall through */ }
  try {
    const res = await fetch('data/journals.json');
    const all = await res.json();
    return Array.isArray(all) ? all.slice(0, limit) : [];
  } catch { /* ignore */ }
  return [];
}

async function _fetchPaperCount() {
  // Live total across every source (preprint + conference + journal). This is the
  // real corpus size on Railway — unaffected by the browse-page SECTION_CAP and
  // never stale, unlike the data/stats.json snapshot used as the fallback.
  try {
    const json = await _papersListFetch(new URLSearchParams({ page: 1, page_size: 1 }));
    if (json && Number.isFinite(json.total)) return json.total;
  } catch { /* fall through */ }
  try {
    const res = await fetch('data/stats.json');
    const stats = await res.json();
    if (stats && Number.isFinite(stats.total_papers)) return stats.total_papers;
  } catch { /* ignore */ }
  return null;
}

async function _searchPapersQuick(query, limit = 5) {
  if (!query || query.trim().length < 2) return [];
  try {
    const json = await _apiFetch(`/search?${new URLSearchParams({ q: query.trim(), limit })}`);
    if (json?.results?.length) return json.results;
  } catch { /* fall through */ }
  return [];
}

async function _searchArxivPapers(query, limit = 6) {
  const value = String(query || '').trim();
  if (value.length < 2) return [];
  try {
    const params = new URLSearchParams({
      q: value, source_type: 'preprint', limit: Math.min(Number(limit) || 6, 20),
    });
    const res = await fetch(`${RS_PAPERS_LIST_API}/search?${params}`, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) return [];
    const json = await res.json();
    return (json.results || []).filter((paper) =>
      String(paper.id || '').startsWith('arxiv:') ||
      String(paper.source || '').toLowerCase() === 'arxiv'
    );
  } catch (_) {
    return [];
  }
}

// ── Auth API ──────────────────────────────────────────────────────────────────

const _authApi = {
  async register(email, password, name = '') {
    const data = await _apiFetch('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    });
    // Save token immediately so the account is recoverable even if /auth/me fails.
    _auth.save(data.access_token, {});
    const user = await _apiFetch('/auth/me', {
      headers: { Authorization: `Bearer ${data.access_token}` },
    });
    _auth.save(data.access_token, user);
    return user;
  },

  async login(email, password) {
    const data = await _apiFetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    // Fetch profile before persisting so a /auth/me failure leaves no partial state.
    const user = await _apiFetch('/auth/me', {
      headers: { Authorization: `Bearer ${data.access_token}` },
    });
    _auth.save(data.access_token, user);
    return user;
  },

  logout() {
    _auth.clear();
    _updateAuthNav();
  },

  async updateProfile(data) {
    const user = await _apiFetch('/auth/me', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    _auth.save(_auth.token(), user);
    _updateAuthNav();
    return user;
  },

  isLoggedIn: () => _auth.isLoggedIn(),
  currentUser: () => _auth.user(),
  me: () => _apiFetch('/auth/me'),
};

// ── Favourites API ────────────────────────────────────────────────────────────

const _favsApi = {
  async list() {
    return _apiFetch('/favourites');
  },
  async add(paperId) {
    return _apiFetch(`/favourites/${encodeURIComponent(paperId)}`, { method: 'POST' });
  },
  async remove(paperId) {
    return _apiFetch(`/favourites/${encodeURIComponent(paperId)}`, { method: 'DELETE' });
  },
  async updateNotes(paperId, notes) {
    return _apiFetch(`/favourites/${encodeURIComponent(paperId)}/notes`, {
      method: 'PATCH',
      body: JSON.stringify({ notes }),
    });
  },
};

// ── Nav auth button + dropdown ────────────────────────────────────────────────

function _injectAuthButton() {
  const anchor = document.getElementById('rs-nav-actions');
  if (!anchor) return;

  const wrap = document.createElement('div');
  wrap.id = 'rs-auth-wrap';
  wrap.className = 'hidden lg:block';
  anchor.insertBefore(wrap, anchor.firstChild);

  const btn = document.createElement('button');
  btn.id = 'rs-auth-btn';
  wrap.appendChild(btn);

  _updateAuthNav();
}

function _updateAuthNav() {
  const btn = document.getElementById('rs-auth-btn');
  const user = _auth.user();
  const loggedIn = Boolean(_auth.isLoggedIn() && user);
  if (btn && loggedIn) {
    const initial = (user.name || user.email || '?')[0].toUpperCase();
    btn.innerHTML = `<span style="width:22px;height:22px;border-radius:50%;background:var(--rs-primary,#a63b2d);color:var(--rs-paper,#eee4c9);display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:700;flex:0 0 auto">${escHtml(initial)}</span><span class="rs-auth-label">${escHtml(user.name || user.email)}</span>`;
    btn.setAttribute('aria-haspopup', 'menu');
    btn.setAttribute('aria-expanded', 'false');
    btn.onclick = (e) => { e.stopPropagation(); _showUserMenu(); };
  } else if (btn) {
    btn.innerHTML = `<svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg><span class="rs-auth-label">Sign in</span>`;
    btn.removeAttribute('aria-haspopup');
    btn.removeAttribute('aria-expanded');
    btn.onclick = (e) => { e.stopPropagation(); rsOpenModal(); };
  }

  const mobile = document.getElementById('rs-mobile-auth');
  if (mobile) {
    mobile.innerHTML = loggedIn
      ? `<a href="profile.html" class="mobile-nav-link">Profile &amp; Settings</a><button type="button" class="mobile-nav-link" onclick="rsLogout()">Sign out</button>`
      : '<a href="signin.html" class="mobile-nav-link">Sign in</a><a href="register.html" class="mobile-nav-link">Create account</a>';
  }
}

function _showUserMenu() {
  const existing = document.getElementById('rs-user-menu');
  const btn = document.getElementById('rs-auth-btn');
  if (existing) {
    existing.remove();
    btn?.setAttribute('aria-expanded', 'false');
    return;
  }
  const user = _auth.user();
  const wrap = document.getElementById('rs-auth-wrap');
  if (!wrap) return;

  const menu = document.createElement('div');
  menu.id = 'rs-user-menu';
  menu.setAttribute('role', 'menu');
  menu.innerHTML = `
    <div style="padding:.65rem 1rem;border-bottom:1px solid var(--rs-border,#aa9970)">
      <div style="font-size:.82rem;font-weight:700;color:var(--rs-text,#14120d)">${escHtml(user?.name || user?.email || '')}</div>
      ${user?.name ? `<div style="font-size:.72rem;color:var(--rs-muted,#3f382d)">${escHtml(user.email || '')}</div>` : ''}
    </div>
    <a href="profile.html">Profile &amp; Settings</a>
    <a href="favourites.html">My Favourites</a>
    <a href="chat-paper">My Paper Chats</a>
    <div style="height:1px;background:var(--rs-border,#aa9970);margin:.25rem 0"></div>
    <button onclick="rsLogout()" style="color:var(--rs-danger,#7f2d23)">Sign out</button>`;
  wrap.appendChild(menu);
  btn?.setAttribute('aria-expanded', 'true');

  setTimeout(() => document.addEventListener('click', function close(e) {
    if (!wrap.contains(e.target)) {
      menu.remove();
      btn?.setAttribute('aria-expanded', 'false');
      document.removeEventListener('click', close);
    }
  }), 0);
}

// ── Auth navigation helpers ───────────────────────────────────────────────────

window.rsOpenModal = function(returnTo) {
  const page = returnTo || window.location.pathname.split('/').pop() || './';
  window.location.href = `signin.html?returnTo=${encodeURIComponent(page)}`;
};

window.rsLogout = function() {
  _authApi.logout();
  if (window.location.pathname.endsWith('favourites.html')) {
    window.location.href = './';
  }
};

// ── Static JSON fetch helper ──────────────────────────────────────────────────

async function _staticFetch(staticPath, limit) {
  try {
    const res = await fetch(staticPath);
    const data = await res.json();
    return Array.isArray(data) ? (limit ? data.slice(0, limit) : data) : [];
  } catch { return []; }
}

// ── window._rs_data — the data client used by every page ──────────────────────

window._rs_data = {
  queryPapers:           _queryPapers,
  fetchTopPapers:        _fetchTopPapers,
  fetchConferencePapers: _fetchConferencePapers,
  fetchJournalPapers:    _fetchJournalPapers,
  fetchPaperCount:       _fetchPaperCount,
  searchPapersQuick:     _searchPapersQuick,
  searchArxivPapers:     _searchArxivPapers,
  fetchAllAuthors:  (n) => _staticFetch('data/authors.json', n),
  fetchAllTopics:   (n) => _staticFetch('data/topics.json',  n),
  fetchAllGaps:     (n) => _staticFetch('data/gaps.json',    n),
  fetchAllLabs:     (n) => _staticFetch('data/labs.json',    n),
};

// ── Public API surface ────────────────────────────────────────────────────────

window._rs_api = {
  baseUrl: RS_API,
  auth:       _authApi,
  favourites: _favsApi,
  papers: {
    list:        (p) => _apiFetch(`/papers?${new URLSearchParams(p)}`),
    get:         (id) => _apiFetch(`/papers/${encodeURIComponent(id)}`),
    viewer:      (id) => _apiFetch(`/papers/${encodeURIComponent(id)}/viewer-url`),
    conferences: (p)  => _apiFetch(`/papers/conferences?${new URLSearchParams(p)}`),
    journals:    (p)  => _apiFetch(`/papers/journals?${new URLSearchParams(p)}`),
  },
  search: (q, opts = {}) => _apiFetch(`/search?${new URLSearchParams({ q, ...opts })}`),
  documents: {
    status:  (paperId) => _apiFetch(`/papers/${encodeURIComponent(paperId)}/document-status`),
    prepare: (paperId) => _apiFetch(`/papers/${encodeURIComponent(paperId)}/prepare`, { method: 'POST' }),
  },
  chat: {
    createSession: (paperId) => _apiFetch('/chat/sessions', {
      method: 'POST', body: JSON.stringify({ paper_id: paperId }),
    }),
    listSessions: (opts = {}) => _apiFetch(`/chat/sessions?${new URLSearchParams(opts)}`, { cache: 'no-store' }),
    getSession: (id) => _apiFetch(`/chat/sessions/${encodeURIComponent(id)}`, { cache: 'no-store' }),
    updateSession: (id, data) => _apiFetch(`/chat/sessions/${encodeURIComponent(id)}`, {
      method: 'PATCH', body: JSON.stringify(data),
    }),
    deleteSession: (id) => _apiFetch(`/chat/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    deleteAllSessions: () => _apiFetch('/chat/sessions', { method: 'DELETE' }),
    listMessages: (id) => _apiFetch(`/chat/sessions/${encodeURIComponent(id)}/messages`),
    sendMessage: (id, content, requestId, signal) => _apiFetchRaw(
      `/chat/sessions/${encodeURIComponent(id)}/messages`,
      {
        method: 'POST', signal,
        headers: { 'Idempotency-Key': requestId },
        body: JSON.stringify({ content }),
      },
    ),
  },
};

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  _injectAuthButton();
});
