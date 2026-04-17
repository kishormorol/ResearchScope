const test = require('node:test');
const assert = require('node:assert/strict');

const library = require('../../site/assets/js/library.js');

function createStorage(initialValue) {
  const state = new Map();

  if (typeof initialValue !== 'undefined') {
    state.set(library.STORAGE_KEY, initialValue);
  }

  return {
    getItem(key) {
      return state.has(key) ? state.get(key) : null;
    },
    setItem(key, value) {
      state.set(key, String(value));
    },
    removeItem(key) {
      state.delete(key);
    },
    dump() {
      return state.get(library.STORAGE_KEY) || null;
    },
  };
}

function createFailingStorage(options) {
  const settings = options || {};
  const state = new Map();

  if (typeof settings.initialValue !== 'undefined') {
    state.set(library.STORAGE_KEY, settings.initialValue);
  }

  return {
    getItem(key) {
      return state.has(key) ? state.get(key) : null;
    },
    setItem(key, value) {
      if (settings.failSet) throw new Error('set failed');
      state.set(key, String(value));
    },
    removeItem(key) {
      if (settings.failRemove) throw new Error('remove failed');
      state.delete(key);
    },
    dump() {
      return state.get(library.STORAGE_KEY) || null;
    },
  };
}

test('readLibraryIds hydrates saved ids and ignores malformed payloads', () => {
  const savedStorage = createStorage(JSON.stringify(['paper-1', 'paper-2']));
  assert.deepEqual(library.readLibraryIds(savedStorage), ['paper-1', 'paper-2']);

  const malformedStorage = createStorage('{bad json');
  assert.deepEqual(library.readLibraryIds(malformedStorage), []);
});

test('writeLibraryIds normalizes duplicates while preserving first-in order', () => {
  const storage = createStorage();
  const ids = library.writeLibraryIds(['paper-1', 'paper-2', 'paper-1', '', 'paper-3'], storage);

  assert.deepEqual(ids, ['paper-1', 'paper-2', 'paper-3']);
  assert.equal(storage.dump(), JSON.stringify(['paper-1', 'paper-2', 'paper-3']));
});

test('toggleLibraryItem follows FIFO semantics for add, remove, and re-add', () => {
  const storage = createStorage();

  assert.deepEqual(library.toggleLibraryItem('paper-1', storage), {
    ids: ['paper-1'],
    inLibrary: true,
    changed: true,
  });
  assert.deepEqual(library.toggleLibraryItem('paper-2', storage), {
    ids: ['paper-1', 'paper-2'],
    inLibrary: true,
    changed: true,
  });
  assert.deepEqual(library.toggleLibraryItem('paper-1', storage), {
    ids: ['paper-2'],
    inLibrary: false,
    changed: true,
  });
  assert.deepEqual(library.toggleLibraryItem('paper-1', storage), {
    ids: ['paper-2', 'paper-1'],
    inLibrary: true,
    changed: true,
  });
});

test('toggleLibraryItem reports no change when add persistence fails', () => {
  const storage = createFailingStorage({ failSet: true });

  assert.deepEqual(library.toggleLibraryItem('paper-1', storage), {
    ids: [],
    inLibrary: false,
    changed: false,
  });
  assert.equal(storage.dump(), null);
});

test('removeFromLibrary preserves persisted ids when removal fails', () => {
  const storage = createFailingStorage({
    initialValue: JSON.stringify(['paper-1']),
    failRemove: true,
  });

  assert.deepEqual(library.removeFromLibrary('paper-1', storage), {
    ids: ['paper-1'],
    inLibrary: true,
    changed: false,
  });
  assert.equal(storage.dump(), JSON.stringify(['paper-1']));
});

test('getLibraryPapers returns papers in stored library order and ignores missing ids', () => {
  const papers = [
    { id: 'paper-3', title: 'Paper 3' },
    { id: 'paper-1', title: 'Paper 1' },
    { id: 'paper-2', title: 'Paper 2' },
  ];

  const ordered = library.getLibraryPapers(papers, ['paper-2', 'missing', 'paper-1']);
  assert.deepEqual(
    ordered.map((paper) => paper.id),
    ['paper-2', 'paper-1']
  );
});

test('paper objects hydrate library ids through the shared id resolver', () => {
  const storage = createStorage();
  const paper = { id: 'paper-9', title: 'Paper 9' };

  library.addToLibrary(paper, storage);

  assert.equal(library.isInLibrary('paper-9', storage), true);
  assert.equal(library.isInLibrary(paper, storage), true);
  assert.deepEqual(library.readLibraryIds(storage), ['paper-9']);
});
