const test = require('node:test');
const assert = require('node:assert/strict');

const graph = require('../../site/assets/js/topic-graph.js');

const topics = [
  {
    id: 'llms',
    name: 'LLMs',
    keywords: ['large language model', 'generation'],
    paper_ids: ['p1', 'p2', 'p3'],
    trend_score: 9,
    starter_pack_ids: ['p1'],
    frontier_pack_ids: ['p2'],
    difficulty: 'frontier',
    related_topics: ['NLP'],
    prerequisites: ['transformers'],
  },
  {
    id: 'nlp',
    name: 'NLP',
    keywords: ['language', 'generation'],
    paper_ids: ['p1', 'p2'],
    trend_score: 7,
    difficulty: 'intermediate',
    related_topics: ['LLMs'],
  },
  {
    id: 'transformers',
    name: 'Transformers',
    keywords: ['attention'],
    paper_ids: ['p2', 'p3'],
    trend_score: 6,
    difficulty: 'L3',
  },
];

const papers = [
  {
    id: 'p1',
    title: 'A Survey of Large Language Models',
    authors: ['Ada Lovelace', 'Grace Hopper'],
    tags: ['LLMs', 'NLP', 'Survey'],
    venue: 'ACL 2025',
    source: 'acl_anthology',
    year: 2025,
    paper_type: 'survey',
    difficulty_level: 'L1',
    paper_score: 8.9,
    read_first_score: 8.1,
  },
  {
    id: 'p2',
    title: 'Efficient Transformer Reasoning',
    authors: ['Ada Lovelace'],
    tags: ['LLMs', 'Transformers'],
    venue: 'ICLR 2026',
    source: 'openreview',
    year: 2026,
    paper_type: 'methods',
    difficulty_level: 'L4',
    paper_score: 9.2,
    read_first_score: 6.2,
  },
  {
    id: 'p3',
    title: 'Attention Systems',
    authors: ['Alan Turing'],
    tags: ['Transformers', 'Systems'],
    venue: 'arXiv',
    source: 'arxiv',
    year: 2024,
    paper_type: 'systems',
    difficulty: 'advanced',
    paper_score: 7.2,
    read_first_score: 4.3,
  },
  {
    id: 'p4',
    title: 'Unrelated Vision Paper',
    authors: ['Katherine Johnson'],
    tags: ['Computer Vision'],
    venue: 'CVPR 2024',
    source: 'cvf',
    year: 2024,
    paper_type: 'benchmark',
    difficulty_level: 'L2',
    paper_score: 8,
    read_first_score: 5,
  },
];

test('normalizeDifficulty supports canonical and legacy values', () => {
  assert.equal(graph.normalizeDifficulty('beginner'), 'L1');
  assert.equal(graph.normalizeDifficulty('intermediate'), 'L2');
  assert.equal(graph.normalizeDifficulty('advanced'), 'L3');
  assert.equal(graph.normalizeDifficulty('frontier'), 'L4');
  assert.equal(graph.normalizeDifficulty('L3'), 'L3');
  assert.equal(graph.normalizeDifficulty('unknown'), 'L2');
});

test('buildTopicGraph creates topic, paper, and explanatory edges', () => {
  const built = graph.buildTopicGraph(topics, papers, {
    maxTopics: 3,
    maxPapers: 3,
    density: 'dense',
  });

  const summary = graph.summarizeGraph(built);
  assert.equal(summary.topicCount, 3);
  assert.equal(summary.paperCount, 3);
  assert.ok(summary.topicPaperEdgeCount >= 5);
  assert.ok(summary.topicTopicEdgeCount >= 2);
  assert.ok(summary.paperPaperEdgeCount >= 1);

  const starterEdge = built.edges.find((edge) => edge.id === 'edge:topic-paper:llms:p1');
  assert.equal(starterEdge.explanation, 'Paper is part of this topic starter path.');
});

test('paper-paper scoring records shared evidence', () => {
  const membership = graph.derivePaperTopicMembership(topics);
  const scored = graph.scorePaperPaperEdge(papers[0], papers[1], { membership });

  assert.ok(scored.weight > 4);
  assert.ok(scored.evidence.some((line) => line.includes('shared topics')));
  assert.ok(scored.evidence.some((line) => line.includes('shared authors')));
});

test('filters apply difficulty, source, year, type, score, and search', () => {
  const built = graph.buildTopicGraph(topics, papers, {
    maxTopics: 3,
    maxPapers: 10,
    difficulty: 'L4',
    source: 'openreview',
    yearMin: 2026,
    yearMax: 2026,
    paperType: 'methods',
    minPaperScore: 9,
    paperQuery: 'reasoning',
  });

  assert.equal(built.stats.paperCount, 1);
  assert.equal(built.nodes.filter((node) => node.kind === 'paper')[0].paperId, 'p2');
});

test('topic search matches names and keywords', () => {
  const byName = graph.buildTopicGraph(topics, papers, {
    topicQuery: 'nlp',
    maxTopics: 10,
    maxPapers: 10,
  });
  assert.deepEqual(
    byName.nodes.filter((node) => node.kind === 'topic').map((node) => node.topicId),
    ['nlp']
  );

  const byKeyword = graph.buildTopicGraph(topics, papers, {
    topicQuery: 'attention',
    maxTopics: 10,
    maxPapers: 10,
  });
  assert.deepEqual(
    byKeyword.nodes.filter((node) => node.kind === 'topic').map((node) => node.topicId),
    ['transformers']
  );
});

test('edge limiting honors per-paper and global caps', () => {
  const edges = [
    { id: 'e1', kind: 'paper-paper', source: 'paper:a', target: 'paper:b', weight: 9 },
    { id: 'e2', kind: 'paper-paper', source: 'paper:a', target: 'paper:c', weight: 8 },
    { id: 'e3', kind: 'paper-paper', source: 'paper:a', target: 'paper:d', weight: 7 },
    { id: 'e4', kind: 'topic-paper', source: 'topic:x', target: 'paper:a', weight: 1 },
  ];

  const limited = graph.limitEdges(edges, { perPaper: 1, maxEdges: 2 });
  assert.equal(limited.length, 2);
  assert.ok(limited.some((edge) => edge.id === 'e1'));
  assert.ok(limited.some((edge) => edge.id === 'e4'));
});

test('empty filters return a stable empty graph stats object', () => {
  const built = graph.buildTopicGraph(topics, papers, {
    topicQuery: 'does not exist',
    maxTopics: 10,
    maxPapers: 10,
  });

  assert.deepEqual(built.stats, {
    topicCount: 0,
    paperCount: 0,
    edgeCount: 0,
    hiddenPaperCount: 0,
    hiddenEdgeCount: 0,
  });
  assert.deepEqual(built.nodes, []);
  assert.deepEqual(built.edges, []);
});
