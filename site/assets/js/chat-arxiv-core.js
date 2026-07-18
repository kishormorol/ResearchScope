(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ResearchScopeArxivCore = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function normalizeArxivId(value) {
    let input = String(value || '').trim();
    if (!input) return '';
    input = input.replace(/^arxiv:/i, '');
    try {
      const url = new URL(input);
      if (!/(^|\.)arxiv\.org$/i.test(url.hostname)) return '';
      const match = url.pathname.match(/^\/(?:abs|pdf)\/(.+?)(?:\.pdf)?\/?$/i);
      input = match ? decodeURIComponent(match[1]) : '';
    } catch (_) { /* raw arXiv ID */ }
    input = input.replace(/\.pdf$/i, '').replace(/^\/+|\/+$/g, '');
    const modern = /^\d{4}\.\d{4,5}(?:v\d+)?$/i;
    return modern.test(input) ? input : '';
  }

  function workspaceUrl(arxivId) {
    const normalized = normalizeArxivId(arxivId);
    return normalized ? `chat-paper?id=${encodeURIComponent(`arxiv:${normalized}`)}` : '';
  }

  return { normalizeArxivId, workspaceUrl };
});
