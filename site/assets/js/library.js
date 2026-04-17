(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
    return;
  }
  root.ResearchScopeLibrary = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const STORAGE_KEY = 'researchscope:library';
  function getStorage(storage) {
    if (storage) return storage;
    if (typeof window !== 'undefined' && window.localStorage) return window.localStorage;
    return null;
  }

  function escapeAttr(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function getPaperLibraryId(paper) {
    if (!paper || typeof paper !== 'object') return '';
    return String(
      paper.id ||
      paper.canonical_id ||
      paper.paper_url ||
      paper.url ||
      paper.title ||
      ''
    ).trim();
  }

  function normalizeLibraryIds(ids) {
    if (!Array.isArray(ids)) return [];
    const seen = new Set();
    const normalized = [];

    for (const value of ids) {
      if (typeof value !== 'string') continue;
      const id = value.trim();
      if (!id || seen.has(id)) continue;
      seen.add(id);
      normalized.push(id);
    }

    return normalized;
  }

  function readStoredIds(target, key) {
    try {
      const raw = target.getItem(key);
      if (!raw) return [];
      return normalizeLibraryIds(JSON.parse(raw));
    } catch (_) {
      return [];
    }
  }

  function readLibraryIds(storage) {
    const target = getStorage(storage);
    if (!target) return [];

    return readStoredIds(target, STORAGE_KEY);
  }

  function persistLibraryIds(ids, storage) {
    const target = getStorage(storage);
    const normalized = normalizeLibraryIds(ids);
    if (!target) {
      return { ids: normalized, persisted: false };
    }

    try {
      if (!normalized.length) {
        target.removeItem(STORAGE_KEY);
      } else {
        target.setItem(STORAGE_KEY, JSON.stringify(normalized));
      }
      return { ids: normalized, persisted: true };
    } catch (_) {
      return { ids: readStoredIds(target, STORAGE_KEY), persisted: false };
    }
  }

  function writeLibraryIds(ids, storage) {
    return persistLibraryIds(ids, storage).ids;
  }

  function resolveLibraryId(paperOrId) {
    if (typeof paperOrId === 'string') return paperOrId.trim();
    return getPaperLibraryId(paperOrId);
  }

  function isInLibrary(paperOrId, storage) {
    const id = resolveLibraryId(paperOrId);
    if (!id) return false;
    return readLibraryIds(storage).includes(id);
  }

  function addToLibrary(paperOrId, storage) {
    const id = resolveLibraryId(paperOrId);
    const ids = readLibraryIds(storage);

    if (!id) {
      return { ids, inLibrary: false, changed: false };
    }
    if (ids.includes(id)) {
      return { ids, inLibrary: true, changed: false };
    }

    const result = persistLibraryIds(ids.concat(id), storage);
    return {
      ids: result.ids,
      inLibrary: result.ids.includes(id),
      changed: result.persisted,
    };
  }

  function removeFromLibrary(paperOrId, storage) {
    const id = resolveLibraryId(paperOrId);
    const ids = readLibraryIds(storage);

    if (!id || !ids.includes(id)) {
      return { ids, inLibrary: false, changed: false };
    }

    const result = persistLibraryIds(
      ids.filter((libraryId) => libraryId !== id),
      storage
    );
    return {
      ids: result.ids,
      inLibrary: result.ids.includes(id),
      changed: result.persisted,
    };
  }

  function toggleLibraryItem(paperOrId, storage) {
    return isInLibrary(paperOrId, storage)
      ? removeFromLibrary(paperOrId, storage)
      : addToLibrary(paperOrId, storage);
  }

  function getLibraryPapers(papers, libraryIds) {
    const ids = Array.isArray(libraryIds)
      ? normalizeLibraryIds(libraryIds)
      : readLibraryIds();

    if (!Array.isArray(papers) || !papers.length || !ids.length) return [];

    const paperMap = new Map();
    for (const paper of papers) {
      const id = getPaperLibraryId(paper);
      if (id && !paperMap.has(id)) {
        paperMap.set(id, paper);
      }
    }

    return ids.map((id) => paperMap.get(id)).filter(Boolean);
  }

  function getLibraryButtonLabel(inLibrary) {
    return inLibrary ? 'Remove from library' : 'Add to library';
  }

  function getLibraryButtonIcon(inLibrary) {
    if (inLibrary) {
      return `<svg viewBox="0 0 20 20" width="16" height="16" fill="currentColor">
        <path fill-rule="evenodd" clip-rule="evenodd" d="M4 2.75A2.75 2.75 0 0 0 1.25 5.5v11.46c0 .98 1.05 1.6 1.9 1.13L10 14.41l6.85 3.68c.85.47 1.9-.15 1.9-1.13V5.5A2.75 2.75 0 0 0 16 2.75H4Z" />
      </svg>`;
    }
    return `<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6">
      <path d="M4.4 2.8h11.2A2.4 2.4 0 0 1 18 5.2v11.44a.9.9 0 0 1-1.32.8L10 13.86l-6.68 3.58a.9.9 0 0 1-1.32-.8V5.2a2.4 2.4 0 0 1 2.4-2.4Z" />
    </svg>`;
  }

  function applyLibraryButtonState(button, inLibrary) {
    if (!button) return;

    const label = getLibraryButtonLabel(inLibrary);
    button.classList.toggle('is-active', inLibrary);
    button.setAttribute('aria-pressed', String(inLibrary));
    button.setAttribute('aria-label', label);
    button.setAttribute('title', label);

    const icon = button.querySelector('[data-library-icon]');
    if (icon) {
      icon.innerHTML = getLibraryButtonIcon(inLibrary);
    }
  }

  function renderLibraryButton(paperOrId, options) {
    const settings = options || {};
    const id = resolveLibraryId(paperOrId);
    if (!id) return '';

    const inLibrary = typeof settings.inLibrary === 'boolean'
      ? settings.inLibrary
      : isInLibrary(id, settings.storage);
    const label = getLibraryButtonLabel(inLibrary);
    const classes = [
      'library-toggle',
      inLibrary ? 'is-active' : '',
    ].filter(Boolean).join(' ');

    return `<button type="button" class="${classes}" data-library-toggle="paper" data-library-id="${escapeAttr(id)}" aria-pressed="${String(inLibrary)}" aria-label="${label}" title="${label}">
      <span class="library-toggle__icon" data-library-icon aria-hidden="true">${getLibraryButtonIcon(inLibrary)}</span>
    </button>`;
  }

  function syncLibraryButtons(root, storage) {
    const host = root || (typeof document !== 'undefined' ? document : null);
    if (!host || !host.querySelectorAll) return new Set();

    const lookup = new Set(readLibraryIds(storage));
    host.querySelectorAll('[data-library-toggle="paper"]').forEach((button) => {
      applyLibraryButtonState(button, lookup.has(button.dataset.libraryId || ''));
    });

    return lookup;
  }

  function rootContains(root, element) {
    if (!root || !element) return false;
    if (typeof document !== 'undefined' && root === document && document.documentElement) {
      return document.documentElement.contains(element);
    }
    return typeof root.contains === 'function' ? root.contains(element) : false;
  }

  function initializeLibraryButtons(options) {
    const settings = options || {};
    const root = settings.root || (typeof document !== 'undefined' ? document : null);
    if (!root || !root.addEventListener) {
      return { refresh: function () { return new Set(); } };
    }

    if (!root.__researchScopeLibraryBound) {
      root.addEventListener('click', function (event) {
        const target = event.target;
        if (!target || !target.closest) return;

        const button = target.closest('[data-library-toggle="paper"]');
        if (!button || !rootContains(root, button)) return;

        event.preventDefault();
        event.stopPropagation();

        const result = toggleLibraryItem(button.dataset.libraryId || '', settings.storage);
        syncLibraryButtons(root, settings.storage);

        if (typeof settings.onChange === 'function') {
          settings.onChange(result);
        }
      }, true);

      root.__researchScopeLibraryBound = true;
    }

    return {
      refresh: function () {
        return syncLibraryButtons(root, settings.storage);
      },
    };
  }

  return {
    STORAGE_KEY,
    addToLibrary,
    getLibraryPapers,
    getPaperLibraryId,
    initializeLibraryButtons,
    isInLibrary,
    readLibraryIds,
    removeFromLibrary,
    renderLibraryButton,
    syncLibraryButtons,
    toggleLibraryItem,
    writeLibraryIds,
  };
});
