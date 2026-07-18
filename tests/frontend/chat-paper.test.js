const assert = require('node:assert/strict');
const core = require('../../site/assets/js/chat-paper-core.js');

assert.equal(
  core.workspaceUrl('arxiv:2501.12/34', 'session 1'),
  'chat-paper?id=arxiv%3A2501.12%2F34&session=session+1'
);

const first = core.consumeSse(
  'event: delta\ndata: {"text":"Hello"}\n\n' +
  'event: citations\ndata: {"citations":[{"page_start":4}]}\n\npartial'
);
assert.equal(first.events.length, 2);
assert.deepEqual(first.events[0], { type: 'delta', data: { text: 'Hello' } });
assert.equal(first.rest, 'partial');
assert.equal(core.citationPage(first.events[1].data.citations[0]), 4);
assert.equal(core.citationPage({ page_start: 0 }), 1);
assert.equal(core.clampViewerPage(7, 5), 5);
assert.equal(core.clampViewerPage(-2, 5), 1);
assert.equal(core.clampViewerZoom(0.1), 0.6);
assert.equal(core.clampViewerZoom(3), 2.25);
assert.equal(core.clampViewerZoom(1.234), 1.25);
assert.deepEqual(
  core.removeSessionById([{ id: 'keep' }, { id: 'delete' }], 'delete'),
  [{ id: 'keep' }]
);
assert.deepEqual(core.removeSessionById(null, 'delete'), []);
const sendState = { submitting: false, generating: false };
assert.equal(core.claimSendSlot(sendState), true);
assert.equal(sendState.submitting, true);
assert.equal(core.claimSendSlot(sendState), false);
sendState.submitting = false;
sendState.generating = true;
assert.equal(core.claimSendSlot(sendState), false);
assert.equal(core.paperLoadPercent(50, 50, true), 50);
assert.equal(core.paperLoadPercent(100, 50, true), 85);
assert.equal(core.paperLoadPercent(42.4, 0, false), 42);
assert.equal(core.paperLoadPercent(150, -10, true), 70);
assert.equal(
  core.displayCitationLabels('Method [S1], results [S2][S3].'),
  'Method [1], results [2][3].'
);
assert.equal(
  core.displayAnswerText(String.raw`At \(10^{-4}\), S_5 used 6 \times 10^{-4}; **supported** [S1].`),
  'At 10⁻⁴, S₅ used 6 × 10⁻⁴; supported [1].'
);
assert.equal(
  core.safeViewerUrl('https://export.arxiv.org/pdf/2501.1'),
  'https://export.arxiv.org/pdf/2501.1'
);
assert.equal(core.safeViewerUrl('https://arxiv.org.attacker.example/paper.pdf'), '');
assert.equal(core.safeViewerUrl('http://arxiv.org/pdf/2501.1'), '');
assert.equal(
  core.safeViewerUrl(
    'http://127.0.0.1:8000/papers/arxiv%3A2501.1/pdf',
    'http://127.0.0.1:8080/chat-paper'
  ),
  'http://127.0.0.1:8000/papers/arxiv%3A2501.1/pdf'
);
assert.equal(
  core.safeViewerUrl(
    'https://researchscope-production.up.railway.app/papers/arxiv%3A2501.1/pdf',
    'https://kishormorol.github.io/ResearchScope/chat-paper',
    'https://researchscope-production.up.railway.app'
  ),
  'https://researchscope-production.up.railway.app/papers/arxiv%3A2501.1/pdf'
);

const invalid = core.consumeSse('event: delta\ndata: not-json\n\n');
assert.equal(invalid.events[0].type, 'error');

console.log('chat-paper core tests passed');
