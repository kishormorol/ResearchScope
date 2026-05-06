/**
 * ResearchScope — Supabase query helpers (browser)
 *
 * Requires @supabase/supabase-js loaded via CDN before this file.
 */

const SUPABASE_URL  = 'https://ippobommkdtemzfcmqic.supabase.co';
const SUPABASE_ANON = 'sb_publishable_BQ3WaQV3Pfm55flynjvtWQ_Lri13024';

let _db = null;
function getDb() {
  if (!_db) _db = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON);
  return _db;
}

const SORT_MAP = {
  paper_score: { col: 'paper_score',            asc: false },
  read_first:  { col: 'read_first_score',        asc: false },
  content:     { col: 'content_potential_score', asc: false },
  year:        { col: 'year',                    asc: false },
  citations:   { col: 'citations',               asc: false },
  title:       { col: 'title',                   asc: true  },
};

/**
 * Given a canonical tag name (e.g. "LLMs"), return all raw variants that
 * normalise to it so we can match any of them in Supabase.
 */
function _rawTagVariants(canonical, normalizeMap) {
  const variants = new Set([canonical]);
  for (const [raw, canon] of Object.entries(normalizeMap || {})) {
    if (canon === canonical) variants.add(raw);
  }
  return [...variants];
}

/**
 * Query papers from Supabase with server-side filtering & pagination.
 *
 * @param {object} opts
 * @returns {Promise<{data: object[], count: number, error: any}>}
 */
async function queryPapers({
  page       = 1,
  pageSize   = 25,
  search     = '',
  tag        = '',
  difficulty = '',
  type       = '',
  source     = '',
  year       = '',
  sortBy     = 'paper_score',
  tagNormalizeMap = {},
} = {}) {
  const db    = getDb();
  const start = (page - 1) * pageSize;
  const end   = start + pageSize - 1;
  const sort  = SORT_MAP[sortBy] || SORT_MAP.paper_score;

  let q = db.from('papers').select('*', { count: 'exact' });

  if (search) {
    // escape single quotes to prevent PostgREST injection
    const s = search.replace(/'/g, "''");
    q = q.or(`title.ilike.%${s}%,abstract.ilike.%${s}%`);
  }

  if (tag) {
    // Build OR of @> (contains) checks for all raw variants of the tag
    const variants = _rawTagVariants(tag, tagNormalizeMap);
    const orClause = variants.map(v => `tags.cs.${JSON.stringify([v])}`).join(',');
    q = q.or(orClause);
  }

  if (difficulty) q = q.eq('difficulty_level', difficulty);
  if (type)       q = q.eq('paper_type', type);
  if (source)     q = q.eq('source', source);
  if (year)       q = q.eq('year', parseInt(year, 10));

  q = q.order(sort.col, { ascending: sort.asc }).range(start, end);

  const { data, count, error } = await q;
  return { data: data || [], count: count || 0, error };
}

/**
 * Lightweight search for the global nav dropdown — returns up to `limit`
 * papers matching the query by title or abstract.
 */
async function searchPapersQuick(query, limit = 5) {
  if (!query || query.trim().length < 2) return [];
  const db = getDb();
  const q  = query.trim().replace(/'/g, "''");
  const { data } = await db
    .from('papers')
    .select('id,title,venue,year,paper_score,paper_url,tags,authors')
    .or(`title.ilike.%${q}%,abstract.ilike.%${q}%`)
    .order('paper_score', { ascending: false })
    .limit(limit);
  return data || [];
}

window._rs_supabase = { queryPapers, searchPapersQuick, getDb };
