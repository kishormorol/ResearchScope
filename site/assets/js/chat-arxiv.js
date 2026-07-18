(function () {
  'use strict';

  const core = window.ResearchScopeArxivCore;
  const form = document.getElementById('arxiv-open-form');
  const input = document.getElementById('arxiv-input');
  const error = document.getElementById('arxiv-input-error');
  const searchResults = document.getElementById('arxiv-search-results');
  const grid = document.getElementById('arxiv-paper-grid');
  let searchTimer = null;
  let searchRequest = 0;
  let activeResult = -1;
  let currentResults = [];

  function setResultsOpen(open) {
    searchResults.classList.toggle('hidden', !open);
    input.setAttribute('aria-expanded', String(open));
  }

  function updateActiveResult(index) {
    const links = [...searchResults.querySelectorAll('.arxiv-search-result')];
    if (!links.length) return;
    activeResult = (index + links.length) % links.length;
    links.forEach((link, itemIndex) => {
      const active = itemIndex === activeResult;
      link.classList.toggle('active', active);
      link.setAttribute('aria-selected', String(active));
    });
    links[activeResult].scrollIntoView({ block: 'nearest' });
  }

  function renderSearchResults(papers, query) {
    currentResults = papers;
    activeResult = -1;
    if (!papers.length) {
      searchResults.innerHTML = `<div class="arxiv-search-state">No arXiv papers found for “${escHtml(query)}”.</div>`;
      setResultsOpen(true);
      return;
    }
    searchResults.innerHTML = papers.map((paper, index) => {
      const destination = `chat-paper?id=${encodeURIComponent(paper.id)}`;
      const authors = (paper.authors || []).slice(0, 3).join(', ');
      const meta = [authors, paper.year].filter(Boolean).join(' · ');
      return `<a class="arxiv-search-result" href="${escHtml(destination)}" role="option" aria-selected="false" data-result-index="${index}">
        <div><h3>${escHtml(paper.title)}</h3><p>${escHtml(meta || 'arXiv paper')}</p></div>
        <span class="arxiv-search-action">Open chat →</span>
      </a>`;
    }).join('');
    setResultsOpen(true);
  }

  async function searchByKeyword(value) {
    const query = String(value || '').trim();
    if (query.length < 2 || core.normalizeArxivId(query)) {
      currentResults = [];
      setResultsOpen(false);
      return;
    }
    const requestId = ++searchRequest;
    searchResults.innerHTML = '<div class="arxiv-search-state">Searching arXiv papers…</div>';
    setResultsOpen(true);
    const papers = await window._rs_data.searchArxivPapers(query, 6);
    if (requestId !== searchRequest || input.value.trim() !== query) return;
    renderSearchResults(papers, query);
  }

  function openInput() {
    const destination = core.workspaceUrl(input.value);
    if (destination) {
      error.textContent = '';
      location.href = destination;
      return;
    }
    if (activeResult >= 0 && currentResults[activeResult]) {
      location.href = `chat-paper?id=${encodeURIComponent(currentResults[activeResult].id)}`;
      return;
    }
    if (input.value.trim().length < 2) {
      error.textContent = 'Enter at least two characters, or paste an arXiv URL or ID.';
      input.focus();
      return;
    }
    error.textContent = '';
    searchByKeyword(input.value);
  }

  function renderPapers(papers) {
    if (!papers.length) {
      grid.innerHTML = '<div class="arxiv-loading">No arXiv papers are available right now.</div>';
      return;
    }
    grid.innerHTML = papers.map((paper) => {
      const chatUrl = `chat-paper?id=${encodeURIComponent(paper.id)}`;
      const externalUrl = paper.paper_url || paper.pdf_url || '#';
      const authors = (paper.authors || []).slice(0, 3).join(', ');
      const extra = (paper.authors || []).length > 3 ? ` +${paper.authors.length - 3}` : '';
      return `<article class="arxiv-paper-card">
        <div class="arxiv-card-kicker"><span>arXiv</span><span>${escHtml(String(paper.year || ''))}</span></div>
        <h3><a href="${escHtml(externalUrl)}" target="_blank" rel="noopener">${escHtml(paper.title)}</a></h3>
        <p class="arxiv-card-authors">${escHtml(authors)}${escHtml(extra)}</p>
        <p class="arxiv-card-summary">${escHtml(paper.summary || paper.abstract || 'No abstract available.')}</p>
        <div class="arxiv-card-footer">
          <span class="arxiv-score">⭐ ${(Number(paper.paper_score) || 0).toFixed(1)}</span>
          <a class="arxiv-chat-button" href="${escHtml(chatUrl)}">✦ Chat with paper</a>
        </div>
      </article>`;
    }).join('');
  }

  async function loadPapers() {
    try {
      const result = await window._rs_data.queryPapers({
        page: 1, pageSize: 12, source: 'arxiv', sortBy: 'paper_score',
      });
      renderPapers(result.data || []);
    } catch (_) {
      grid.innerHTML = '<div class="arxiv-loading">Could not load arXiv papers.</div>';
    }
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    openInput();
  });
  input.addEventListener('input', () => {
    error.textContent = '';
    clearTimeout(searchTimer);
    searchRequest += 1;
    const query = input.value.trim();
    if (query.length < 2 || core.normalizeArxivId(query)) {
      currentResults = [];
      setResultsOpen(false);
      return;
    }
    searchTimer = setTimeout(() => searchByKeyword(query), 280);
  });
  input.addEventListener('keydown', (event) => {
    if (searchResults.classList.contains('hidden')) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      updateActiveResult(activeResult + 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      updateActiveResult(activeResult - 1);
    } else if (event.key === 'Escape') {
      setResultsOpen(false);
    }
  });
  input.addEventListener('focus', () => {
    if (searchResults.textContent.trim()) setResultsOpen(true);
  });
  document.addEventListener('click', (event) => {
    if (!form.contains(event.target) && !searchResults.contains(event.target)) {
      setResultsOpen(false);
    }
  });
  document.querySelector('[data-example]').addEventListener('click', (event) => {
    input.value = event.currentTarget.dataset.example;
    openInput();
  });
  loadPapers();
})();
