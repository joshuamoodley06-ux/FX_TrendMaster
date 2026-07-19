const fs = require('fs');
const path = require('path');
const fsp = fs.promises;
const { ipcMain, app, dialog, shell } = require('electron');
const {
  runHistoricalRangeScan,
  runBatchRangePromote,
  runDetectorPerformance,
  runDetectorLocal,
  listDetectorSuggestionsLocal,
  latestDetectorRunLocal,
  listDetectorRunLocal,
  reviewSuggestionLocal,
  exportDetectionAuditLocal,
  runRandomRangeAudit,
  runRecordAuditVerdict,
  runPullVpsCandles,
  runLocalResearchSeed,
  resolveBackendDir,
  spawnLocalPythonScript,
} = require('./localPythonRunner.cjs');
const {
  defaultDatabasePath,
  ensureResearchFolder,
  researchFolder,
  resolveActiveDatabasePath,
  writeResearchSettings,
} = require('./localResearchSettings.cjs');
const { inspectDatabaseFile } = require('./localResearchDatabase.cjs');
const { cacheDbPath } = require('./candleCache.cjs');

let localResearchBusy = false;
const weeklyAnalysisCopies = new Set();

function buildDatabaseStatus(options = {}) {
  const databasePath = resolveActiveDatabasePath(options.databasePath);
  const folder = ensureResearchFolder();
  const inspected = inspectDatabaseFile(databasePath, {
    symbol: options.symbol,
    timeframe: options.timeframe,
  });
  return {
    ok: true,
    researchFolder: folder,
    defaultDatabasePath: defaultDatabasePath(),
    ...inspected,
  };
}

function normalizeRunnerArgs(args) {
  const payload = args && typeof args === 'object' ? { ...args } : {};
  payload.databasePath = resolveActiveDatabasePath(payload.databasePath);
  if (!payload.backendDir) {
    payload.backendDir = resolveBackendDir();
  }
  return payload;
}

function validateBatchPromoteArgs(args) {
  if (args?.confirm && !args?.userConfirmed) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: 'batch promote --confirm requires userConfirmed: true from renderer',
    };
  }
  return null;
}

async function runExclusive(taskName, runner) {
  if (localResearchBusy) {
    return {
      ok: false,
      exitCode: null,
      stdout: '',
      stderr: '',
      error: `local research busy (${taskName}); wait for the current job to finish`,
    };
  }
  localResearchBusy = true;
  try {
    return await runner();
  } finally {
    localResearchBusy = false;
  }
}

function resolveRangeLibraryPythonRoot(explicit) {
  const candidates = [
    explicit,
    process.env.FXTM_RANGE_LIBRARY_PYTHON_ROOT,
    path.resolve(process.cwd(), '../python'),
    path.resolve(process.cwd(), 'python'),
    path.resolve(__dirname, '../../python'),
    path.resolve(__dirname, '../../../python'),
    process.resourcesPath,
  ].filter(Boolean);
  for (const candidate of candidates) {
    const root = path.resolve(String(candidate));
    if (fs.existsSync(path.join(root, 'range_library_memory', 'xauusd_mapping_assistant.py'))) {
      return root;
    }
  }
  return path.resolve(String(candidates[0] || path.resolve(process.cwd(), '../python')));
}

function buildMappingAssistantSpec(args = {}) {
  const databasePath = String(args.databasePath || '').trim();
  if (!databasePath) throw new Error('Mapping Assistant requires an explicit Range Library database path.');
  const absoluteDatabasePath = path.resolve(databasePath);
  const pythonRoot = resolveRangeLibraryPythonRoot(args.pythonRoot);
  const pythonPath = args.pythonPath || process.env.FXTM_PYTHON || process.env.PYTHON || 'python';
  return {
    script: 'range_library_memory.xauusd_mapping_assistant',
    pythonPath,
    args: [
      '-m',
      'range_library_memory.xauusd_mapping_assistant',
      '--db-path', absoluteDatabasePath,
      '--symbol', 'XAUUSD',
      '--json',
    ],
    cwd: pythonRoot,
    env: {
      ...process.env,
      PYTHONPATH: pythonRoot,
      PYTHONUNBUFFERED: '1',
      FXTM_RANGE_LIBRARY_MEMORY_DB: absoluteDatabasePath,
    },
  };
}

function runMappingAssistant(args = {}) {
  const spec = buildMappingAssistantSpec(args);
  return spawnLocalPythonScript(spec, {
    timeoutMs: args.timeoutMs || 120_000,
  });
}

function buildWeeklyScript1Spec(args = {}) {
  const candleDatabasePath = path.resolve(String(args.candleDatabasePath || ''));
  const analysisDatabasePath = path.resolve(String(args.analysisDatabasePath || ''));
  const caseRef = String(args.caseRef || '').trim();
  const symbol = String(args.symbol || '').trim().toUpperCase();
  if (!args.candleDatabasePath || !args.analysisDatabasePath || !caseRef || !symbol) {
    throw new Error('Weekly Script 1 requires explicit candle, disposable database, case, and symbol inputs.');
  }
  if (candleDatabasePath === analysisDatabasePath) {
    throw new Error('Weekly Script 1 refuses to use the candle database as its write target.');
  }
  const pythonRoot = resolveRangeLibraryPythonRoot(args.pythonRoot);
  return {
    script: 'range_library_memory.cli',
    pythonPath: args.pythonPath || process.env.FXTM_PYTHON || process.env.PYTHON || 'python',
    args: ['-m', 'range_library_memory.cli', 'build-weekly-script1',
      '--db-path', analysisDatabasePath, '--source-db', candleDatabasePath,
      '--case-ref', caseRef, '--symbol', symbol, '--json'],
    cwd: pythonRoot,
    env: { ...process.env, PYTHONPATH: pythonRoot, PYTHONUNBUFFERED: '1',
      FXTM_RANGE_LIBRARY_MEMORY_DB: analysisDatabasePath },
  };
}

function buildWeeklyMasterMapSpec(args = {}) {
  const analysisDatabasePath = path.resolve(String(args.analysisDatabasePath || ''));
  const outputPath = path.resolve(String(args.outputPath || ''));
  if (!args.analysisDatabasePath || !args.outputPath) {
    throw new Error('Weekly Script 1 Master Map refresh requires disposable database and output paths.');
  }
  const pythonRoot = resolveRangeLibraryPythonRoot(args.pythonRoot);
  return {
    script: 'range_library_memory.master_map',
    pythonPath: args.pythonPath || process.env.FXTM_PYTHON || process.env.PYTHON || 'python',
    args: ['-m', 'range_library_memory.master_map', '--db-path', analysisDatabasePath,
      '--symbol', String(args.symbol || 'XAUUSD').toUpperCase(), '--output', outputPath, '--json'],
    cwd: pythonRoot,
    env: { ...process.env, PYTHONPATH: pythonRoot, PYTHONUNBUFFERED: '1',
      FXTM_RANGE_LIBRARY_MEMORY_DB: analysisDatabasePath },
  };
}

function buildWeeklyScript1ReviewSpec(args = {}) {
  const analysisDatabasePath = path.resolve(String(args.analysisDatabasePath || ''));
  const runId = String(args.runId || '').trim();
  const caseRef = String(args.caseRef || '').trim();
  const symbol = String(args.symbol || '').trim().toUpperCase();
  const canonicalRangeId = String(args.canonicalRangeId || '').trim();
  const decision = String(args.decision || '').trim().toUpperCase();
  if (!args.analysisDatabasePath || !runId || !caseRef || !symbol) {
    throw new Error('Weekly Script 1 review requires the analysis copy, run identity, case, and symbol.');
  }
  if (!canonicalRangeId || !['APPROVED', 'REJECTED'].includes(decision)) {
    throw new Error('Weekly Script 1 sample decision is invalid.');
  }
  const pythonRoot = resolveRangeLibraryPythonRoot(args.pythonRoot);
  return {
    script: 'range_library_memory.cli',
    pythonPath: args.pythonPath || process.env.FXTM_PYTHON || process.env.PYTHON || 'python',
    args: ['-m', 'range_library_memory.cli', 'review-weekly-script1',
      '--db-path', analysisDatabasePath, '--run-id', runId,
      '--case-ref', caseRef, '--symbol', symbol, '--canonical-range-id', canonicalRangeId,
      '--decision', decision, '--json'],
    cwd: pythonRoot,
    env: { ...process.env, PYTHONPATH: pythonRoot, PYTHONUNBUFFERED: '1',
      FXTM_RANGE_LIBRARY_MEMORY_DB: analysisDatabasePath },
  };
}

function tableNames(database) {
  return new Set(database.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map((row) => String(row.name)));
}

function preflightWeeklyAnalysis({ candleDatabasePath, analysisDatabasePath, caseRef, symbol }) {
  const { DatabaseSync } = require('node:sqlite');
  const candle = new DatabaseSync(candleDatabasePath, { readOnly: true });
  try {
    if (!tableNames(candle).has('candles')) throw new Error('CANDLE_SOURCE_INVALID');
    const candleCount = Number(candle.prepare(
      'SELECT COUNT(*) AS count FROM candles WHERE UPPER(symbol)=? AND UPPER(timeframe)=?'
    ).get(symbol, 'W1')?.count || 0);
    if (candleCount < 1) throw new Error('CANDLE_SCOPE_EMPTY');
  } finally { candle.close(); }

  const rangeLibrary = new DatabaseSync(analysisDatabasePath, { readOnly: true });
  try {
    const names = tableNames(rangeLibrary);
    for (const required of ['raw_ranges', 'raw_events', 'master_map_ranges', 'master_map_outputs']) {
      if (!names.has(required)) throw new Error(`RANGE_LIBRARY_CONTRACT_MISSING:${required}`);
    }
    const row = rangeLibrary.prepare('SELECT output_json FROM master_map_outputs WHERE UPPER(symbol)=?').get(symbol);
    if (!row) throw new Error('MASTER_MAP_SCOPE_MISSING');
    const output = JSON.parse(String(row.output_json));
    const roots = [output.trusted_root, output.review_root].filter(Boolean);
    const stack = [...roots];
    let weeklyCount = 0;
    while (stack.length) {
      const node = stack.pop();
      if (!node || typeof node !== 'object') continue;
      if (String(node.structure_layer || '').toUpperCase() === 'WEEKLY'
        && Array.isArray(node.source_refs)
        && node.source_refs.some((ref) => String(ref?.case_ref || '') === caseRef)) weeklyCount += 1;
      if (Array.isArray(node.children)) stack.push(...node.children);
    }
    if (!weeklyCount) throw new Error('SELECTED_CASE_HAS_NO_WEEKLY_RANGES');
  } finally { rangeLibrary.close(); }
}

async function createDisposableAnalysisCopy(sourcePath, targetPath) {
  const source = path.resolve(sourcePath);
  const target = path.resolve(targetPath);
  if (source === target) throw new Error('Disposable analysis copy cannot be the live database.');
  await fsp.mkdir(path.dirname(target), { recursive: true });
  const { DatabaseSync, backup } = require('node:sqlite');
  const database = new DatabaseSync(source, { readOnly: true });
  try {
    await backup(database, target);
  } finally {
    database.close();
  }
  return target;
}

function weeklyAnalysisPaths(liveDatabasePath, caseRef, symbol, analysisRoot) {
  const root = analysisRoot || path.join(researchFolder(), 'analysis-copies', 'weekly-script1');
  const scopeId = require('node:crypto').createHash('sha256')
    .update(`${path.resolve(liveDatabasePath)}|${caseRef}|${symbol}`).digest('hex').slice(0, 20);
  return { analysisDatabasePath: path.join(root, `${scopeId}.sqlite3`),
    outputPath: path.join(root, `${scopeId}.master-map.json`) };
}

async function runWeeklyScript1Activation(args = {}, dependencies = {}) {
  const liveDatabasePath = path.resolve(String(args.databasePath || ''));
  const candleDatabasePath = path.resolve(String(args.candleDatabasePath || cacheDbPath()));
  const caseRef = String(args.caseRef || '').trim();
  const symbol = String(args.symbol || '').trim().toUpperCase();
  if (!args.databasePath || !fs.existsSync(liveDatabasePath)) {
    throw new Error(`Range Library database does not exist: ${liveDatabasePath}`);
  }
  if (!caseRef || !symbol) throw new Error('Selected case and symbol are required.');
  if (!fs.existsSync(candleDatabasePath)) throw new Error('CANDLE_SOURCE_UNRESOLVED');
  if (candleDatabasePath === liveDatabasePath) throw new Error('CANDLE_AND_RANGE_LIBRARY_MUST_BE_SEPARATE');
  const analysisRoot = args.analysisRoot
    ? path.resolve(String(args.analysisRoot))
    : path.join(researchFolder(), 'analysis-copies', 'weekly-script1');
  const { analysisDatabasePath, outputPath } = weeklyAnalysisPaths(liveDatabasePath, caseRef, symbol, analysisRoot);
  const copyDatabase = dependencies.copyDatabase || createDisposableAnalysisCopy;
  const runScript = dependencies.runScript || spawnLocalPythonScript;
  const preflight = dependencies.preflight || preflightWeeklyAnalysis;
  if (!fs.existsSync(analysisDatabasePath)) await copyDatabase(liveDatabasePath, analysisDatabasePath);
  preflight({ candleDatabasePath, analysisDatabasePath, caseRef, symbol });
  const common = { candleDatabasePath, analysisDatabasePath, caseRef, symbol, pythonPath: args.pythonPath, pythonRoot: args.pythonRoot };
  weeklyAnalysisCopies.add(path.resolve(analysisDatabasePath));
  const pythonRoot = resolveRangeLibraryPythonRoot(args.pythonRoot);
  const inserted = await runDoctrineCommand('insert-script', { ...common,
    scriptKey: 'weekly_structure', displayName: 'Weekly Script 1', versionLabel: '1',
    sourceFile: path.join(pythonRoot, 'range_library_memory', 'weekly_chronology_bos.py'),
    adapterKey: 'weekly_chronology_bos_v1', executionOrder: 10,
  }, { runScript });
  const doctrineState = await runDoctrineCommand('run-doctrine-pipeline', { ...common,
    versionId: inserted.result.version_id,
  }, { runScript });
  const mapResult = await runScript(buildWeeklyMasterMapSpec({ ...common, outputPath }), {
    timeoutMs: args.timeoutMs || 180_000,
    parse: (stdout) => JSON.parse(String(stdout).trim()),
  });
  if (!mapResult?.ok || !mapResult?.parsed) {
    throw new Error(mapResult?.error || mapResult?.stderr || 'Disposable Master Map refresh failed.');
  }
  return { ok: true, source: 'DISPOSABLE_ANALYSIS_COPY', liveDatabasePath, candleDatabasePath,
    analysisDatabasePath, masterMap: mapResult.parsed, doctrineState: doctrineState.result };
}

async function loadWeeklyScript1State(args = {}, dependencies = {}) {
  const liveDatabasePath = path.resolve(String(args.databasePath || ''));
  const caseRef = String(args.caseRef || '').trim();
  const symbol = String(args.symbol || '').trim().toUpperCase();
  if (!liveDatabasePath || !caseRef || !symbol) return { ok: false, source: 'LIVE' };
  const analysisRoot = args.analysisRoot ? path.resolve(String(args.analysisRoot))
    : path.join(researchFolder(), 'analysis-copies', 'weekly-script1');
  const { analysisDatabasePath, outputPath } = weeklyAnalysisPaths(liveDatabasePath, caseRef, symbol, analysisRoot);
  if (!fs.existsSync(analysisDatabasePath)) return { ok: false, source: 'LIVE' };
  const runScript = dependencies.runScript || spawnLocalPythonScript;
  const mapResult = await runScript(buildWeeklyMasterMapSpec({ analysisDatabasePath, outputPath, symbol,
    pythonPath: args.pythonPath, pythonRoot: args.pythonRoot }), {
    timeoutMs: args.timeoutMs || 180_000, parse: (stdout) => JSON.parse(String(stdout).trim()),
  });
  if (!mapResult?.ok || !mapResult?.parsed) return { ok: false, source: 'LIVE' };
  weeklyAnalysisCopies.add(path.resolve(analysisDatabasePath));
  let doctrineState = null;
  try { doctrineState = (await runDoctrineCommand('show-script', { analysisDatabasePath, scriptKey: 'weekly_structure',
    pythonPath: args.pythonPath, pythonRoot: args.pythonRoot }, { runScript })).result; } catch { /* legacy copy */ }
  return { ok: true, source: 'DISPOSABLE_ANALYSIS_COPY', liveDatabasePath,
    analysisDatabasePath, masterMap: mapResult.parsed, doctrineState };
}

async function runWeeklyScript1Review(args = {}, dependencies = {}) {
  const analysisDatabasePath = path.resolve(String(args.analysisDatabasePath || ''));
  const liveDatabasePath = path.resolve(String(args.liveDatabasePath || ''));
  const allowedCopies = dependencies.allowedCopies || weeklyAnalysisCopies;
  if (!args.analysisDatabasePath || !allowedCopies.has(analysisDatabasePath)) {
    throw new Error('ANALYSIS_COPY_UNAVAILABLE');
  }
  if (args.liveDatabasePath && analysisDatabasePath === liveDatabasePath) {
    throw new Error('LIVE_RANGE_LIBRARY_WRITE_BLOCKED');
  }
  const runScript = dependencies.runScript || spawnLocalPythonScript;
  const common = { ...args, analysisDatabasePath };
  const reviewResult = await runDoctrineCommand('review-doctrine-sample', { ...common,
    runId: args.runId, canonicalRangeId: args.canonicalRangeId, decision: args.decision,
  }, { runScript, allowedCopies });
  const outputPath = path.join(path.dirname(analysisDatabasePath), `${path.basename(analysisDatabasePath, path.extname(analysisDatabasePath))}.master-map.json`);
  const mapResult = await runScript(buildWeeklyMasterMapSpec({ ...common, outputPath }), {
    timeoutMs: args.timeoutMs || 180_000,
    parse: (stdout) => JSON.parse(String(stdout).trim()),
  });
  if (!mapResult?.ok || !mapResult?.parsed) throw new Error('SCRIPT1_REVIEW_REFRESH_FAILED');
  const stored = await runDoctrineCommand('show-script', { ...common, scriptKey: 'weekly_structure' }, { runScript, allowedCopies });
  return { ok: true, source: 'DISPOSABLE_ANALYSIS_COPY', analysisDatabasePath,
    decision: String(args.decision || '').toUpperCase(), doctrineState: stored.result, masterMap: mapResult.parsed };
}

function buildDoctrineSpec(command, args = {}, allowedCopies = weeklyAnalysisCopies) {
  const databasePath = path.resolve(String(args.analysisDatabasePath || ''));
  if (!args.analysisDatabasePath || !allowedCopies.has(databasePath)) {
    throw new Error('ANALYSIS_COPY_UNAVAILABLE');
  }
  const pythonRoot = resolveRangeLibraryPythonRoot(args.pythonRoot);
  const cliArgs = ['-m', 'range_library_memory.cli', command, '--db-path', databasePath];
  const add = (flag, value) => { if (value !== undefined && value !== null && String(value) !== '') cliArgs.push(flag, String(value)); };
  if (command === 'insert-script') {
    add('--script-key', args.scriptKey); add('--display-name', args.displayName);
    add('--version-label', args.versionLabel); add('--source-file', args.sourceFile);
    add('--adapter-key', args.adapterKey); add('--execution-order', args.executionOrder ?? 100);
    add('--description', args.description);
  } else if (command === 'show-script' || command === 'retire-script') add('--script-key', args.scriptKey);
  else if (command === 'run-doctrine-pipeline') {
    add('--source-db', args.candleDatabasePath || cacheDbPath()); add('--case-ref', args.caseRef);
    add('--symbol', args.symbol); add('--version-id', args.versionId);
  } else if (command === 'review-doctrine-sample') {
    add('--run-id', args.runId); add('--canonical-range-id', args.canonicalRangeId); add('--decision', args.decision);
  }
  return { script: 'range_library_memory.cli', pythonPath: args.pythonPath || process.env.FXTM_PYTHON || process.env.PYTHON || 'python',
    args: cliArgs, cwd: pythonRoot, env: { ...process.env, PYTHONPATH: pythonRoot, PYTHONUNBUFFERED: '1', FXTM_RANGE_LIBRARY_MEMORY_DB: databasePath } };
}

async function runDoctrineCommand(command, args = {}, dependencies = {}) {
  const runScript = dependencies.runScript || spawnLocalPythonScript;
  const result = await runScript(buildDoctrineSpec(command, args, dependencies.allowedCopies || weeklyAnalysisCopies), {
    timeoutMs: args.timeoutMs || 180_000, parse: (stdout) => JSON.parse(String(stdout).trim()),
  });
  if (!result?.ok || result.parsed === undefined) throw new Error('DOCTRINE_COMMAND_FAILED');
  return { ok: true, result: result.parsed };
}

function registerLocalResearchIpc() {
  ensureResearchFolder();

  ipcMain.handle('local-research:getDatabaseStatus', async (_event, args) => {
    try {
      return buildDatabaseStatus(args || {});
    } catch (err) {
      return {
        ok: false,
        databasePath: defaultDatabasePath(),
        researchFolder: researchFolder(),
        exists: false,
        readable: false,
        readyForWeeklyScan: false,
        error: err?.message || String(err),
      };
    }
  });

  ipcMain.handle('local-research:pickDatabaseFile', async () => {
    const result = await dialog.showOpenDialog({
      title: 'Choose local research database',
      properties: ['openFile'],
      filters: [
        { name: 'SQLite database', extensions: ['db', 'sqlite', 'sqlite3'] },
        { name: 'All files', extensions: ['*'] },
      ],
      defaultPath: researchFolder(),
    });
    if (result.canceled || !result.filePaths?.length) {
      return { ok: false, canceled: true };
    }
    const databasePath = result.filePaths[0];
    writeResearchSettings({ databasePath });
    return {
      ok: true,
      canceled: false,
      ...buildDatabaseStatus({ databasePath }),
    };
  });

  ipcMain.handle('local-research:setDatabasePath', async (_event, args) => {
    const databasePath = String(args?.databasePath || '').trim();
    if (!databasePath) {
      return { ok: false, error: 'databasePath is required' };
    }
    writeResearchSettings({ databasePath });
    return {
      ok: true,
      ...buildDatabaseStatus({ databasePath }),
    };
  });

  ipcMain.handle('local-research:openResearchFolder', async () => {
    const folder = ensureResearchFolder();
    const err = await shell.openPath(folder);
    return { ok: !err, folder, error: err || undefined };
  });

  ipcMain.handle('local-research:pull-vps-candles', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    const result = await runExclusive('pull-vps-candles', () => runPullVpsCandles({
      ...payload,
      baseUrl: payload.baseUrl,
      symbol: payload.symbol,
      timeframes: payload.timeframes,
      limit: payload.limit,
      json: payload.json !== false,
      timeoutMs: 180_000,
    }));
    if (result.ok) {
      writeResearchSettings({ databasePath: payload.databasePath });
    }
    return result;
  });

  ipcMain.handle('local-research:seed', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    if (!payload?.command) {
      return {
        ok: false,
        exitCode: null,
        stdout: '',
        stderr: '',
        error: 'command is required (check, list, create-manual, activate)',
      };
    }
    return runExclusive('local-research-seed', () => runLocalResearchSeed({
      ...payload,
      command: payload.command,
      symbol: payload.symbol,
      rangeHigh: payload.rangeHigh,
      rangeLow: payload.rangeLow,
      rangeHighTime: payload.rangeHighTime,
      rangeLowTime: payload.rangeLowTime,
      rangeId: payload.rangeId,
      limit: payload.limit,
      json: payload.json !== false,
      timeoutMs: 60_000,
    }));
  });

  ipcMain.handle('local-research:historical-range-scan', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    return runExclusive('historical-range-scan', () => runHistoricalRangeScan(payload));
  });

  ipcMain.handle('local-research:batch-range-promote', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    const blocked = validateBatchPromoteArgs(payload);
    if (blocked) return blocked;
    return runExclusive('batch-range-promote', () => runBatchRangePromote(payload));
  });

  ipcMain.handle('local-research:detector-performance', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    return runExclusive('detector-performance', () => runDetectorPerformance(payload));
  });

  ipcMain.handle('local-research:run-detector', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    if (!payload?.payload || typeof payload.payload !== 'object') {
      return {
        ok: false,
        exitCode: null,
        stdout: '',
        stderr: '',
        error: 'payload object is required',
      };
    }
    return runExclusive('run-detector', () => runDetectorLocal(payload));
  });

  ipcMain.handle('local-research:list-suggestions', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    return runExclusive('list-suggestions', () => listDetectorSuggestionsLocal(payload));
  });

  ipcMain.handle('local-research:latest-detector-run', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    return runExclusive('latest-detector-run', () => latestDetectorRunLocal(payload));
  });

  ipcMain.handle('local-research:list-detector-run', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    if (!payload?.detectionRunId) {
      return {
        ok: false,
        exitCode: null,
        stdout: '',
        stderr: '',
        error: 'detectionRunId is required',
      };
    }
    return runExclusive('list-detector-run', () => listDetectorRunLocal(payload));
  });

  ipcMain.handle('local-research:review-suggestion', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    if (!payload?.suggestionId || !payload?.action) {
      return {
        ok: false,
        exitCode: null,
        stdout: '',
        stderr: '',
        error: 'suggestionId and action are required',
      };
    }
    return runExclusive('review-suggestion', () => reviewSuggestionLocal(payload));
  });

  ipcMain.handle('local-research:export-detection-audit', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    if (!payload?.detectionRunId) {
      return {
        ok: false,
        exitCode: null,
        stdout: '',
        stderr: '',
        error: 'detectionRunId is required',
      };
    }
    return runExclusive('export-detection-audit', () => exportDetectionAuditLocal(payload));
  });

  ipcMain.handle('local-research:random-range-audit', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    return runExclusive('random-range-audit', () => runRandomRangeAudit(payload));
  });

  ipcMain.handle('local-research:record-audit-verdict', async (_event, args) => {
    const payload = normalizeRunnerArgs(args);
    if (!payload?.suggestionId) {
      return {
        ok: false,
        exitCode: null,
        stdout: '',
        stderr: '',
        error: 'suggestionId is required',
      };
    }
    return runExclusive('record-audit-verdict', () => runRecordAuditVerdict(payload));
  });

  ipcMain.handle('local-research:mapping-assistant', async (_event, args) => {
    const databasePath = String(args?.databasePath || '').trim();
    if (!databasePath) {
      return {
        ok: false,
        exitCode: null,
        stdout: '',
        stderr: '',
        error: 'Mapping Assistant requires an explicit Range Library database path.',
      };
    }
    return runExclusive('mapping-assistant', () => runMappingAssistant({
      databasePath,
      pythonPath: args?.pythonPath,
      pythonRoot: args?.pythonRoot,
      timeoutMs: args?.timeoutMs,
    }));
  });

  ipcMain.handle('local-research:weekly-script1', async (_event, args) => {
    try {
      return await runExclusive('weekly-script1', () => runWeeklyScript1Activation(args || {}));
    } catch (err) {
      console.error(`[weekly-script1] ${err?.stack || err?.message || String(err)}`);
      const detail = String(err?.message || err || '');
      const error = detail.includes('CANDLE') || /candles table/i.test(detail)
        ? 'Weekly analysis could not start because the candle source database was not resolved.'
        : detail.includes('SELECTED_CASE') ? 'The selected case has no Weekly records available for analysis.'
        : detail.includes('case and symbol') ? 'Select a case before running Weekly analysis.'
        : 'Weekly analysis could not start. Technical details were written to the Electron log.';
      return { ok: false, source: 'LIVE', error };
    }
  });

  ipcMain.handle('local-research:weekly-script1-state', async (_event, args) => {
    try { return await loadWeeklyScript1State(args || {}); }
    catch (err) {
      console.error(`[weekly-script1-state] ${err?.stack || err?.message || String(err)}`);
      return { ok: false, source: 'LIVE' };
    }
  });

  ipcMain.handle('local-research:weekly-script1-review', async (_event, args) => {
    try {
      return await runExclusive('weekly-script1-review', () => runWeeklyScript1Review(args || {}));
    } catch (err) {
      console.error(`[weekly-script1-review] ${err?.stack || err?.message || String(err)}`);
      return { ok: false, source: 'DISPOSABLE_ANALYSIS_COPY',
        error: 'The Weekly analysis review could not be saved safely.' };
    }
  });

  ipcMain.handle('local-research:doctrine-list', async (_event, args) => {
    try { return await runDoctrineCommand('list-scripts', args || {}); }
    catch (err) { console.error(`[doctrine-list] ${err?.stack || err}`); return { ok: false, error: 'Stored scripts could not be loaded.' }; }
  });
  ipcMain.handle('local-research:doctrine-insert', async (_event, args) => {
    try {
      const picked = args?.sourceFile ? { canceled: false, filePaths: [args.sourceFile] } : await dialog.showOpenDialog({
        title: 'Insert Doctrine Script', properties: ['openFile'], filters: [{ name: 'Doctrine packages', extensions: ['py', 'json'] }],
      });
      if (picked.canceled || !picked.filePaths[0]) return { ok: false, canceled: true };
      return await runDoctrineCommand('insert-script', { ...(args || {}), sourceFile: picked.filePaths[0] });
    } catch (err) { console.error(`[doctrine-insert] ${err?.stack || err}`); return { ok: false, error: 'The doctrine package could not be stored safely.' }; }
  });
  ipcMain.handle('local-research:doctrine-run', async (_event, args) => {
    try { return await runExclusive('doctrine-run', () => runDoctrineCommand('run-doctrine-pipeline', args || {})); }
    catch (err) { console.error(`[doctrine-run] ${err?.stack || err}`); return { ok: false, error: 'The doctrine pipeline could not run safely.' }; }
  });
  ipcMain.handle('local-research:doctrine-review', async (_event, args) => {
    try { return await runExclusive('doctrine-review', () => runDoctrineCommand('review-doctrine-sample', args || {})); }
    catch (err) { console.error(`[doctrine-review] ${err?.stack || err}`); return { ok: false, error: 'The validation decision could not be stored safely.' }; }
  });

  ipcMain.handle('local-research:getPaths', () => {
    const databasePath = resolveActiveDatabasePath();
    return {
      ok: true,
      backendDir: resolveBackendDir(),
      databasePath,
      researchFolder: researchFolder(),
      scripts: {
        historicalRangeScan: path.join(resolveBackendDir(), 'historical_range_scan.py'),
        batchRangePromote: path.join(resolveBackendDir(), 'batch_range_promote.py'),
        detectorPerformance: path.join(resolveBackendDir(), 'detector_performance.py'),
        randomRangeAudit: path.join(resolveBackendDir(), 'random_range_audit.py'),
        recordAuditVerdict: path.join(resolveBackendDir(), 'record_audit_verdict.py'),
        pullVpsCandles: path.join(resolveBackendDir(), 'pull_vps_candles.py'),
        localResearchSeed: path.join(resolveBackendDir(), 'local_research_seed.py'),
        mappingAssistant: path.join(
          resolveRangeLibraryPythonRoot(),
          'range_library_memory',
          'xauusd_mapping_assistant.py',
        ),
      },
    };
  });
}

module.exports = {
  registerLocalResearchIpc,
  validateBatchPromoteArgs,
  normalizeRunnerArgs,
  defaultDatabasePath,
  buildDatabaseStatus,
  resolveRangeLibraryPythonRoot,
  buildMappingAssistantSpec,
  runMappingAssistant,
  buildWeeklyScript1Spec,
  buildWeeklyMasterMapSpec,
  buildWeeklyScript1ReviewSpec,
  buildDoctrineSpec,
  runDoctrineCommand,
  createDisposableAnalysisCopy,
  preflightWeeklyAnalysis,
  runWeeklyScript1Activation,
  runWeeklyScript1Review,
  loadWeeklyScript1State,
  weeklyAnalysisPaths,
};
