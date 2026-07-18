(function () {
  'use strict';

  const core = window.ResearchScopeChatCore;
  const pdfjs = window.pdfjsLib;
  const elements = {};
  const state = {
    document: null,
    url: '',
    page: 1,
    zoom: 1,
    fitWidth: true,
    generation: 0,
    observer: null,
    resizeTimer: null,
    scrollFrame: null,
  };

  function reportProgress(phase, percent, label) {
    window.dispatchEvent(new CustomEvent('researchscope:pdf-progress', {
      detail: { phase, percent, label },
    }));
  }

  function bindElements() {
    elements.scroll = document.getElementById('pdf-scroll');
    elements.pages = document.getElementById('pdf-pages');
    elements.frame = document.getElementById('paper-frame');
    elements.placeholder = document.getElementById('paper-placeholder');
    elements.pageNumber = document.getElementById('pdf-page-number');
    elements.pageCount = document.getElementById('pdf-page-count');
    elements.zoomValue = document.getElementById('pdf-zoom-value');
    elements.title = document.getElementById('pdf-toolbar-title');
  }

  function setControlsEnabled(enabled) {
    ['pdf-prev', 'pdf-next', 'pdf-zoom-out', 'pdf-zoom-in', 'pdf-fit-width'].forEach((id) => {
      const button = document.getElementById(id);
      if (button) button.disabled = !enabled;
    });
    if (elements.pageNumber) elements.pageNumber.disabled = !enabled;
  }

  function updateControls() {
    const total = state.document?.numPages || 0;
    if (elements.pageNumber) {
      elements.pageNumber.value = String(state.page);
      elements.pageNumber.max = String(Math.max(1, total));
    }
    if (elements.pageCount) elements.pageCount.textContent = total || '—';
    if (elements.zoomValue) elements.zoomValue.textContent = `${Math.round(state.zoom * 100)}%`;
    const previous = document.getElementById('pdf-prev');
    const next = document.getElementById('pdf-next');
    if (previous) previous.disabled = !total || state.page <= 1;
    if (next) next.disabled = !total || state.page >= total;
  }

  function availableWidth() {
    return Math.max(280, Math.min(940, (elements.scroll?.clientWidth || 900) - 48));
  }

  async function pageDimensions(pageNumber) {
    const page = await state.document.getPage(pageNumber);
    const viewport = page.getViewport({ scale: 1 });
    const baseScale = state.fitWidth ? availableWidth() / viewport.width : 1.15;
    const scale = baseScale * state.zoom;
    return { page, viewport: page.getViewport({ scale }) };
  }

  async function renderPage(container) {
    if (!state.document || ['true', 'loading'].includes(container.dataset.rendered)) return;
    const generation = Number(container.dataset.generation);
    const pageNumber = Number(container.dataset.page);
    container.dataset.rendered = 'loading';
    try {
      const { page, viewport } = await pageDimensions(pageNumber);
      if (generation !== state.generation) return;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const canvas = document.createElement('canvas');
      canvas.className = 'pdf-page-canvas';
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;
      container.style.width = `${Math.floor(viewport.width)}px`;
      container.style.minHeight = `${Math.floor(viewport.height)}px`;
      await page.render({
        canvasContext: canvas.getContext('2d', { alpha: false }),
        viewport,
        transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0],
      }).promise;
      if (generation !== state.generation) return;
      container.replaceChildren(canvas);
      container.dataset.rendered = 'true';
    } catch (_) {
      container.dataset.rendered = 'false';
    }
  }

  function observePages() {
    state.observer?.disconnect();
    state.observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) renderPage(entry.target);
      });
    }, { root: elements.scroll, rootMargin: '800px 0px', threshold: [0.1, 0.5, 0.8] });
    elements.pages.querySelectorAll('.pdf-page').forEach((page) => state.observer.observe(page));
  }

  function syncPageFromScroll() {
    if (!state.document) return;
    const target = elements.scroll.scrollTop + 20;
    let nearestPage = 1;
    let nearestDistance = Number.POSITIVE_INFINITY;
    elements.pages.querySelectorAll('.pdf-page').forEach((page) => {
      const distance = Math.abs(page.offsetTop - target);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestPage = Number(page.dataset.page);
      }
    });
    const nextPage = core.clampViewerPage(nearestPage, state.document.numPages);
    if (nextPage !== state.page) {
      state.page = nextPage;
      updateControls();
    }
  }

  async function buildPageShells(targetPage) {
    const generation = ++state.generation;
    state.observer?.disconnect();
    elements.pages.replaceChildren();
    const firstPage = await state.document.getPage(1);
    const firstViewport = firstPage.getViewport({ scale: 1 });
    const baseScale = state.fitWidth ? availableWidth() / firstViewport.width : 1.15;
    const width = Math.floor(firstViewport.width * baseScale * state.zoom);
    const height = Math.floor(firstViewport.height * baseScale * state.zoom);
    const fragment = document.createDocumentFragment();
    for (let pageNumber = 1; pageNumber <= state.document.numPages; pageNumber += 1) {
      const page = document.createElement('section');
      page.className = 'pdf-page';
      page.dataset.page = String(pageNumber);
      page.dataset.generation = String(generation);
      page.style.width = `${width}px`;
      page.style.minHeight = `${height}px`;
      page.setAttribute('aria-label', `Page ${pageNumber}`);
      fragment.appendChild(page);
    }
    elements.pages.appendChild(fragment);
    observePages();
    requestAnimationFrame(() => goToPage(targetPage || state.page, 'auto'));
  }

  function goToPage(value, behavior) {
    if (!state.document) return;
    state.page = core.clampViewerPage(value, state.document.numPages);
    const page = elements.pages.querySelector(`[data-page="${state.page}"]`);
    if (page) {
      renderPage(page);
      elements.scroll.scrollTo({
        top: Math.max(0, page.offsetTop - 12),
        behavior: behavior || 'smooth',
      });
    }
    updateControls();
  }

  async function setZoom(value, preservePage) {
    if (!state.document) return;
    state.zoom = core.clampViewerZoom(value);
    state.fitWidth = true;
    updateControls();
    await buildPageShells(preservePage || state.page);
  }

  function showFallback(url, page) {
    elements.scroll.style.display = 'none';
    elements.frame.src = `${url}#page=${page || 1}`;
    elements.frame.style.display = 'block';
    elements.placeholder.style.display = 'none';
    setControlsEnabled(false);
    reportProgress('ready', 100, 'PDF opened in the browser viewer');
  }

  async function open(url, page) {
    if (!url) return false;
    if (state.document && state.url === url) {
      goToPage(page || state.page);
      return true;
    }
    if (!pdfjs) {
      showFallback(url, page);
      return true;
    }
    try {
      reportProgress('downloading', 2, 'Downloading PDF');
      state.generation += 1;
      state.observer?.disconnect();
      state.document?.destroy();
      state.document = null;
      state.url = url;
      state.page = Math.max(1, Number(page) || 1);
      state.zoom = 1;
      state.fitWidth = true;
      elements.frame.style.display = 'none';
      elements.frame.removeAttribute('src');
      elements.scroll.style.display = 'block';
      elements.placeholder.style.display = 'grid';
      elements.placeholder.innerHTML = '<div><div class="pdf-loading-mark" aria-hidden="true">▤</div><h2 class="font-bold mb-2">Opening paper</h2><p>Preparing the reading view…</p></div>';
      const task = pdfjs.getDocument({ url, withCredentials: false });
      task.onProgress = ({ loaded, total }) => {
        const ratio = total > 0 ? loaded / total : 0;
        const percent = total > 0 ? Math.min(78, 5 + Math.round(ratio * 73)) : 18;
        reportProgress('downloading', percent, 'Downloading PDF');
      };
      state.document = await task.promise;
      reportProgress('rendering', 86, 'Building the PDF reading view');
      state.page = core.clampViewerPage(state.page, state.document.numPages);
      elements.placeholder.style.display = 'none';
      setControlsEnabled(true);
      updateControls();
      await buildPageShells(state.page);
      reportProgress('ready', 100, 'PDF ready');
      return true;
    } catch (_) {
      showFallback(url, page);
      return true;
    }
  }

  function initialize() {
    bindElements();
    if (!elements.scroll || !elements.pages) return;
    if (pdfjs) {
      pdfjs.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    }
    setControlsEnabled(false);
    document.getElementById('pdf-prev')?.addEventListener('click', () => goToPage(state.page - 1));
    document.getElementById('pdf-next')?.addEventListener('click', () => goToPage(state.page + 1));
    document.getElementById('pdf-zoom-out')?.addEventListener('click', () => setZoom(state.zoom - 0.15));
    document.getElementById('pdf-zoom-in')?.addEventListener('click', () => setZoom(state.zoom + 0.15));
    document.getElementById('pdf-fit-width')?.addEventListener('click', () => setZoom(1));
    elements.pageNumber?.addEventListener('change', () => goToPage(elements.pageNumber.value));
    elements.pageNumber?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        goToPage(elements.pageNumber.value);
        elements.pageNumber.blur();
      }
    });
    elements.scroll.addEventListener('scroll', () => {
      if (state.scrollFrame) cancelAnimationFrame(state.scrollFrame);
      state.scrollFrame = requestAnimationFrame(syncPageFromScroll);
    }, { passive: true });
    window.addEventListener('resize', () => {
      clearTimeout(state.resizeTimer);
      state.resizeTimer = setTimeout(() => {
        if (state.document && state.fitWidth) buildPageShells(state.page);
      }, 180);
    });
  }

  initialize();
  window.ResearchScopePdfViewer = { goToPage, open };
})();
