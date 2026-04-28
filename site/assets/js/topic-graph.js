(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
    return;
  }
  root.ResearchScopeTopicGraph = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const DIFFICULTY_MAP = {
    beginner: 'L1',
    intermediate: 'L2',
    advanced: 'L3',
    frontier: 'L4',
    l1: 'L1',
    l2: 'L2',
    l3: 'L3',
    l4: 'L4',
  };

  const DENSITY = {
    focused: { perPaper: 3, threshold: 4.2, maxEdges: 900 },
    balanced: { perPaper: 5, threshold: 3.2, maxEdges: 1600 },
    dense: { perPaper: 8, threshold: 2.4, maxEdges: 2500 },
  };

  const SOURCE_LABELS = {
    arxiv: 'arXiv',
    acl_anthology: 'ACL',
    acl: 'ACL',
    openreview: 'OpenReview',
    cvf: 'CVF',
    pmlr: 'PMLR',
  };

  function asArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function toKey(value) {
    return String(value || '').trim().toLowerCase();
  }

  function slug(value) {
    return toKey(value).replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  }

  function number(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function normalizeDifficulty(value) {
    const key = toKey(value);
    return DIFFICULTY_MAP[key] || (String(value || '').match(/^L[1-4]$/) ? value : 'L2');
  }

  function unique(values) {
    const seen = new Set();
    const result = [];
    for (const value of asArray(values)) {
      const normalized = String(value || '').trim();
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      result.push(normalized);
    }
    return result;
  }

  function intersection(a, b) {
    const left = new Set(asArray(a).map(toKey).filter(Boolean));
    const hits = [];
    for (const value of asArray(b)) {
      const key = toKey(value);
      if (key && left.has(key)) hits.push(value);
    }
    return unique(hits);
  }

  function jaccard(a, b) {
    const left = new Set(asArray(a).map(toKey).filter(Boolean));
    const right = new Set(asArray(b).map(toKey).filter(Boolean));
    if (!left.size && !right.size) return 0;
    let overlap = 0;
    left.forEach((value) => {
      if (right.has(value)) overlap += 1;
    });
    return overlap / (left.size + right.size - overlap);
  }

  function buildPaperIndex(papers) {
    const index = new Map();
    for (const paper of asArray(papers)) {
      if (paper && paper.id) index.set(String(paper.id), paper);
    }
    return index;
  }

  function buildTopicIndex(topics) {
    const index = new Map();
    for (const topic of asArray(topics)) {
      if (!topic) continue;
      const id = String(topic.id || slug(topic.name));
      if (id) index.set(id, topic);
      if (topic.name) index.set(slug(topic.name), topic);
    }
    return index;
  }

  function derivePaperTopicMembership(topics) {
    const membership = new Map();
    for (const topic of asArray(topics)) {
      const topicId = String(topic.id || slug(topic.name));
      if (!topicId) continue;
      for (const paperId of asArray(topic.paper_ids)) {
        const id = String(paperId);
        if (!membership.has(id)) membership.set(id, []);
        membership.get(id).push(topicId);
      }
    }
    return membership;
  }

  function searchableText(parts) {
    return parts.flatMap((part) => Array.isArray(part) ? part : [part])
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
  }

  function sourceGroup(paper) {
    const source = toKey(paper.source);
    const id = toKey(paper.id);
    if (source.includes('acl') || id.startsWith('acl:')) return 'acl';
    if (source.includes('openreview') || id.startsWith('openreview:')) return 'openreview';
    if (source.includes('cvf') || id.startsWith('cvf:')) return 'cvf';
    if (source.includes('pmlr') || id.startsWith('pmlr:')) return 'pmlr';
    if (source.includes('arxiv') || id.startsWith('arxiv:')) return 'arxiv';
    return source || 'other';
  }

  function paperPassesFilters(paper, filters) {
    const difficulty = normalizeDifficulty(paper.difficulty_level || paper.difficulty);
    const year = number(paper.year, 0);
    const source = sourceGroup(paper);
    const paperType = toKey(paper.paper_type);
    const paperText = searchableText([
      paper.title,
      paper.abstract,
      paper.summary,
      paper.venue,
      paper.paper_type,
      paper.authors,
      paper.tags,
    ]);

    if (filters.paperQuery && !paperText.includes(toKey(filters.paperQuery))) return false;
    if (filters.difficulty && filters.difficulty !== 'all' && difficulty !== filters.difficulty) return false;
    if (filters.source && filters.source !== 'all' && source !== filters.source) return false;
    if (filters.paperType && filters.paperType !== 'all' && paperType !== filters.paperType) return false;
    if (filters.yearMin && year && year < number(filters.yearMin, year)) return false;
    if (filters.yearMax && year && year > number(filters.yearMax, year)) return false;
    if (number(paper.paper_score, 0) < number(filters.minPaperScore, 0)) return false;
    if (number(paper.read_first_score, 0) < number(filters.minReadFirstScore, 0)) return false;
    return true;
  }

  function topicPassesFilters(topic, filters) {
    const difficulty = normalizeDifficulty(topic.difficulty);
    const topicText = searchableText([topic.name, topic.keywords]);
    if (filters.topicQuery && !topicText.includes(toKey(filters.topicQuery))) return false;
    if (filters.difficulty && filters.difficulty !== 'all' && difficulty !== filters.difficulty) return false;
    return true;
  }

  function filterGraphInputs(topics, papers, filters) {
    const settings = filters || {};
    const topicLimit = number(settings.maxTopics, 30);
    const paperLimit = number(settings.maxPapers || settings.limit, 75);
    const paperIndex = buildPaperIndex(papers);

    const topicRows = asArray(topics)
      .filter((topic) => topicPassesFilters(topic, settings))
      .sort((a, b) => number(b.trend_score, 0) - number(a.trend_score, 0))
      .slice(0, topicLimit);

    const allowedTopicPaperIds = new Set();
    topicRows.forEach((topic) => {
      asArray(topic.paper_ids).forEach((id) => allowedTopicPaperIds.add(String(id)));
    });

    const paperRows = Array.from(allowedTopicPaperIds)
      .map((id) => paperIndex.get(id))
      .filter(Boolean)
      .filter((paper) => paperPassesFilters(paper, settings))
      .sort((a, b) => {
        const scoreDelta = number(b.paper_score, 0) - number(a.paper_score, 0);
        if (scoreDelta) return scoreDelta;
        return String(a.title || a.id).localeCompare(String(b.title || b.id));
      })
      .slice(0, paperLimit);

    return {
      topics: topicRows,
      papers: settings.showPapers === false ? [] : paperRows,
      hiddenPaperCount: Math.max(0, allowedTopicPaperIds.size - paperRows.length),
    };
  }

  function makeTopicNode(topic) {
    const topicId = String(topic.id || slug(topic.name));
    return {
      id: `topic:${topicId}`,
      kind: 'topic',
      label: topic.name || topicId,
      topicId,
      difficulty: normalizeDifficulty(topic.difficulty),
      trendScore: number(topic.trend_score, 0),
      paperCount: asArray(topic.paper_ids).length,
      keywords: unique(topic.keywords),
      relatedTopics: unique(topic.related_topics),
      prerequisites: unique(topic.prerequisites),
      raw: topic,
    };
  }

  function makePaperNode(paper, topicIds) {
    return {
      id: `paper:${paper.id}`,
      kind: 'paper',
      label: paper.title || paper.id,
      paperId: paper.id,
      year: number(paper.year, 0),
      source: sourceGroup(paper),
      sourceLabel: SOURCE_LABELS[sourceGroup(paper)] || paper.source || 'Other',
      venue: paper.venue || '',
      paperType: paper.paper_type || '',
      difficulty: normalizeDifficulty(paper.difficulty_level || paper.difficulty),
      paperScore: number(paper.paper_score, 0),
      readFirstScore: number(paper.read_first_score, 0),
      tags: unique(paper.tags),
      authors: unique(paper.authors),
      url: paper.paper_url || paper.url || '',
      summary: paper.one_line_takeaway || paper.summary || paper.abstract || '',
      topicIds: unique(topicIds),
      raw: paper,
    };
  }

  function resolveTopicRef(ref, topicIndex) {
    const direct = topicIndex.get(String(ref || ''));
    if (direct) return String(direct.id || slug(direct.name));
    const bySlug = topicIndex.get(slug(ref));
    return bySlug ? String(bySlug.id || slug(bySlug.name)) : '';
  }

  function scoreTopicTopicEdge(topicA, topicB, context) {
    const aId = String(topicA.id || slug(topicA.name));
    const bId = String(topicB.id || slug(topicB.name));
    const topicIndex = context.topicIndex || buildTopicIndex(context.topics || []);
    const aRelated = asArray(topicA.related_topics).some((ref) => resolveTopicRef(ref, topicIndex) === bId);
    const bRelated = asArray(topicB.related_topics).some((ref) => resolveTopicRef(ref, topicIndex) === aId);
    const aPrereq = asArray(topicA.prerequisites).some((ref) => resolveTopicRef(ref, topicIndex) === bId);
    const bPrereq = asArray(topicB.prerequisites).some((ref) => resolveTopicRef(ref, topicIndex) === aId);
    const paperOverlap = jaccard(topicA.paper_ids, topicB.paper_ids);
    const keywordOverlap = jaccard(topicA.keywords, topicB.keywords);
    const weight = (aRelated || bRelated ? 3 : 0)
      + (aPrereq || bPrereq ? 2 : 0)
      + paperOverlap * 4
      + keywordOverlap * 2;

    const evidence = [];
    if (aRelated || bRelated) evidence.push('listed as related topics');
    if (aPrereq || bPrereq) evidence.push('prerequisite relationship');
    if (paperOverlap > 0) evidence.push('overlapping papers');
    if (keywordOverlap > 0) evidence.push('overlapping keywords');

    return {
      weight,
      evidence,
      type: aPrereq || bPrereq ? 'prerequisite' : 'topic-topic',
    };
  }

  function scorePaperPaperEdge(paperA, paperB, context) {
    const topicA = asArray(context.membership.get(paperA.id));
    const topicB = asArray(context.membership.get(paperB.id));
    const sharedTopics = intersection(topicA, topicB);
    const sharedTags = intersection(paperA.tags, paperB.tags);
    const sharedAuthors = intersection(paperA.authors, paperB.authors);
    const sameVenue = paperA.venue && paperB.venue && toKey(paperA.venue) === toKey(paperB.venue);
    const sameType = paperA.paper_type && paperB.paper_type && toKey(paperA.paper_type) === toKey(paperB.paper_type);
    const diffA = normalizeDifficulty(paperA.difficulty_level || paperA.difficulty);
    const diffB = normalizeDifficulty(paperB.difficulty_level || paperB.difficulty);
    const sameDifficulty = diffA === diffB;
    const yearDistance = Math.abs(number(paperA.year, 0) - number(paperB.year, 0));
    const closeYearBonus = yearDistance === 0 ? 0.6 : (yearDistance <= 2 ? 0.3 : 0);

    const weight = sharedTopics.length * 3.0
      + sharedTags.length * 1.4
      + sharedAuthors.length * 2.5
      + (sameVenue ? 0.8 : 0)
      + (sameType ? 0.5 : 0)
      + (sameDifficulty ? 0.3 : 0)
      + closeYearBonus;

    const evidence = [];
    if (sharedTopics.length) evidence.push(`shared topics: ${sharedTopics.join(', ')}`);
    if (sharedTags.length) evidence.push(`shared tags: ${sharedTags.slice(0, 5).join(', ')}`);
    if (sharedAuthors.length) evidence.push(`shared authors: ${sharedAuthors.slice(0, 4).join(', ')}`);
    if (sameVenue) evidence.push(`same venue: ${paperA.venue}`);
    if (sameType) evidence.push(`same paper type: ${paperA.paper_type}`);
    if (sameDifficulty) evidence.push(`same difficulty: ${diffA}`);
    if (closeYearBonus) evidence.push('published in a close year window');

    return { weight, evidence, sharedTopics, sharedTags, sharedAuthors };
  }

  function pairKey(a, b) {
    return a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`;
  }

  function addCandidatePair(scores, ids, amount, reason) {
    const list = Array.from(new Set(ids)).sort();
    const localCap = 140;
    for (let i = 0; i < Math.min(list.length, localCap); i += 1) {
      for (let j = i + 1; j < Math.min(list.length, localCap); j += 1) {
        const key = pairKey(list[i], list[j]);
        if (!scores.has(key)) scores.set(key, { score: 0, reasons: new Set() });
        const row = scores.get(key);
        row.score += amount;
        row.reasons.add(reason);
      }
    }
  }

  function buildInvertedIndexes(papers, membership) {
    const indexes = {
      tags: new Map(),
      authors: new Map(),
      topics: new Map(),
      venue: new Map(),
    };

    function push(map, key, paperId) {
      const normalized = toKey(key);
      if (!normalized) return;
      if (!map.has(normalized)) map.set(normalized, []);
      map.get(normalized).push(paperId);
    }

    for (const paper of papers) {
      asArray(paper.tags).forEach((tag) => push(indexes.tags, tag, paper.id));
      asArray(paper.authors).forEach((author) => push(indexes.authors, author, paper.id));
      asArray(membership.get(paper.id)).forEach((topicId) => push(indexes.topics, topicId, paper.id));
      push(indexes.venue, paper.venue, paper.id);
    }

    return indexes;
  }

  function limitEdges(edges, options) {
    const settings = options || {};
    const density = DENSITY[settings.density || 'balanced'] || DENSITY.balanced;
    const maxEdges = number(settings.maxEdges, density.maxEdges);
    const perPaper = number(settings.perPaper, density.perPaper);
    const counts = new Map();
    const kept = [];
    const sorted = edges.slice().sort((a, b) => {
      const weightDelta = number(b.weight, 0) - number(a.weight, 0);
      if (weightDelta) return weightDelta;
      return String(a.id).localeCompare(String(b.id));
    });

    for (const edge of sorted) {
      if (kept.length >= maxEdges) break;
      if (edge.kind === 'paper-paper') {
        const aCount = counts.get(edge.source) || 0;
        const bCount = counts.get(edge.target) || 0;
        if (aCount >= perPaper || bCount >= perPaper) continue;
        counts.set(edge.source, aCount + 1);
        counts.set(edge.target, bCount + 1);
      }
      kept.push(edge);
    }

    return kept.sort((a, b) => String(a.id).localeCompare(String(b.id)));
  }

  function buildPaperPaperEdges(papers, membership, options) {
    const settings = options || {};
    const density = DENSITY[settings.density || 'balanced'] || DENSITY.balanced;
    const threshold = number(settings.paperPaperThreshold, density.threshold);
    const paperMap = buildPaperIndex(papers);
    const candidateScores = new Map();
    const indexes = buildInvertedIndexes(papers, membership);

    indexes.topics.forEach((ids) => addCandidatePair(candidateScores, ids, 3, 'topic'));
    indexes.tags.forEach((ids) => addCandidatePair(candidateScores, ids, 1.4, 'tag'));
    indexes.authors.forEach((ids) => addCandidatePair(candidateScores, ids, 2.5, 'author'));
    indexes.venue.forEach((ids) => addCandidatePair(candidateScores, ids, 0.8, 'venue'));

    const edges = [];
    candidateScores.forEach((candidate, key) => {
      const [aId, bId] = key.split('\u0000');
      const a = paperMap.get(aId);
      const b = paperMap.get(bId);
      if (!a || !b) return;
      const scored = scorePaperPaperEdge(a, b, { membership });
      if (scored.weight < threshold) return;
      edges.push({
        id: `edge:paper:${aId}:${bId}`,
        kind: 'paper-paper',
        source: `paper:${aId}`,
        target: `paper:${bId}`,
        weight: Number(scored.weight.toFixed(2)),
        evidence: scored.evidence,
        explanation: scored.evidence.length
          ? scored.evidence.join('; ')
          : 'Papers share weak bibliographic or topic signals.',
      });
    });

    return edges;
  }

  function enabledRelation(options, relation) {
    const relations = options && options.relations;
    if (!relations) return true;
    return relations[relation] !== false;
  }

  function buildTopicGraph(topics, papers, options) {
    const settings = options || {};
    const filtered = filterGraphInputs(topics, papers, settings);
    const topicIndex = buildTopicIndex(filtered.topics);
    const fullMembership = derivePaperTopicMembership(topics);
    const visiblePaperIds = new Set(filtered.papers.map((paper) => paper.id));
    const visibleTopicIds = new Set(filtered.topics.map((topic) => String(topic.id || slug(topic.name))));
    const nodes = [];
    const edges = [];

    filtered.topics.forEach((topic) => nodes.push(makeTopicNode(topic)));
    filtered.papers.forEach((paper) => {
      const topicIds = asArray(fullMembership.get(paper.id)).filter((topicId) => visibleTopicIds.has(topicId));
      nodes.push(makePaperNode(paper, topicIds));
    });

    if (enabledRelation(settings, 'topicPaper')) {
      filtered.topics.forEach((topic) => {
        const topicId = String(topic.id || slug(topic.name));
        asArray(topic.paper_ids).forEach((paperId) => {
          const id = String(paperId);
          if (!visiblePaperIds.has(id)) return;
          const starter = asArray(topic.starter_pack_ids).includes(id);
          const frontier = asArray(topic.frontier_pack_ids).includes(id);
          const weight = 1 + (starter ? 0.5 : 0) + (frontier ? 0.7 : 0);
          edges.push({
            id: `edge:topic-paper:${topicId}:${id}`,
            kind: 'topic-paper',
            source: `topic:${topicId}`,
            target: `paper:${id}`,
            weight,
            evidence: [starter ? 'starter paper' : '', frontier ? 'frontier paper' : ''].filter(Boolean),
            explanation: starter
              ? 'Paper is part of this topic starter path.'
              : (frontier ? 'Paper is part of this topic frontier path.' : 'Paper belongs to this topic.'),
          });
        });
      });
    }

    if (enabledRelation(settings, 'topicTopic')) {
      for (let i = 0; i < filtered.topics.length; i += 1) {
        for (let j = i + 1; j < filtered.topics.length; j += 1) {
          const a = filtered.topics[i];
          const b = filtered.topics[j];
          const aId = String(a.id || slug(a.name));
          const bId = String(b.id || slug(b.name));
          const scored = scoreTopicTopicEdge(a, b, { topics: filtered.topics, topicIndex });
          if (scored.weight < 0.7) continue;
          if (scored.type === 'prerequisite' && !enabledRelation(settings, 'prerequisite')) continue;
          edges.push({
            id: `edge:topic:${aId}:${bId}`,
            kind: scored.type,
            source: `topic:${aId}`,
            target: `topic:${bId}`,
            weight: Number(scored.weight.toFixed(2)),
            evidence: scored.evidence,
            explanation: scored.evidence.length
              ? scored.evidence.join('; ')
              : 'Topics share papers or keywords.',
          });
        }
      }
    }

    if (enabledRelation(settings, 'paperPaper') && filtered.papers.length > 1) {
      edges.push(...buildPaperPaperEdges(filtered.papers, fullMembership, settings));
    }

    const limitedEdges = limitEdges(edges, settings);
    return {
      nodes: nodes.sort((a, b) => String(a.id).localeCompare(String(b.id))),
      edges: limitedEdges,
      stats: {
        topicCount: filtered.topics.length,
        paperCount: filtered.papers.length,
        edgeCount: limitedEdges.length,
        hiddenPaperCount: filtered.hiddenPaperCount,
        hiddenEdgeCount: Math.max(0, edges.length - limitedEdges.length),
      },
    };
  }

  function summarizeGraph(graph) {
    const summary = {
      topicCount: 0,
      paperCount: 0,
      edgeCount: 0,
      topicPaperEdgeCount: 0,
      topicTopicEdgeCount: 0,
      paperPaperEdgeCount: 0,
    };
    asArray(graph && graph.nodes).forEach((node) => {
      if (node.kind === 'topic') summary.topicCount += 1;
      if (node.kind === 'paper') summary.paperCount += 1;
    });
    asArray(graph && graph.edges).forEach((edge) => {
      summary.edgeCount += 1;
      if (edge.kind === 'topic-paper') summary.topicPaperEdgeCount += 1;
      if (edge.kind === 'topic-topic' || edge.kind === 'prerequisite') summary.topicTopicEdgeCount += 1;
      if (edge.kind === 'paper-paper') summary.paperPaperEdgeCount += 1;
    });
    return summary;
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function truncate(value, max) {
    const text = String(value || '');
    return text.length > max ? `${text.slice(0, max)}...` : text;
  }

  function computeLayout(graph, width, height) {
    const topicNodes = graph.nodes.filter((node) => node.kind === 'topic');
    const paperNodes = graph.nodes.filter((node) => node.kind === 'paper');
    const positions = new Map();
    const cx = width / 2;
    const cy = height / 2;
    const shortestSide = Math.min(width, height);
    const topicRadius = Math.max(120, shortestSide * 0.27);
    const paperRadius = Math.max(205, shortestSide * 0.44);

    topicNodes.forEach((node, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(1, topicNodes.length) - Math.PI / 2;
      const ringOffset = (index % 2) * 22;
      positions.set(node.id, {
        x: cx + Math.cos(angle) * (topicRadius + ringOffset),
        y: cy + Math.sin(angle) * (topicRadius + ringOffset),
      });
    });

    paperNodes.forEach((node, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(1, paperNodes.length) - Math.PI / 2;
      const wobble = (index % 3) * 30;
      positions.set(node.id, {
        x: cx + Math.cos(angle) * (paperRadius + wobble),
        y: cy + Math.sin(angle) * (paperRadius + wobble),
      });
    });

    return positions;
  }

  function renderDetails(nodeOrEdge, graph, options) {
    const panel = options.panel;
    if (!panel) return;
    if (!nodeOrEdge) {
      panel.innerHTML = `
        <div class="topic-graph-panel-empty">
          <p class="font-semibold">Select a node or edge</p>
          <p>Click any topic, paper, or connection to inspect why it appears in the graph.</p>
        </div>`;
      return;
    }

    if (nodeOrEdge.source && nodeOrEdge.target) {
      panel.innerHTML = `
        <div class="topic-graph-panel-section">
          <p class="topic-graph-kicker">${escapeHtml(nodeOrEdge.kind.replace('-', ' '))}</p>
          <h3>${escapeHtml(nodeOrEdge.kind === 'paper-paper' ? 'Paper relationship' : 'Topic relationship')}</h3>
          <p class="topic-graph-muted">Weight ${number(nodeOrEdge.weight, 0).toFixed(1)}</p>
          <p>${escapeHtml(nodeOrEdge.explanation || 'These items are connected by shared evidence.')}</p>
        </div>`;
      return;
    }

    if (nodeOrEdge.kind === 'topic') {
      const keywords = asArray(nodeOrEdge.keywords).slice(0, 8)
        .map((keyword) => `<span class="badge badge-tag">${escapeHtml(keyword)}</span>`).join('');
      const related = asArray(nodeOrEdge.relatedTopics).slice(0, 6)
        .map((topic) => `<span class="topic-graph-mini-chip">${escapeHtml(topic)}</span>`).join('');
      panel.innerHTML = `
        <div class="topic-graph-panel-section">
          <p class="topic-graph-kicker">Topic</p>
          <h3>${escapeHtml(nodeOrEdge.label)}</h3>
          <div class="topic-graph-metrics">
            <span>${escapeHtml(nodeOrEdge.difficulty)}</span>
            <span>${number(nodeOrEdge.trendScore, 0).toFixed(1)} trend</span>
            <span>${nodeOrEdge.paperCount} papers</span>
          </div>
          <div class="topic-graph-chip-row">${keywords}</div>
          ${related ? `<p class="topic-graph-subhead">Related</p><div class="topic-graph-chip-row">${related}</div>` : ''}
          <button type="button" class="topic-graph-action" data-topic-open="${escapeHtml(nodeOrEdge.topicId)}">Open reading path</button>
        </div>`;
      return;
    }

    const tags = asArray(nodeOrEdge.tags).slice(0, 8)
      .map((tag) => `<span class="badge badge-tag">${escapeHtml(tag)}</span>`).join('');
    const authors = asArray(nodeOrEdge.authors).slice(0, 4).join(', ');
    const paperSearchUrl = `papers.html?q=${encodeURIComponent(nodeOrEdge.label || '')}`;
    panel.innerHTML = `
      <div class="topic-graph-panel-section">
        <p class="topic-graph-kicker">Paper</p>
        <h3>${escapeHtml(nodeOrEdge.label)}</h3>
        <p class="topic-graph-muted">${escapeHtml(authors)}${authors ? ' · ' : ''}${escapeHtml(nodeOrEdge.venue || nodeOrEdge.sourceLabel)} ${nodeOrEdge.year || ''}</p>
        <div class="topic-graph-metrics">
          <span>${number(nodeOrEdge.paperScore, 0).toFixed(1)} score</span>
          <span>${number(nodeOrEdge.readFirstScore, 0).toFixed(1)} read first</span>
          <span>${escapeHtml(nodeOrEdge.difficulty)}</span>
        </div>
        <p>${escapeHtml(truncate(nodeOrEdge.summary, 260))}</p>
        <div class="topic-graph-chip-row">${tags}</div>
        <div class="topic-graph-action-row">
          ${nodeOrEdge.url ? `<a class="topic-graph-action" target="_blank" rel="noopener" href="${escapeHtml(nodeOrEdge.url)}">Open paper</a>` : ''}
          <a class="topic-graph-action secondary" href="${escapeHtml(paperSearchUrl)}">Find in Papers</a>
        </div>
      </div>`;
  }

  function renderGraph(container, graph, options) {
    const settings = options || {};
    if (!container) return null;
    container.innerHTML = '';
    const width = Math.max(container.clientWidth || 900, 320);
    const height = Math.max(container.clientHeight || 620, 420);
    const layoutWidth = Math.max(width * 1.25, 1120);
    const layoutHeight = Math.max(height * 1.2, 780);
    if (!graph.nodes.length) {
      container.innerHTML = '<div class="topic-graph-empty">No graph nodes match the current filters.</div>';
      renderDetails(null, graph, settings);
      return null;
    }

    const positions = computeLayout(graph, layoutWidth, layoutHeight);
    const svgNs = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNs, 'svg');
    const viewState = {
      x: 0,
      y: 0,
      width: layoutWidth,
      height: layoutHeight,
    };
    function applyViewBox() {
      svg.setAttribute('viewBox', `${viewState.x} ${viewState.y} ${viewState.width} ${viewState.height}`);
    }
    applyViewBox();
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'Topic and paper network graph');
    svg.classList.add('topic-graph-svg');

    const edgeLayer = document.createElementNS(svgNs, 'g');
    const nodeLayer = document.createElementNS(svgNs, 'g');
    svg.append(edgeLayer, nodeLayer);

    const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
    const elementsByNode = new Map();
    const elementsByEdge = new Map();
    let selectedId = '';

    function connectedIds(id) {
      const ids = new Set([id]);
      graph.edges.forEach((edge) => {
        if (edge.source === id) ids.add(edge.target);
        if (edge.target === id) ids.add(edge.source);
      });
      return ids;
    }

    function applyHighlight(id) {
      const connected = id ? connectedIds(id) : null;
      elementsByNode.forEach((el, nodeId) => {
        el.classList.toggle('is-dimmed', Boolean(connected && !connected.has(nodeId)));
        el.classList.toggle('is-selected', selectedId === nodeId);
        el.classList.toggle('is-neighbor', Boolean(connected && connected.has(nodeId) && selectedId !== nodeId));
      });
      elementsByEdge.forEach((el, edgeId) => {
        const edge = graph.edges.find((item) => item.id === edgeId);
        const active = connected && edge && connected.has(edge.source) && connected.has(edge.target);
        el.classList.toggle('is-dimmed', Boolean(connected && !active));
        el.classList.toggle('is-selected', selectedId === edgeId);
        el.classList.toggle('is-active-edge', Boolean(active && selectedId !== edgeId));
      });
    }

    graph.edges.forEach((edge) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) return;
      const line = document.createElementNS(svgNs, 'line');
      line.setAttribute('x1', source.x);
      line.setAttribute('y1', source.y);
      line.setAttribute('x2', target.x);
      line.setAttribute('y2', target.y);
      line.setAttribute('stroke-width', String(Math.max(1, Math.min(5, edge.weight))));
      line.classList.add('topic-graph-edge', `edge-${edge.kind}`);
      line.tabIndex = 0;
      line.addEventListener('click', () => {
        selectedId = edge.id;
        renderDetails(edge, graph, settings);
        applyHighlight(edge.source);
      });
      line.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') line.dispatchEvent(new Event('click'));
      });
      elementsByEdge.set(edge.id, line);
      edgeLayer.appendChild(line);
    });

    graph.nodes.forEach((node) => {
      const pos = positions.get(node.id);
      if (!pos) return;
      const group = document.createElementNS(svgNs, 'g');
      group.classList.add('topic-graph-node', `node-${node.kind}`);
      group.tabIndex = 0;
      group.setAttribute('transform', `translate(${pos.x}, ${pos.y})`);

      const title = document.createElementNS(svgNs, 'title');
      title.textContent = node.kind === 'topic'
        ? `${node.label}: ${node.paperCount} papers`
        : `${node.label}: ${node.paperScore.toFixed(1)} score`;
      group.appendChild(title);

      if (node.kind === 'topic') {
        const radius = Math.max(16, Math.min(34, 15 + Math.sqrt(node.paperCount || 1)));
        const circle = document.createElementNS(svgNs, 'circle');
        circle.setAttribute('r', String(radius));
        group.appendChild(circle);
      } else {
        const radius = Math.max(5, Math.min(12, 5 + node.paperScore / 2));
        const circle = document.createElementNS(svgNs, 'circle');
        circle.setAttribute('r', String(radius));
        group.appendChild(circle);
      }

      const label = document.createElementNS(svgNs, 'text');
      label.setAttribute('y', node.kind === 'topic' ? '46' : '22');
      label.setAttribute('text-anchor', 'middle');
      label.textContent = truncate(node.label, node.kind === 'topic' ? 24 : 18);
      group.appendChild(label);

      group.addEventListener('mouseenter', () => applyHighlight(node.id));
      group.addEventListener('mouseleave', () => applyHighlight(selectedId.startsWith('edge:') ? '' : selectedId));
      group.addEventListener('click', () => {
        selectedId = node.id;
        renderDetails(node, graph, settings);
        applyHighlight(node.id);
      });
      group.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') group.dispatchEvent(new Event('click'));
      });
      elementsByNode.set(node.id, group);
      nodeLayer.appendChild(group);
    });

    container.appendChild(svg);
    renderDetails(null, graph, settings);
    function zoom(scale) {
      const nextWidth = Math.max(260, Math.min(layoutWidth, viewState.width * scale));
      const nextHeight = Math.max(220, Math.min(layoutHeight, viewState.height * scale));
      const centerX = viewState.x + viewState.width / 2;
      const centerY = viewState.y + viewState.height / 2;
      viewState.width = nextWidth;
      viewState.height = nextHeight;
      viewState.x = Math.max(0, Math.min(layoutWidth - viewState.width, centerX - viewState.width / 2));
      viewState.y = Math.max(0, Math.min(layoutHeight - viewState.height, centerY - viewState.height / 2));
      applyViewBox();
    }

    return {
      fit: function () {
        viewState.x = 0;
        viewState.y = 0;
        viewState.width = layoutWidth;
        viewState.height = layoutHeight;
        applyViewBox();
      },
      zoomIn: function () {
        zoom(0.78);
      },
      zoomOut: function () {
        zoom(1.28);
      },
      focusNode: function (nodeId) {
        const node = nodeById.get(nodeId);
        if (!node) return false;
        const pos = positions.get(nodeId);
        if (pos) {
          viewState.x = Math.max(0, Math.min(layoutWidth - viewState.width, pos.x - viewState.width / 2));
          viewState.y = Math.max(0, Math.min(layoutHeight - viewState.height, pos.y - viewState.height / 2));
          applyViewBox();
        }
        selectedId = nodeId;
        renderDetails(node, graph, settings);
        applyHighlight(nodeId);
        return true;
      },
    };
  }

  return {
    buildPaperIndex,
    buildTopicGraph,
    buildTopicIndex,
    derivePaperTopicMembership,
    filterGraphInputs,
    limitEdges,
    normalizeDifficulty,
    renderGraph,
    scorePaperPaperEdge,
    scoreTopicTopicEdge,
    summarizeGraph,
  };
});
