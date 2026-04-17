(function () {
  function uniqueTags(tags) {
    return Array.from(new Set((tags || []).filter(Boolean)));
  }

  function renderLibraryCard(paper, index, libraryApi) {
    const url = paper.paper_url || paper.url || '#';
    const authors = (paper.authors || []).slice(0, 3).join(', ');
    const extra = (paper.authors || []).length > 3
      ? ` +${paper.authors.length - 3}`
      : '';
    const tags = uniqueTags(paper.tags).slice(0, 4);
    const links = [
      paper.paper_url
        ? `<a href="${escHtml(paper.paper_url)}" target="_blank" rel="noopener" class="text-sm font-medium hover:underline" style="color:var(--rs-primary)">Paper</a>`
        : '',
      paper.pdf_url
        ? `<a href="${escHtml(paper.pdf_url)}" target="_blank" rel="noopener" class="text-sm font-medium hover:underline" style="color:var(--rs-primary)">PDF</a>`
        : '',
    ].filter(Boolean).join('');

    return `
      <article class="rs-card p-5 mb-4 library-card">
        <div class="library-card__header">
          <div class="min-w-0 flex-1">
            <div class="library-card__eyebrow">Saved #${index + 1}</div>
            <a href="${escHtml(url)}" target="_blank" rel="noopener" class="text-base font-semibold hover:text-indigo-600 transition-colors">
              ${escHtml(paper.title)}
            </a>
            <p class="text-xs mt-1" style="color:var(--rs-muted)">
              ${escHtml(authors)}${escHtml(extra)}${authors ? ' · ' : ''}${escHtml(paper.venue || '')} ${paper.year || ''}
            </p>
          </div>
          <div class="library-card__actions">
            ${libraryApi.renderLibraryButton(paper, { inLibrary: true })}
          </div>
        </div>
        <p class="text-sm mt-3 leading-relaxed" style="color:var(--rs-muted)">
          ${escHtml(truncate(paper.summary || paper.abstract, 240))}
        </p>
        <div class="mt-3 flex flex-wrap gap-1">
          ${scoreBadge(paper.paper_score)}
          ${difficultyBadge(paper)}
          ${rankBadge(paper.conference_rank)}
          ${sourceBadge(paper)}
          ${tagChips(tags)}
        </div>
        ${links ? `<div class="mt-4 flex flex-wrap gap-3">${links}</div>` : ''}
      </article>`;
  }

  async function initLibraryPage() {
    const libraryApi = window.ResearchScopeLibrary;
    const listEl = document.getElementById('library-list');
    const emptyEl = document.getElementById('library-empty');
    const countEl = document.getElementById('library-count');
    const emptyTitleEl = document.getElementById('library-empty-title');
    const emptyCopyEl = document.getElementById('library-empty-copy');

    if (!libraryApi || !listEl || !emptyEl || !countEl) return;

    const libraryButtons = libraryApi.initializeLibraryButtons({
      root: document,
      onChange: renderLibrary,
    });

    const papers = await fetchData('data/papers.json');
    if (!papers || !papers.length) {
      countEl.textContent = 'No papers are available right now.';
      listEl.innerHTML = '';
      emptyEl.classList.remove('hidden');
      if (emptyTitleEl) emptyTitleEl.textContent = 'No papers available';
      if (emptyCopyEl) emptyCopyEl.textContent = 'No papers are available in the current dataset.';
      return;
    }

    function renderLibrary() {
      const libraryIds = libraryApi.readLibraryIds();
      const libraryPapers = libraryApi.getLibraryPapers(papers, libraryIds);

      countEl.textContent = `${libraryPapers.length} saved paper${libraryPapers.length === 1 ? '' : 's'} · oldest saved first`;

      if (!libraryPapers.length) {
        listEl.innerHTML = '';
        emptyEl.classList.remove('hidden');
        return;
      }

      emptyEl.classList.add('hidden');
      listEl.innerHTML = libraryPapers
        .map((paper, index) => renderLibraryCard(paper, index, libraryApi))
        .join('');

      libraryButtons.refresh();
    }

    renderLibrary();

    window.addEventListener('storage', function (event) {
      if (event.key === libraryApi.STORAGE_KEY) {
        renderLibrary();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLibraryPage);
  } else {
    initLibraryPage();
  }
})();
