const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const BRIDGE_SCHEMA_VERSION = 'local_mapping_bridge_v1';
const PROCESSOR_VERSION = 'range_library_local_edit_v1';
const ALLOWED_EDIT_KINDS = new Set(['structural_range', 'structural_event']);

function nowIso() {
  return new Date().toISOString();
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === 'object') {
    return Object.keys(value)
      .sort()
      .reduce((out, key) => {
        out[key] = canonicalize(value[key]);
        return out;
      }, {});
  }
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(canonicalize(value));
}

function normalizeEditRequest(request = {}) {
  const editKind = String(request.kind || '').trim();
  const editSource = String(request.source || '').trim();
  if (!ALLOWED_EDIT_KINDS.has(editKind)) {
    throw new Error(`local mapping bridge does not accept edit kind: ${editKind || 'missing'}`);
  }
  if (!editSource) {
    throw new Error('local mapping bridge requires edit source');
  }
  const envelope = {
    schema_version: BRIDGE_SCHEMA_VERSION,
    kind: editKind,
    source: editSource,
    payload: request.payload && typeof request.payload === 'object' ? request.payload : {},
    path_params: request.pathParams && typeof request.pathParams === 'object' ? request.pathParams : {},
  };
  const payloadJson = canonicalJson(envelope);
  const payloadSha256 = crypto.createHash('sha256').update(payloadJson).digest('hex');
  const editId = String(request.editId || `fxedit_${payloadSha256}`);
  return { editId, payloadJson, payloadSha256, envelope };
}

function ensureBridgeSchema(database) {
  database.exec(`
    CREATE TABLE IF NOT EXISTS local_mapping_edits (
      edit_id TEXT PRIMARY KEY,
      schema_version TEXT NOT NULL,
      edit_kind TEXT NOT NULL,
      edit_source TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      payload_sha256 TEXT NOT NULL,
      status TEXT NOT NULL,
      attempt_count INTEGER NOT NULL DEFAULT 0,
      created_at_utc TEXT NOT NULL,
      updated_at_utc TEXT NOT NULL,
      processing_started_at_utc TEXT,
      processed_at_utc TEXT,
      last_error TEXT,
      result_json TEXT,
      processor_version TEXT,
      python_database_path TEXT
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_local_mapping_edits_payload
      ON local_mapping_edits(payload_sha256);
    CREATE INDEX IF NOT EXISTS idx_local_mapping_edits_status
      ON local_mapping_edits(status, updated_at_utc);
  `);
}

function openDatabase(databasePath) {
  const resolved = path.resolve(databasePath);
  fs.mkdirSync(path.dirname(resolved), { recursive: true });
  const { DatabaseSync } = require('node:sqlite');
  const database = new DatabaseSync(resolved);
  database.exec('PRAGMA journal_mode = WAL');
  database.exec('PRAGMA synchronous = FULL');
  database.exec('PRAGMA busy_timeout = 60000');
  ensureBridgeSchema(database);
  return { database, databasePath: resolved };
}

function parseJsonOrNull(value) {
  if (!value) return null;
  try {
    return JSON.parse(String(value));
  } catch {
    return { raw: String(value) };
  }
}

function rowToPublicState(row, electronDatabasePath) {
  if (!row) return null;
  const rawStatus = String(row.status || 'PENDING').toUpperCase();
  const state = rawStatus === 'PROCESSED' ? 'SUCCESS' : rawStatus === 'FAILED' ? 'FAILED' : 'PENDING';
  const pythonDatabasePath = row.python_database_path ? path.resolve(String(row.python_database_path)) : null;
  const electronPath = path.resolve(electronDatabasePath);
  return {
    ok: state !== 'FAILED',
    saved: true,
    state,
    editId: String(row.edit_id),
    duplicate: false,
    attemptCount: Number(row.attempt_count || 0),
    databasePath: electronPath,
    electronDatabasePath: electronPath,
    pythonDatabasePath,
    sameDatabasePath: pythonDatabasePath ? pythonDatabasePath === electronPath : null,
    processorVersion: row.processor_version || null,
    error: row.last_error || undefined,
    result: parseJsonOrNull(row.result_json),
    createdAt: row.created_at_utc,
    updatedAt: row.updated_at_utc,
    processedAt: row.processed_at_utc || null,
  };
}

function createLocalMappingStore(options = {}) {
  if (!options.databasePath) throw new Error('databasePath is required');
  const opened = openDatabase(options.databasePath);
  const database = opened.database;
  const databasePath = opened.databasePath;
  let closed = false;

  function assertOpen() {
    if (closed) throw new Error('local mapping store is closed');
  }

  function readRow(editId) {
    assertOpen();
    return database.prepare('SELECT * FROM local_mapping_edits WHERE edit_id = ?').get(String(editId));
  }

  function save(request) {
    assertOpen();
    const normalized = normalizeEditRequest(request);
    const createdAt = nowIso();
    const result = database.prepare(`
      INSERT OR IGNORE INTO local_mapping_edits (
        edit_id, schema_version, edit_kind, edit_source,
        payload_json, payload_sha256, status,
        attempt_count, created_at_utc, updated_at_utc
      ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', 0, ?, ?)
    `).run(
      normalized.editId,
      BRIDGE_SCHEMA_VERSION,
      normalized.envelope.kind,
      normalized.envelope.source,
      normalized.payloadJson,
      normalized.payloadSha256,
      createdAt,
      createdAt,
    );
    const row = readRow(normalized.editId) || database.prepare(
      'SELECT * FROM local_mapping_edits WHERE payload_sha256 = ? ORDER BY created_at_utc LIMIT 1',
    ).get(normalized.payloadSha256);
    const state = rowToPublicState(row, databasePath);
    state.duplicate = Number(result.changes || 0) === 0;
    return state;
  }

  function markFailed(editId, error) {
    assertOpen();
    database.prepare(`
      UPDATE local_mapping_edits
      SET status = 'FAILED',
          last_error = ?,
          updated_at_utc = ?,
          processor_version = COALESCE(processor_version, ?),
          python_database_path = COALESCE(python_database_path, ?)
      WHERE edit_id = ?
        AND status != 'PROCESSED'
    `).run(String(error || 'Python processing failed'), nowIso(), PROCESSOR_VERSION, databasePath, String(editId));
    return getStatus(editId);
  }

  function markPending(editId) {
    assertOpen();
    database.prepare(`
      UPDATE local_mapping_edits
      SET status = 'PENDING',
          last_error = NULL,
          processing_started_at_utc = NULL,
          updated_at_utc = ?
      WHERE edit_id = ?
        AND status != 'PROCESSED'
    `).run(nowIso(), String(editId));
    return getStatus(editId);
  }

  function recoverInterrupted() {
    assertOpen();
    const recoveredAt = nowIso();
    const result = database.prepare(`
      UPDATE local_mapping_edits
      SET status = 'PENDING',
          last_error = 'Recovered after application restart while processing.',
          processing_started_at_utc = NULL,
          updated_at_utc = ?
      WHERE status = 'PROCESSING'
    `).run(recoveredAt);
    return Number(result.changes || 0);
  }

  function getStatus(editId) {
    assertOpen();
    return rowToPublicState(readRow(editId), databasePath);
  }

  function listPending(limit = 100) {
    assertOpen();
    const safeLimit = Math.max(1, Math.min(Number(limit) || 100, 1000));
    return database.prepare(`
      SELECT * FROM local_mapping_edits
      WHERE status = 'PENDING'
      ORDER BY created_at_utc ASC
      LIMIT ?
    `).all(safeLimit).map((row) => rowToPublicState(row, databasePath));
  }

  function count() {
    assertOpen();
    return Number(database.prepare('SELECT COUNT(*) AS n FROM local_mapping_edits').get()?.n || 0);
  }

  function close() {
    if (closed) return;
    database.close();
    closed = true;
  }

  return {
    databasePath,
    save,
    getStatus,
    markFailed,
    markPending,
    recoverInterrupted,
    listPending,
    count,
    close,
  };
}

function resolveRangeLibraryPythonRoot(explicit) {
  const candidates = [
    explicit,
    process.env.FXTM_RANGE_LIBRARY_PYTHON_ROOT,
    path.resolve(process.cwd(), '../python'),
    path.resolve(process.cwd(), 'python'),
    path.resolve(__dirname, '../../python'),
    process.resourcesPath,
  ].filter(Boolean);
  for (const candidate of candidates) {
    const root = path.resolve(String(candidate));
    if (fs.existsSync(path.join(root, 'range_library_memory', 'local_edit_bridge.py'))) return root;
  }
  return path.resolve(String(candidates[0] || path.resolve(process.cwd(), '../python')));
}

async function runPythonProcessor({ editId, databasePath, pythonRoot, pythonPath, spawnFn, timeoutMs }) {
  const { spawnLocalPythonScript } = require('./localPythonRunner.cjs');
  const root = resolveRangeLibraryPythonRoot(pythonRoot);
  const executable = pythonPath || process.env.FXTM_PYTHON || process.env.PYTHON || 'python';
  return spawnLocalPythonScript(
    {
      script: 'range_library_memory.local_edit_bridge',
      pythonPath: executable,
      args: [
        '-m',
        'range_library_memory.local_edit_bridge',
        'process',
        '--db-path',
        path.resolve(databasePath),
        '--edit-id',
        String(editId),
        '--json',
      ],
      cwd: root,
      env: {
        ...process.env,
        PYTHONPATH: root,
        PYTHONUNBUFFERED: '1',
        FXTM_RANGE_LIBRARY_MEMORY_DB: path.resolve(databasePath),
      },
    },
    { spawnFn, timeoutMs: timeoutMs || 60_000, parse: (stdout) => JSON.parse(String(stdout).trim()) },
  );
}

function createLocalMappingBridgeService(options = {}) {
  const store = createLocalMappingStore({ databasePath: options.databasePath });
  const processor = options.processor || runPythonProcessor;
  const inFlight = new Map();
  store.recoverInterrupted();

  async function processEdit(editId) {
    const key = String(editId);
    if (inFlight.has(key)) return inFlight.get(key);
    const promise = (async () => {
      const before = store.getStatus(key);
      if (!before) throw new Error(`local mapping edit not found: ${key}`);
      if (before.state === 'SUCCESS') return before;
      const result = await processor({
        editId: key,
        databasePath: store.databasePath,
        pythonRoot: options.pythonRoot,
        pythonPath: options.pythonPath,
        spawnFn: options.spawnFn,
        timeoutMs: options.timeoutMs,
      });
      if (!result?.ok) {
        return store.markFailed(key, result?.error || result?.stderr || 'Python processing failed');
      }
      const after = store.getStatus(key);
      if (!after || after.state === 'PENDING') {
        return store.markFailed(key, 'Python exited without completing the local edit state.');
      }
      return after;
    })().finally(() => inFlight.delete(key));
    inFlight.set(key, promise);
    return promise;
  }

  async function submit(request) {
    let saved;
    try {
      saved = store.save(request);
    } catch (err) {
      return {
        ok: false,
        saved: false,
        state: 'FAILED',
        databasePath: store.databasePath,
        electronDatabasePath: store.databasePath,
        pythonDatabasePath: null,
        sameDatabasePath: null,
        error: err?.message || String(err),
      };
    }
    if (saved.state === 'SUCCESS') return saved;
    return processEdit(saved.editId);
  }

  async function retry(editId) {
    const current = store.getStatus(editId);
    if (!current) return { ok: false, saved: false, state: 'FAILED', error: 'edit not found' };
    if (current.state === 'SUCCESS') return current;
    store.markPending(editId);
    return processEdit(editId);
  }

  async function resumePending(limit = 100) {
    const pending = store.listPending(limit);
    const results = [];
    for (const item of pending) results.push(await processEdit(item.editId));
    return { ok: true, resumed: results.length, results, databasePath: store.databasePath };
  }

  function getStatus(editId) {
    const state = store.getStatus(editId);
    return state || { ok: false, saved: false, state: 'FAILED', error: 'edit not found' };
  }

  return {
    store,
    submit,
    retry,
    resumePending,
    getStatus,
    getPaths: () => ({
      ok: true,
      databasePath: store.databasePath,
      electronDatabasePath: store.databasePath,
      rangeLibraryPythonRoot: resolveRangeLibraryPythonRoot(options.pythonRoot),
    }),
    close: () => store.close(),
  };
}

let defaultService = null;

function defaultRangeLibraryDatabasePath() {
  const { app } = require('electron');
  return path.join(app.getPath('documents'), 'FXTM_Research', 'range_library_memory.sqlite3');
}

function getDefaultService() {
  if (defaultService) return defaultService;
  defaultService = createLocalMappingBridgeService({ databasePath: defaultRangeLibraryDatabasePath() });
  return defaultService;
}

function registerLocalMappingBridgeIpc() {
  const { ipcMain, app } = require('electron');
  const service = getDefaultService();
  ipcMain.handle('local-mapping:submit', (_event, request) => service.submit(request || {}));
  ipcMain.handle('local-mapping:get-status', (_event, args) => service.getStatus(args?.editId));
  ipcMain.handle('local-mapping:retry', (_event, args) => service.retry(args?.editId));
  ipcMain.handle('local-mapping:get-paths', () => service.getPaths());
  ipcMain.handle('local-mapping:resume-pending', (_event, args) => service.resumePending(args?.limit));
  app.once('will-quit', closeLocalMappingBridge);
  setImmediate(() => {
    service.resumePending().catch((err) => {
      console.error(`[local-mapping] pending resume failed: ${err?.message || String(err)}`);
    });
  });
}

function closeLocalMappingBridge() {
  if (!defaultService) return;
  defaultService.close();
  defaultService = null;
}

module.exports = {
  BRIDGE_SCHEMA_VERSION,
  PROCESSOR_VERSION,
  canonicalJson,
  normalizeEditRequest,
  createLocalMappingStore,
  createLocalMappingBridgeService,
  resolveRangeLibraryPythonRoot,
  defaultRangeLibraryDatabasePath,
  runPythonProcessor,
  registerLocalMappingBridgeIpc,
  closeLocalMappingBridge,
};
