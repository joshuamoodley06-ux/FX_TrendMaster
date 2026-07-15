const fs = require('fs');
const path = require('path');
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

let localResearchBusy = false;

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
};
