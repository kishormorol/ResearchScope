(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ResearchScopeChatCore = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function workspaceUrl(paperId, sessionId) {
    const params = new URLSearchParams();
    if (paperId) params.set('id', String(paperId));
    if (sessionId) params.set('session', String(sessionId));
    return `chat-paper${params.size ? `?${params}` : ''}`;
  }

  function consumeSse(buffer) {
    const normalized = buffer.replace(/\r\n/g, '\n');
    const blocks = normalized.split('\n\n');
    const rest = blocks.pop() || '';
    const events = [];
    for (const block of blocks) {
      let type = 'message';
      const data = [];
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) type = line.slice(6).trim();
        if (line.startsWith('data:')) data.push(line.slice(5).trim());
      }
      if (!data.length) continue;
      try { events.push({ type, data: JSON.parse(data.join('\n')) }); }
      catch (_) { events.push({ type: 'error', data: { code: 'invalid_stream_event' } }); }
    }
    return { events, rest };
  }

  function citationPage(citation) {
    const page = Number(citation && citation.page_start);
    return Number.isFinite(page) && page > 0 ? page : 1;
  }

  function clampViewerPage(value, totalPages) {
    const total = Math.max(1, Number(totalPages) || 1);
    const page = Math.round(Number(value) || 1);
    return Math.min(total, Math.max(1, page));
  }

  function clampViewerZoom(value) {
    const zoom = Number(value) || 1;
    return Math.min(2.25, Math.max(0.6, Math.round(zoom * 20) / 20));
  }

  function removeSessionById(sessions, sessionId) {
    if (!Array.isArray(sessions)) return [];
    return sessions.filter((session) => String(session?.id) !== String(sessionId));
  }

  function claimSendSlot(state) {
    if (!state || state.submitting || state.generating) return false;
    state.submitting = true;
    return true;
  }

  function paperLoadPercent(pdfPercent, contextPercent, includeContext) {
    const clamp = (value) => Math.min(100, Math.max(0, Number(value) || 0));
    const pdf = clamp(pdfPercent);
    if (!includeContext) return Math.round(pdf);
    const context = clamp(contextPercent);
    return Math.round((pdf * 0.7) + (context * 0.3));
  }

  function displayCitationLabels(value) {
    return String(value || '').replace(/\[S(\d+)\]/g, '[$1]');
  }

  function displayAnswerText(value) {
    const superscript = {
      0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹',
      '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
    };
    const subscript = {
      0: '₀', 1: '₁', 2: '₂', 3: '₃', 4: '₄', 5: '₅', 6: '₆', 7: '₇', 8: '₈', 9: '₉',
      '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎',
    };
    const translate = (text, characters) => [...text].map((item) => characters[item] || item).join('');
    let text = String(value || '');
    text = text.replace(/\\(?:text|mathrm|mathbf)\{([^{}]*)\}/g, '$1');
    text = text.replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, '$1/$2');
    text = text.replace(/\^\{([0-9+\-=()]+)\}/g, (_, part) => translate(part, superscript));
    text = text.replace(/_\{([0-9+\-=()]+)\}/g, (_, part) => translate(part, subscript));
    text = text.replace(/_([0-9+\-=()])/g, (_, part) => translate(part, subscript));
    text = text.replace(/\\times/g, '×').replace(/\\cdot/g, '·').replace(/\\pm/g, '±');
    text = text.replace(/\\leq/g, '≤').replace(/\\geq/g, '≥').replace(/\\neq/g, '≠');
    text = text.replace(/\\%/g, '%').replace(/\\[()[\]]/g, '').replace(/\*\*/g, '');
    return displayCitationLabels(text).trim();
  }

  function safeViewerUrl(value, baseUrl, apiBaseUrl) {
    if (!value) return '';
    try {
      const url = new URL(value, baseUrl || 'https://researchscope.invalid/');
      const allowed = [
        'arxiv.org', 'openreview.net', 'aclanthology.org',
        'proceedings.mlr.press', 'openaccess.thecvf.com',
        'semanticscholar.org', 'pdfs.semanticscholar.org',
      ];
      const host = url.hostname.toLowerCase();
      const trusted = allowed.some((item) => host === item || host.endsWith(`.${item}`));
      const base = new URL(baseUrl || 'https://researchscope.invalid/');
      const localHosts = ['127.0.0.1', 'localhost'];
      const localViewer = localHosts.includes(base.hostname) && localHosts.includes(host) &&
        (url.protocol === 'http:' || url.protocol === 'https:');
      let trustedApiViewer = false;
      if (apiBaseUrl) {
        const api = new URL(apiBaseUrl, base);
        trustedApiViewer = url.protocol === 'https:' && url.origin === api.origin;
      }
      return (url.protocol === 'https:' && (trusted || trustedApiViewer)) || localViewer
        ? url.href
        : '';
    } catch (_) {
      return '';
    }
  }

  return {
    citationPage, claimSendSlot, clampViewerPage, clampViewerZoom, consumeSse, displayAnswerText,
    displayCitationLabels, paperLoadPercent, removeSessionById, safeViewerUrl, workspaceUrl,
  };
});
