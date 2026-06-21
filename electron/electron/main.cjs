const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');

const iconPath = path.join(__dirname, '../assets/icon.png');

// ---------------------------------------------------------------------------
// Python Analyst integration (Phase D).
// Electron only: writes input files, spawns the local analyst CLI, reads
// report files back. No DB access, no market interpretation.
// ---------------------------------------------------------------------------

// In a packaged build the Python engine is shipped via asarUnpack, so the
// real files live under app.asar.unpacked (spawn cannot execute from asar).
const ANALYST_DIR = path
  .join(__dirname, '..', 'python_analyst')
  .replace(`app.asar${path.sep}`, `app.asar.unpacked${path.sep}`);
const ANALYST_SCRIPT = path.join(ANALYST_DIR, 'analyst_v1.py');
const FIXTURE_INPUT = path.join(ANALYST_DIR, 'tests', 'fixtures', 'XAUUSD_2020_fixture.json');
const MAX_REPORT_BYTES = 20 * 1024 * 1024;
const SKIP_WORKSPACE_SUBDIRS = new Set(['combined', 'queries']);

const {
  buildMediatorQuery,
  explainMediatorResult,
  buildMediatorSql,
  testAiConnection,
  listAiModels,
  mergeSettings,
  OLLAMA_DEFAULTS,
} = require('./mediatorAi.cjs');
const { registerLocalResearchIpc } = require('./localResearchIpc.cjs');
const { registerCandleCacheIpc } = require('./candleCacheIpc.cjs');
const { closeCandleCache } = require('./candleCache.cjs');

let activeChild = null;

function analystRoot() {
  return path.join(app.getPath('documents'), 'FXTM_Analyst');
}

function workspaceDir() {
  return path.join(analystRoot(), 'workspace');
}

function inputDir() {
  return path.join(analystRoot(), 'input');
}

function mediatorSettingsPath() {
  return path.join(analystRoot(), 'mediator_settings.json');
}

function mediatorQueriesDir() {
  return path.join(analystRoot(), 'mediator_queries');
}

async function readMediatorSettings() {
  const file = mediatorSettingsPath();
  if (!fs.existsSync(file)) {
    return mergeSettings({});
  }
  try {
    const raw = JSON.parse(await fsp.readFile(file, 'utf-8'));
    return mergeSettings(raw);
  } catch {
    return mergeSettings({});
  }
}

async function listWorkspaceYearLabels(symbol) {
  const symbolDir = path.join(workspaceDir(), symbol);
  if (!fs.existsSync(symbolDir)) return [];
  const labels = [];
  for (const entry of await fsp.readdir(symbolDir, { withFileTypes: true })) {
    if (!entry.isDirectory() || SKIP_WORKSPACE_SUBDIRS.has(entry.name)) continue;
    const batchDir = path.join(symbolDir, entry.name);
    if (fs.existsSync(path.join(batchDir, 'yearly_stats.json'))) {
      labels.push(entry.name);
    }
  }
  return labels.sort();
}

function isInside(parent, target) {
  const rel = path.relative(path.resolve(parent), path.resolve(target));
  return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel));
}

// User-chosen batch label for workspace/XAUUSD/<label>/ — not limited to 4-digit years.
function sanitizeAnalystLabel(raw) {
  const text = String(raw || '').trim();
  if (!text) return null;
  const sanitized = text
    .replace(/\s+/g, '_')
    .replace(/[^a-zA-Z0-9._-]/g, '')
    .replace(/_+/g, '_')
    .replace(/^\.+/, '')
    .slice(0, 48);
  return sanitized.length > 0 ? sanitized : null;
}

function sendLog(webContents, stream, text) {
  if (webContents && !webContents.isDestroyed()) {
    webContents.send('analyst:log', { stream, text, at: Date.now() });
  }
}

function spawnAnalyst(webContents, pythonPath, args) {
  return new Promise((resolve) => {
    if (activeChild) {
      resolve({ ok: false, error: 'An analyst process is already running.' });
      return;
    }
    let child;
    try {
      child = spawn(pythonPath || 'python', args, { cwd: ANALYST_DIR, windowsHide: true });
    } catch (err) {
      resolve({ ok: false, error: String(err && err.message ? err.message : err) });
      return;
    }
    activeChild = child;
    sendLog(webContents, 'system', `$ ${pythonPath || 'python'} ${args.join(' ')}`);

    let spawnError = null;
    let stdout = '';
    let stderr = '';
    child.on('error', (err) => {
      spawnError = String(err && err.message ? err.message : err);
      sendLog(webContents, 'stderr', `spawn error: ${spawnError}`);
    });
    child.stdout.on('data', (chunk) => {
      const text = chunk.toString();
      stdout += text;
      sendLog(webContents, 'stdout', text);
    });
    child.stderr.on('data', (chunk) => {
      const text = chunk.toString();
      stderr += text;
      sendLog(webContents, 'stderr', text);
    });
    child.on('close', (code) => {
      activeChild = null;
      sendLog(webContents, 'system', `process exited with code ${code === null ? 'null (killed)' : code}`);
      if (spawnError) {
        resolve({ ok: false, exitCode: null, error: spawnError, stdout, stderr });
      } else {
        resolve({ ok: code === 0, exitCode: code, stdout, stderr });
      }
    });
  });
}

function workspaceCandidates() {
  const primary = workspaceDir();
  const home = app.getPath('home');
  const candidates = [
    primary,
    path.join(home, 'OneDrive', 'Documents', 'FXTM_Analyst', 'workspace'),
    path.join(home, 'Documents', 'FXTM_Analyst', 'workspace'),
  ];
  return [...new Set(candidates.map((p) => path.resolve(p)))];
}

function parseQueryResultFromStdout(stdout) {
  const lines = String(stdout || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i];
    if (!line.startsWith('{') || !line.endsWith('}')) continue;
    try {
      const parsed = JSON.parse(line);
      if (parsed?.schema_version === 'mediator_result_v1') {
        return parsed;
      }
    } catch {
      // continue
    }
  }
  const pathMatch = stdout.match(/query result written to (.+)/);
  return { resultPath: pathMatch ? pathMatch[1].trim() : null };
}

function findQueryResultFile(sym, qid) {
  if (!sym || !qid) return null;
  for (const root of workspaceCandidates()) {
    const candidate = path.join(root, sym, 'queries', qid, 'query_result.json');
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function registerAnalystIpc() {
  ipcMain.handle('analyst:getPaths', () => ({
    ok: true,
    analystRoot: analystRoot(),
    workspaceDir: workspaceDir(),
    inputDir: inputDir(),
    analystScript: ANALYST_SCRIPT,
    fixtureInput: FIXTURE_INPUT,
    scriptExists: fs.existsSync(ANALYST_SCRIPT),
    fixtureExists: fs.existsSync(FIXTURE_INPUT),
  }));

  ipcMain.handle('analyst:checkPython', async (_event, { pythonPath }) => {
    return new Promise((resolve) => {
      let child;
      try {
        child = spawn(pythonPath || 'python', ['--version'], { windowsHide: true });
      } catch (err) {
        resolve({ ok: false, error: String(err && err.message ? err.message : err) });
        return;
      }
      let output = '';
      let failed = null;
      const timer = setTimeout(() => {
        failed = 'timed out after 10s';
        child.kill();
      }, 10000);
      child.on('error', (err) => {
        failed = String(err && err.message ? err.message : err);
      });
      child.stdout.on('data', (chunk) => { output += chunk.toString(); });
      child.stderr.on('data', (chunk) => { output += chunk.toString(); });
      child.on('close', (code) => {
        clearTimeout(timer);
        if (failed || code !== 0) {
          resolve({ ok: false, error: failed || `exit code ${code}: ${output.trim()}` });
        } else {
          resolve({ ok: true, version: output.trim() });
        }
      });
    });
  });

  ipcMain.handle('analyst:writeInput', async (_event, { fileName, content }) => {
    const safeName = path.basename(String(fileName || ''));
    if (!safeName.endsWith('.json')) {
      return { ok: false, error: 'input file name must end with .json' };
    }
    const target = path.join(inputDir(), safeName);
    await fsp.mkdir(inputDir(), { recursive: true });
    await fsp.writeFile(target, typeof content === 'string' ? content : JSON.stringify(content, null, 2), 'utf-8');
    return { ok: true, path: target };
  });

  ipcMain.handle('analyst:run', async (event, { pythonPath, inputPath, symbol, year }) => {
    if (!fs.existsSync(ANALYST_SCRIPT)) {
      return { ok: false, error: `analyst script not found: ${ANALYST_SCRIPT}` };
    }
    const resolvedInput = path.resolve(String(inputPath || ''));
    const inputAllowed =
      fs.existsSync(resolvedInput) &&
      resolvedInput.endsWith('.json') &&
      (isInside(analystRoot(), resolvedInput) || isInside(ANALYST_DIR, resolvedInput));
    if (!inputAllowed) {
      return { ok: false, error: `input package not found or outside allowed folders: ${resolvedInput}` };
    }
    const safeSymbol = String(symbol || '').trim().toUpperCase();
    const safeYear = sanitizeAnalystLabel(year);
    if (!/^[A-Z0-9._-]{1,24}$/.test(safeSymbol)) {
      return { ok: false, error: `invalid symbol: ${symbol}` };
    }
    if (!safeYear) {
      return { ok: false, error: `invalid year label: ${year}` };
    }

    const outputDir = path.join(workspaceDir(), safeSymbol, safeYear);
    await fsp.mkdir(outputDir, { recursive: true });

    const args = [
      ANALYST_SCRIPT,
      '--input', resolvedInput,
      '--output', outputDir,
      '--workspace', workspaceDir(),
    ];
    const result = await spawnAnalyst(event.sender, pythonPath, args);
    return {
      ...result,
      outputDir,
      reportsDir: path.join(outputDir, 'reports'),
      summaryPath: path.join(outputDir, 'reports', 'analyst_summary.json'),
      reportPath: path.join(outputDir, 'reports', 'analyst_report.md'),
    };
  });

  ipcMain.handle('analyst:runQuery', async (event, { pythonPath, queryPath }) => {
    if (!fs.existsSync(ANALYST_SCRIPT)) {
      return { ok: false, error: `analyst script not found: ${ANALYST_SCRIPT}` };
    }
    const resolved = path.resolve(String(queryPath || ''));
    const allowed =
      fs.existsSync(resolved) &&
      resolved.endsWith('.json') &&
      (isInside(analystRoot(), resolved) || isInside(ANALYST_DIR, resolved));
    if (!allowed) {
      return { ok: false, error: `query file not found or outside allowed folders: ${resolved}` };
    }
    const args = [
      ANALYST_SCRIPT,
      '--query', resolved,
      '--workspace', workspaceDir(),
    ];
    const result = await spawnAnalyst(event.sender, pythonPath, args);
    let queryResult = null;
    let resultPath = null;

    const stdoutParsed = parseQueryResultFromStdout(result.stdout);
    if (stdoutParsed?.schema_version === 'mediator_result_v1') {
      queryResult = stdoutParsed;
      resultPath = stdoutParsed.result_path || stdoutParsed.resultPath || null;
    }

    try {
      const raw = JSON.parse(await fsp.readFile(resolved, 'utf-8'));
      const sym = String(raw.symbol || '').toUpperCase();
      const qid = raw.query_id;
      if (!queryResult && sym && qid) {
        resultPath = findQueryResultFile(sym, qid) || resultPath;
        if (resultPath && fs.existsSync(resultPath)) {
          queryResult = JSON.parse(await fsp.readFile(resultPath, 'utf-8'));
        }
      }
      if (!resultPath && stdoutParsed?.resultPath) {
        resultPath = stdoutParsed.resultPath;
        if (fs.existsSync(resultPath)) {
          queryResult = JSON.parse(await fsp.readFile(resultPath, 'utf-8'));
        }
      }
    } catch (err) {
      if (!queryResult) {
        sendLog(event.sender, 'stderr', `query result read failed: ${String(err.message || err)}`);
      }
    }

    const ok = queryResult != null || result.ok;
    return {
      ...result,
      ok,
      queryPath: resolved,
      resultPath,
      queryResult,
      workspaceDir: workspaceDir(),
      error: queryResult
        ? result.error
        : result.error || (result.ok ? 'query_result.json was not found — check workspace path in Local Python Runtime' : `Python exited with code ${result.exitCode}`),
    };
  });

  ipcMain.handle('analyst:writeMediatorQuery', async (_event, { query }) => {
    let payload = query;
    if (typeof query === 'string') {
      try {
        payload = JSON.parse(query);
      } catch (err) {
        return { ok: false, error: `invalid query JSON: ${String(err.message || err)}` };
      }
    }
    if (!payload || typeof payload !== 'object') {
      return { ok: false, error: 'query must be a JSON object' };
    }
    if (!payload.schema_version) {
      payload.schema_version = 'mediator_query_v1';
    }
    const queryId = String(payload.query_id || `q_${Date.now()}`);
    payload.query_id = queryId;
    const dir = mediatorQueriesDir();
    await fsp.mkdir(dir, { recursive: true });
    const target = path.join(dir, `${queryId}.json`);
    await fsp.writeFile(target, JSON.stringify(payload, null, 2), 'utf-8');
    return { ok: true, path: target, queryId, query: payload };
  });

  ipcMain.handle('analyst:getMediatorSettings', async () => {
    const settings = await readMediatorSettings();
    return {
      ok: true,
      settings: {
        provider: settings.provider || 'ollama',
        apiBaseUrl: settings.apiBaseUrl,
        model: settings.model,
        hasApiKey: Boolean(settings.apiKey),
        isOllama: settings.provider === 'ollama' || String(settings.apiBaseUrl).includes('11434'),
      },
    };
  });

  ipcMain.handle('analyst:saveMediatorSettings', async (_event, { settings }) => {
    const current = await readMediatorSettings();
    const provider = settings?.provider || current.provider || OLLAMA_DEFAULTS.provider;
    const next = mergeSettings({
      provider,
      apiBaseUrl: settings?.apiBaseUrl || current.apiBaseUrl,
      model: settings?.model || current.model,
      apiKey: settings?.apiKey ? String(settings.apiKey).trim() : current.apiKey,
    });
    if (settings?.clearApiKey) {
      next.apiKey = next.provider === 'ollama' ? 'ollama' : '';
    }
    if (next.provider === 'ollama' && !next.apiKey) {
      next.apiKey = 'ollama';
    }
    await fsp.mkdir(analystRoot(), { recursive: true });
    await fsp.writeFile(
      mediatorSettingsPath(),
      JSON.stringify(
        {
          provider: next.provider,
          apiBaseUrl: next.apiBaseUrl,
          model: next.model,
          apiKey: next.apiKey,
        },
        null,
        2
      ),
      'utf-8'
    );
    return {
      ok: true,
      hasApiKey: Boolean(next.apiKey),
      settingsPath: mediatorSettingsPath(),
      provider: next.provider,
    };
  });

  ipcMain.handle('analyst:testAiConnection', async (_event, { settings }) => {
    const merged = mergeSettings(settings || await readMediatorSettings());
    return testAiConnection(merged);
  });

  ipcMain.handle('analyst:listAiModels', async (_event, { settings }) => {
    const merged = mergeSettings(settings || await readMediatorSettings());
    return listAiModels(merged);
  });

  ipcMain.handle('analyst:buildMediatorSql', async (_event, payload) => {
    const settings = await readMediatorSettings();
    const symbol = payload?.symbol || 'XAUUSD';
    const yearLabels = payload?.yearLabels || await listWorkspaceYearLabels(symbol);
    return buildMediatorSql(settings, { ...payload, symbol, yearLabels });
  });

  ipcMain.handle('analyst:runSqlInspector', async (event, { pythonPath, sqlPayload }) => {
    if (!fs.existsSync(ANALYST_SCRIPT)) {
      return { ok: false, error: `analyst script not found: ${ANALYST_SCRIPT}` };
    }
    const dir = mediatorQueriesDir();
    await fsp.mkdir(dir, { recursive: true });
    const sqlFile = path.join(dir, `sql_${Date.now()}.json`);
    const payload = {
      ...sqlPayload,
      workspace_root: sqlPayload?.workspace_root || workspaceDir(),
    };
    await fsp.writeFile(sqlFile, JSON.stringify(payload, null, 2), 'utf-8');

    return new Promise((resolve) => {
      const child = spawn(
        pythonPath || 'python',
        [ANALYST_SCRIPT, '--sql', sqlFile, '--workspace', workspaceDir()],
        { cwd: ANALYST_DIR, env: process.env }
      );
      let stdout = '';
      let stderr = '';
      child.stdout.on('data', (chunk) => {
        const text = String(chunk);
        stdout += text;
        sendLog(event.sender, 'stdout', text);
      });
      child.stderr.on('data', (chunk) => {
        const text = String(chunk);
        stderr += text;
        sendLog(event.sender, 'stderr', text);
      });
      child.on('close', (code) => {
        let sqlResult = null;
        const jsonLine = stdout
          .split('\n')
          .map((line) => line.trim())
          .filter((line) => line.startsWith('{') && line.endsWith('}'))
          .pop();
        if (jsonLine) {
          try {
            sqlResult = JSON.parse(jsonLine);
          } catch {
            sqlResult = null;
          }
        }
        resolve({
          ok: code === 0 && sqlResult?.status === 'OK',
          exitCode: code,
          sqlResult,
          error: sqlResult?.error || (code !== 0 ? stderr.trim() || 'SQL inspector failed' : undefined),
        });
      });
    });
  });

  ipcMain.handle('analyst:buildMediatorQuery', async (_event, payload) => {
    const settings = await readMediatorSettings();
    const symbol = String(payload?.symbol || 'XAUUSD').toUpperCase();
    const yearLabels = payload?.yearLabels || await listWorkspaceYearLabels(symbol);
    return buildMediatorQuery(settings, {
      question: payload?.question,
      symbol,
      yearLabels,
      followUp: payload?.followUp,
      priorQuestion: payload?.priorQuestion,
      priorQuery: payload?.priorQuery,
      priorResult: payload?.priorResult,
    });
  });

  ipcMain.handle('analyst:explainMediatorResult', async (_event, payload) => {
    const settings = await readMediatorSettings();
    return explainMediatorResult(settings, {
      question: payload?.question,
      result: payload?.result,
    });
  });

  ipcMain.handle('analyst:rebuildCombined', async (event, { pythonPath, symbol }) => {
    const safeSymbol = String(symbol || '').trim().toUpperCase();
    if (!/^[A-Z0-9._-]{1,24}$/.test(safeSymbol)) {
      return { ok: false, error: `invalid symbol: ${symbol}` };
    }
    const args = [
      ANALYST_SCRIPT,
      '--rebuild-combined',
      '--symbol', safeSymbol,
      '--workspace', workspaceDir(),
    ];
    const result = await spawnAnalyst(event.sender, pythonPath, args);
    return { ...result, combinedDir: path.join(workspaceDir(), safeSymbol, 'combined') };
  });

  ipcMain.handle('analyst:cancel', () => {
    if (!activeChild) {
      return { ok: false, error: 'no analyst process running' };
    }
    activeChild.kill();
    return { ok: true };
  });

  ipcMain.handle('analyst:listWorkspace', async () => {
    const root = workspaceDir();
    const symbols = [];
    if (!fs.existsSync(root)) {
      return { ok: true, workspaceDir: root, symbols };
    }
    for (const symbolEntry of await fsp.readdir(root, { withFileTypes: true })) {
      if (!symbolEntry.isDirectory()) continue;
      const symbolDir = path.join(root, symbolEntry.name);
      const years = [];
      let combined = null;
      for (const yearEntry of await fsp.readdir(symbolDir, { withFileTypes: true })) {
        if (!yearEntry.isDirectory()) continue;
        const entryDir = path.join(symbolDir, yearEntry.name);
        if (yearEntry.name === 'combined') {
          const files = (await fsp.readdir(entryDir)).sort();
          combined = { dir: entryDir, files };
          continue;
        }
        if (SKIP_WORKSPACE_SUBDIRS.has(yearEntry.name)) continue;
        if (!fs.existsSync(path.join(entryDir, 'yearly_stats.json'))) continue;
        const reportsDir = path.join(entryDir, 'reports');
        const reports = fs.existsSync(reportsDir) ? (await fsp.readdir(reportsDir)).sort() : [];
        years.push({
          year: yearEntry.name,
          dir: entryDir,
          hasStats: true,
          reportsDir,
          reports,
        });
      }
      years.sort((a, b) => a.year.localeCompare(b.year));
      symbols.push({ symbol: symbolEntry.name, dir: symbolDir, years, combined });
    }
    symbols.sort((a, b) => a.symbol.localeCompare(b.symbol));
    return { ok: true, workspaceDir: root, symbols };
  });

  ipcMain.handle('analyst:readReport', async (_event, { filePath }) => {
    const resolved = path.resolve(String(filePath || ''));
    if (!isInside(analystRoot(), resolved)) {
      return { ok: false, error: 'path is outside the analyst workspace' };
    }
    let stat;
    try {
      stat = await fsp.stat(resolved);
    } catch {
      return { ok: false, error: `file not found: ${resolved}` };
    }
    if (!stat.isFile() || stat.size > MAX_REPORT_BYTES) {
      return { ok: false, error: 'not a readable report file (missing or too large)' };
    }
    const content = await fsp.readFile(resolved, 'utf-8');
    return { ok: true, path: resolved, content };
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: '#05070d',
    title: 'FX TrendMaster Cockpit',
    icon: iconPath,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.cjs')
    }
  });

  const useDevServer = process.argv.includes('--dev') || process.env.ELECTRON_START_URL;

  if (useDevServer) {
    win.loadURL(process.env.ELECTRON_START_URL || 'http://localhost:5173');
    const shouldOpenDevTools = process.argv.includes('--devtools') || process.env.ELECTRON_OPEN_DEVTOOLS === '1';
    if (shouldOpenDevTools) {
      win.webContents.openDevTools({ mode: 'detach' });
    }
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

app.whenReady().then(() => {
  registerAnalystIpc();
  registerLocalResearchIpc();
  registerCandleCacheIpc();
  createWindow();
});
app.on('will-quit', () => {
  closeCandleCache();
});
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
