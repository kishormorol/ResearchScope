const assert = require('node:assert/strict');
const core = require('../../site/assets/js/chat-arxiv-core.js');

assert.equal(core.normalizeArxivId('1706.03762'), '1706.03762');
assert.equal(core.normalizeArxivId('arxiv:2601.20055v2'), '2601.20055v2');
assert.equal(
  core.normalizeArxivId('https://arxiv.org/pdf/1706.03762.pdf'),
  '1706.03762'
);
assert.equal(core.normalizeArxivId('https://export.arxiv.org/abs/cs/9901001'), '');
assert.equal(core.normalizeArxivId('https://example.com/1706.03762'), '');
assert.equal(core.normalizeArxivId('not-an-id'), '');
assert.equal(
  core.workspaceUrl('1706.03762'),
  'chat-paper?id=arxiv%3A1706.03762'
);

console.log('chat arXiv core tests passed');
