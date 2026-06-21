var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/localPythonRunner.ts
var localPythonRunner_exports = {};
__export(localPythonRunner_exports, {
  DEFAULT_VPS_BASE_URL: () => DEFAULT_VPS_BASE_URL,
  LAST_DETECTION_RUN_STORAGE_KEY: () => LAST_DETECTION_RUN_STORAGE_KEY,
  buildBatchRangePromoteCommand: () => buildBatchRangePromoteCommand,
  buildDetectorPerformanceCommand: () => buildDetectorPerformanceCommand,
  buildExportDetectionAuditLocalCommand: () => buildExportDetectionAuditLocalCommand,
  buildHistoricalRangeScanCommand: () => buildHistoricalRangeScanCommand,
  buildLatestDetectorRunLocalCommand: () => buildLatestDetectorRunLocalCommand,
  buildListDetectorRunLocalCommand: () => buildListDetectorRunLocalCommand,
  buildListDetectorSuggestionsLocalCommand: () => buildListDetectorSuggestionsLocalCommand,
  buildLocalPythonEnv: () => buildLocalPythonEnv,
  buildLocalResearchSeedCommand: () => buildLocalResearchSeedCommand,
  buildPullVpsCandlesCommand: () => buildPullVpsCandlesCommand,
  buildRandomRangeAuditCommand: () => buildRandomRangeAuditCommand,
  buildRecordAuditVerdictCommand: () => buildRecordAuditVerdictCommand,
  buildReviewSuggestionLocalCommand: () => buildReviewSuggestionLocalCommand,
  buildRunDetectorLocalCommand: () => buildRunDetectorLocalCommand,
  exportDetectionAuditLocal: () => exportDetectionAuditLocal,
  latestDetectorRunLocal: () => latestDetectorRunLocal,
  listDetectorRunLocal: () => listDetectorRunLocal,
  listDetectorSuggestionsLocal: () => listDetectorSuggestionsLocal,
  resolveBackendDir: () => resolveBackendDir,
  resolveDatabasePath: () => resolveDatabasePath,
  reviewSuggestionLocal: () => reviewSuggestionLocal,
  runBatchRangePromote: () => runBatchRangePromote,
  runDetectorLocal: () => runDetectorLocal,
  runDetectorPerformance: () => runDetectorPerformance,
  runHistoricalRangeScan: () => runHistoricalRangeScan,
  runLocalResearchSeed: () => runLocalResearchSeed,
  runPullVpsCandles: () => runPullVpsCandles,
  runRandomRangeAudit: () => runRandomRangeAudit,
  runRecordAuditVerdict: () => runRecordAuditVerdict,
  spawnLocalPythonScript: () => spawnLocalPythonScript
});
module.exports = __toCommonJS(localPythonRunner_exports);
var import_child_process = require("child_process");
var import_fs = __toESM(require("fs"));
var import_os = __toESM(require("os"));
var import_path = __toESM(require("path"));

// src/localPythonOutput.ts
function parseHistoricalScanOutput(stdout) {
  const out = {};
  const patterns = [
    ["candles_scanned", /candles_scanned:\s+(\d+)/],
    ["suggestions_created", /suggestions_created:\s+(\d+)/],
    ["range_candidate_count", /RANGE_CANDIDATE:\s+(\d+)/],
    ["chain_candidates", /chain_candidates:\s+(\d+)/],
    ["no_valid_range_count", /NO_VALID_RANGE:\s+(\d+)/],
    ["no_minor_structure_count", /NO_MINOR_STRUCTURE:\s+(\d+)/],
    ["first_suggestion", /first_suggestion:\s+(.+)/],
    ["last_suggestion", /last_suggestion:\s+(.+)/],
    ["detection_run_id", /detection_run_id:\s+(\S+)/]
  ];
  for (const [key, re] of patterns) {
    const match = stdout.match(re);
    if (!match) continue;
    const raw = match[1].trim();
    out[key] = /^\d+$/.test(raw) ? Number(raw) : raw === "\u2014" ? null : raw;
  }
  return out;
}
function parseJsonOutput(stdout) {
  const trimmed = stdout.trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    const jsonStart = trimmed.indexOf("{");
    if (jsonStart >= 0) {
      try {
        return JSON.parse(trimmed.slice(jsonStart));
      } catch {
        return { raw: trimmed };
      }
    }
    return { raw: trimmed };
  }
}
function parseBatchPromoteOutput(stdout) {
  return parseJsonOutput(stdout);
}
function parseDetectorPerformanceOutput(stdout) {
  return parseJsonOutput(stdout);
}
function parseRandomAuditOutput(stdout) {
  const parsed = parseJsonOutput(stdout);
  if (!parsed || typeof parsed !== "object") return null;
  return parsed;
}

// src/vpsConfig.ts
var DEFAULT_VPS_BASE_URL = "https://api01.apexcoastalrentals.co.za";

// src/localPythonRunner.ts
var LAST_DETECTION_RUN_STORAGE_KEY = "fx_tm_last_detection_run_id";
var DEFAULT_PYTHON = process.env.FXTM_PYTHON || "python";
function resolveBackendDir(explicit) {
  if (explicit) return import_path.default.resolve(explicit);
  if (process.env.FXTM_BACKEND_DIR) return import_path.default.resolve(process.env.FXTM_BACKEND_DIR);
  const candidates = [
    import_path.default.resolve(process.cwd(), "backend"),
    import_path.default.resolve(process.cwd(), "../backend"),
    import_path.default.resolve(__dirname, "../../backend"),
    import_path.default.resolve(__dirname, "../../../backend")
  ];
  for (const candidate of candidates) {
    if (import_fs.default.existsSync(import_path.default.join(candidate, "historical_range_scan.py"))) {
      return candidate;
    }
  }
  return import_path.default.resolve(process.cwd(), "../backend");
}
function resolveDatabasePath(explicit) {
  if (explicit) return import_path.default.resolve(explicit);
  if (process.env.DATABASE_PATH) return import_path.default.resolve(process.env.DATABASE_PATH);
  const home = process.env.USERPROFILE || process.env.HOME || "";
  if (home) {
    return import_path.default.join(home, "Documents", "FXTM_Research", "raw_mapping_v159.db");
  }
  return import_path.default.resolve(resolveBackendDir(), "data", "raw_mapping_v159.db");
}
function buildLocalPythonEnv(options) {
  const backendDir = import_path.default.resolve(options.backendDir);
  const dbPath = import_path.default.resolve(options.databasePath || resolveDatabasePath());
  const rawPath = import_path.default.resolve(options.rawMappingDbPath || dbPath);
  return {
    ...process.env,
    PYTHONPATH: backendDir,
    PYTHONUNBUFFERED: "1",
    DATABASE_PATH: dbPath,
    RAW_MAPPING_DB_PATH: rawPath,
    MARKET_MEMORY_DB_PATH: dbPath,
    DETECTOR_RANGE_MODE: "doctrine_v2",
    DETECTOR_RANGE_SCALE_MODE: "generic",
    FXTM_BACKEND_DIR: backendDir,
    ...options.extra
  };
}
function pushArg(args, flag, value) {
  if (value === void 0 || value === null || value === "") return;
  args.push(flag, String(value));
}
function buildHistoricalRangeScanCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    import_path.default.join(backendDir, "historical_range_scan.py"),
    "--symbol",
    args.symbol || "XAUUSD",
    "--timeframe",
    args.timeframe || "W1",
    "--from",
    args.dateFrom,
    "--to",
    args.dateTo
  ];
  pushArg(cliArgs, "--layer", args.layer);
  pushArg(cliArgs, "--sample", args.sample);
  pushArg(cliArgs, "--detection-run-id", args.detectionRunId);
  pushArg(cliArgs, "--candidate-kind", args.candidateKind);
  pushArg(cliArgs, "--limit", args.limit);
  pushArg(cliArgs, "--candle-limit", args.candleLimit);
  pushArg(cliArgs, "--db", args.databasePath);
  if (args.chain) cliArgs.push("--chain");
  if (args.useManualSeed) cliArgs.push("--use-manual-seed");
  if (args.seedPolicy === "reviewed_truth_only") {
    pushArg(cliArgs, "--seed-policy", "reviewed_truth_only");
  }
  if (args.dryRun) cliArgs.push("--dry-run");
  return {
    script: "historical_range_scan.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
function buildBatchRangePromoteCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    import_path.default.join(backendDir, "batch_range_promote.py"),
    "--symbol",
    args.symbol || "XAUUSD",
    "--timeframe",
    args.timeframe || "W1"
  ];
  pushArg(cliArgs, "--layer", args.layer);
  pushArg(cliArgs, "--from", args.dateFrom);
  pushArg(cliArgs, "--to", args.dateTo);
  pushArg(cliArgs, "--candidate-kind", args.candidateKind);
  pushArg(cliArgs, "--status", args.status);
  pushArg(cliArgs, "--detector-version", args.detectorVersion);
  pushArg(cliArgs, "--detection-run-id", args.detectionRunId);
  pushArg(cliArgs, "--db", args.databasePath);
  if (args.confirm) cliArgs.push("--confirm");
  if (args.summaryOnly) cliArgs.push("--summary-only");
  if (args.json !== false) cliArgs.push("--json");
  return {
    script: "batch_range_promote.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
function buildDetectorPerformanceCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [import_path.default.join(backendDir, "detector_performance.py")];
  pushArg(cliArgs, "--symbol", args.symbol);
  pushArg(cliArgs, "--structure-layer", args.structureLayer);
  pushArg(cliArgs, "--source-timeframe", args.sourceTimeframe);
  pushArg(cliArgs, "--db", args.databasePath);
  if (args.json !== false) cliArgs.push("--json");
  return {
    script: "detector_performance.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
function buildRandomRangeAuditCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    import_path.default.join(backendDir, "random_range_audit.py"),
    "--symbol",
    args.symbol || "XAUUSD",
    "--timeframe",
    args.timeframe || "W1"
  ];
  pushArg(cliArgs, "--layer", args.layer);
  pushArg(cliArgs, "--from", args.dateFrom);
  pushArg(cliArgs, "--to", args.dateTo);
  pushArg(cliArgs, "--limit", args.limit);
  pushArg(cliArgs, "--source", args.source);
  pushArg(cliArgs, "--detection-run-id", args.detectionRunId);
  pushArg(cliArgs, "--db", args.databasePath);
  if (args.json !== false) cliArgs.push("--json");
  return {
    script: "random_range_audit.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
function buildRecordAuditVerdictCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    import_path.default.join(backendDir, "record_audit_verdict.py"),
    "--suggestion-id",
    args.suggestionId,
    "--action",
    args.action
  ];
  pushArg(cliArgs, "--notes", args.notes);
  pushArg(cliArgs, "--db", args.databasePath);
  if (args.json !== false) cliArgs.push("--json");
  return {
    script: "record_audit_verdict.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
function buildPullVpsCandlesCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    import_path.default.join(backendDir, "pull_vps_candles.py"),
    "--base-url",
    args.baseUrl || DEFAULT_VPS_BASE_URL,
    "--symbol",
    args.symbol || "XAUUSD",
    "--timeframes",
    args.timeframes || "W1,D1,H4,H1,M15,M5"
  ];
  pushArg(cliArgs, "--limit", args.limit);
  pushArg(cliArgs, "--db", args.databasePath);
  if (args.json !== false) cliArgs.push("--json");
  return {
    script: "pull_vps_candles.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
function buildLocalResearchSeedCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    import_path.default.join(backendDir, "local_research_seed.py"),
    args.command,
    "--symbol",
    args.symbol || "XAUUSD"
  ];
  pushArg(cliArgs, "--db", args.databasePath);
  if (args.command === "create-manual") {
    pushArg(cliArgs, "--range-high", args.rangeHigh);
    pushArg(cliArgs, "--range-low", args.rangeLow);
    pushArg(cliArgs, "--range-high-time", args.rangeHighTime);
    pushArg(cliArgs, "--range-low-time", args.rangeLowTime);
  }
  if (args.command === "activate") {
    pushArg(cliArgs, "--range-id", args.rangeId);
  }
  if (args.command === "list") {
    pushArg(cliArgs, "--limit", args.limit);
  }
  if (args.command === "diagnose-scan") {
    pushArg(cliArgs, "--detection-run-id", args.detectionRunId);
  }
  if (args.json !== false) cliArgs.push("--json");
  return {
    script: "local_research_seed.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
function formatCommand(spec) {
  return `${spec.pythonPath} ${spec.args.join(" ")}`;
}
async function spawnLocalPythonScript(spec, options) {
  const spawnImpl = options?.spawnFn || import_child_process.spawn;
  const command = formatCommand(spec);
  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let spawnError;
    let timedOut = false;
    let child;
    try {
      child = spawnImpl(spec.pythonPath, spec.args, {
        cwd: spec.cwd,
        env: spec.env,
        windowsHide: true
      });
    } catch (err) {
      resolve({
        ok: false,
        exitCode: null,
        stdout: "",
        stderr: "",
        error: String(err instanceof Error ? err.message : err),
        command
      });
      return;
    }
    const timer = options?.timeoutMs && options.timeoutMs > 0 ? setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
    }, options.timeoutMs) : null;
    let settled = false;
    const finish = (payload) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      const parsed = options?.parse && stdout ? options.parse(stdout) : void 0;
      resolve({
        ok: payload.ok,
        exitCode: payload.exitCode,
        stdout,
        stderr,
        error: payload.error,
        command,
        parsed
      });
    };
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (err) => {
      spawnError = String(err.message || err);
      finish({
        ok: false,
        exitCode: null,
        error: spawnError
      });
    });
    child.on("close", (code) => {
      const ok = !spawnError && !timedOut && code === 0;
      finish({
        ok,
        exitCode: code,
        error: spawnError || (timedOut ? `timeout after ${options?.timeoutMs}ms` : void 0)
      });
    });
  });
}
async function runHistoricalRangeScan(args) {
  const spec = buildHistoricalRangeScanCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs,
    parse: parseHistoricalScanOutput
  });
}
async function runBatchRangePromote(args) {
  const spec = buildBatchRangePromoteCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs,
    parse: parseBatchPromoteOutput
  });
}
async function runDetectorPerformance(args) {
  const spec = buildDetectorPerformanceCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs,
    parse: parseDetectorPerformanceOutput
  });
}
async function runRandomRangeAudit(args) {
  const spec = buildRandomRangeAuditCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs,
    parse: parseRandomAuditOutput
  });
}
async function runRecordAuditVerdict(args) {
  const spec = buildRecordAuditVerdictCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs,
    parse: parseBatchPromoteOutput
  });
}
async function runPullVpsCandles(args) {
  const spec = buildPullVpsCandlesCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 18e4,
    parse: parseJsonOutput
  });
}
async function runLocalResearchSeed(args) {
  const spec = buildLocalResearchSeedCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 6e4,
    parse: parseJsonOutput
  });
}
function buildRunDetectorLocalCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    import_path.default.join(backendDir, "run_detector_local.py"),
    "--db",
    args.databasePath || resolveDatabasePath(),
    "run",
    "--payload-file",
    args.payloadFile
  ];
  return {
    script: "run_detector_local.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
function buildListDetectorSuggestionsLocalCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    import_path.default.join(backendDir, "run_detector_local.py"),
    "--db",
    args.databasePath || resolveDatabasePath(),
    "list",
    "--symbol",
    args.symbol || "XAUUSD",
    "--structure-layer",
    args.structureLayer || "WEEKLY",
    "--source-timeframe",
    args.sourceTimeframe || "W1"
  ];
  pushArg(cliArgs, "--detection-run-id", args.detectionRunId);
  pushArg(cliArgs, "--replay-until-ms", args.replayUntilMs);
  pushArg(cliArgs, "--limit", args.limit);
  pushArg(cliArgs, "--status", args.status);
  return {
    script: "run_detector_local.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
async function runDetectorLocal(args) {
  const payloadFile = import_path.default.join(
    import_os.default.tmpdir(),
    `fx-detector-payload-${Date.now()}-${Math.random().toString(16).slice(2)}.json`
  );
  import_fs.default.writeFileSync(payloadFile, JSON.stringify(args.payload ?? {}), "utf8");
  try {
    const spec = buildRunDetectorLocalCommand({ ...args, payloadFile });
    return await spawnLocalPythonScript(spec, {
      spawnFn: args.spawnFn,
      timeoutMs: args.timeoutMs ?? 12e4,
      parse: parseJsonOutput
    });
  } finally {
    try {
      import_fs.default.unlinkSync(payloadFile);
    } catch {
    }
  }
}
async function listDetectorSuggestionsLocal(args) {
  const spec = buildListDetectorSuggestionsLocalCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 6e4,
    parse: parseJsonOutput
  });
}
function buildListDetectorRunLocalCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    import_path.default.join(backendDir, "run_detector_local.py"),
    "--db",
    args.databasePath || resolveDatabasePath(),
    "list-run",
    "--symbol",
    args.symbol || "XAUUSD",
    "--structure-layer",
    args.structureLayer || "WEEKLY",
    "--source-timeframe",
    args.sourceTimeframe || "W1",
    "--detection-run-id",
    args.detectionRunId,
    "--candidate-kind",
    args.candidateKind || "RANGE_CANDIDATE"
  ];
  return {
    script: "run_detector_local.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
function buildReviewSuggestionLocalCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    import_path.default.join(backendDir, "run_detector_local.py"),
    "--db",
    args.databasePath || resolveDatabasePath(),
    "review",
    "--suggestion-id",
    args.suggestionId,
    "--action",
    args.action
  ];
  if (args.edits && Object.keys(args.edits).length) {
    cliArgs.push("--edits-json", JSON.stringify(args.edits));
  }
  pushArg(cliArgs, "--error-category", args.errorCategory);
  pushArg(cliArgs, "--notes", args.notes);
  return {
    script: "run_detector_local.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
function buildExportDetectionAuditLocalCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    import_path.default.join(backendDir, "run_detector_local.py"),
    "--db",
    args.databasePath || resolveDatabasePath(),
    "export-audit",
    "--symbol",
    args.symbol || "XAUUSD",
    "--structure-layer",
    args.structureLayer || "WEEKLY",
    "--source-timeframe",
    args.sourceTimeframe || "W1",
    "--detection-run-id",
    args.detectionRunId,
    "--candidate-kind",
    args.candidateKind || "RANGE_CANDIDATE"
  ];
  pushArg(cliArgs, "--out", args.outPath);
  return {
    script: "run_detector_local.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
async function listDetectorRunLocal(args) {
  const spec = buildListDetectorRunLocalCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 6e4,
    parse: parseJsonOutput
  });
}
async function reviewSuggestionLocal(args) {
  const spec = buildReviewSuggestionLocalCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 6e4,
    parse: parseJsonOutput
  });
}
async function exportDetectionAuditLocal(args) {
  const spec = buildExportDetectionAuditLocalCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 12e4,
    parse: parseJsonOutput
  });
}
function buildLatestDetectorRunLocalCommand(args) {
  const backendDir = resolveBackendDir(args.backendDir);
  const pythonPath = args.pythonPath || DEFAULT_PYTHON;
  const cliArgs = [
    import_path.default.join(backendDir, "run_detector_local.py"),
    "--db",
    args.databasePath || resolveDatabasePath(),
    "latest-run",
    "--symbol",
    args.symbol || "XAUUSD",
    "--structure-layer",
    args.structureLayer || "WEEKLY",
    "--source-timeframe",
    args.sourceTimeframe || "W1",
    "--candidate-kind",
    args.candidateKind || "RANGE_CANDIDATE"
  ];
  return {
    script: "run_detector_local.py",
    args: cliArgs,
    cwd: backendDir,
    env: buildLocalPythonEnv({
      backendDir,
      databasePath: args.databasePath,
      rawMappingDbPath: args.rawMappingDbPath
    }),
    pythonPath
  };
}
async function latestDetectorRunLocal(args) {
  const spec = buildLatestDetectorRunLocalCommand(args);
  return spawnLocalPythonScript(spec, {
    spawnFn: args.spawnFn,
    timeoutMs: args.timeoutMs ?? 6e4,
    parse: parseJsonOutput
  });
}
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  DEFAULT_VPS_BASE_URL,
  LAST_DETECTION_RUN_STORAGE_KEY,
  buildBatchRangePromoteCommand,
  buildDetectorPerformanceCommand,
  buildExportDetectionAuditLocalCommand,
  buildHistoricalRangeScanCommand,
  buildLatestDetectorRunLocalCommand,
  buildListDetectorRunLocalCommand,
  buildListDetectorSuggestionsLocalCommand,
  buildLocalPythonEnv,
  buildLocalResearchSeedCommand,
  buildPullVpsCandlesCommand,
  buildRandomRangeAuditCommand,
  buildRecordAuditVerdictCommand,
  buildReviewSuggestionLocalCommand,
  buildRunDetectorLocalCommand,
  exportDetectionAuditLocal,
  latestDetectorRunLocal,
  listDetectorRunLocal,
  listDetectorSuggestionsLocal,
  resolveBackendDir,
  resolveDatabasePath,
  reviewSuggestionLocal,
  runBatchRangePromote,
  runDetectorLocal,
  runDetectorPerformance,
  runHistoricalRangeScan,
  runLocalResearchSeed,
  runPullVpsCandles,
  runRandomRangeAudit,
  runRecordAuditVerdict,
  spawnLocalPythonScript
});
