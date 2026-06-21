const fs = require('fs');
const { spawnSync } = require('child_process');

const INSPECT_PY = `
import json
import sqlite3
import sys

def safe_count(cur, sql, params=()):
    try:
        row = cur.execute(sql, params).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return None

def main():
    db_path = sys.argv[1]
    symbol = (sys.argv[2] if len(sys.argv) > 2 else "XAUUSD").upper()
    timeframe = (sys.argv[3] if len(sys.argv) > 3 else "W1").upper()
    out = {
        "readable": False,
        "totalCandles": None,
        "w1Candles": None,
        "suggestions": None,
        "mapRanges": None,
    }
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = conn.cursor()
    out["readable"] = True
    out["totalCandles"] = safe_count(cur, "SELECT COUNT(*) FROM candles")
    out["w1Candles"] = safe_count(
        cur,
        "SELECT COUNT(*) FROM candles WHERE symbol=? AND timeframe=?",
        (symbol, timeframe),
    )
    out["suggestions"] = safe_count(cur, "SELECT COUNT(*) FROM detector_suggestions")
    out["mapRanges"] = safe_count(cur, "SELECT COUNT(*) FROM map_ranges")
    conn.close()
    print(json.dumps(out))

if __name__ == "__main__":
    main()
`.trim();

function resolvePythonExecutable() {
  return process.env.FXTM_PYTHON || process.env.PYTHON || 'python';
}

function inspectDatabaseFile(dbPath, options = {}) {
  const symbol = String(options.symbol || 'XAUUSD').toUpperCase();
  const timeframe = String(options.timeframe || 'W1').toUpperCase();
  const exists = fs.existsSync(dbPath);
  const base = {
    databasePath: dbPath,
    exists,
    readable: false,
    totalCandles: null,
    w1Candles: null,
    suggestions: null,
    mapRanges: null,
    readyForWeeklyScan: false,
  };

  if (!exists) {
    return {
      ...base,
      error: 'Database file not found. Copy your VPS database here or choose another file.',
    };
  }

  try {
    const stat = fs.statSync(dbPath);
    if (!stat.isFile()) {
      return { ...base, error: 'Path is not a file.' };
    }
  } catch (err) {
    return { ...base, error: err.message || String(err) };
  }

  const result = spawnSync(
    resolvePythonExecutable(),
    ['-c', INSPECT_PY, dbPath, symbol, timeframe],
    { encoding: 'utf8', timeout: 15000 },
  );

  if (result.error) {
    return { ...base, error: result.error.message || String(result.error) };
  }
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || '').trim();
    return {
      ...base,
      error: detail || `Database inspect failed (exit ${result.status})`,
    };
  }

  let parsed;
  try {
    parsed = JSON.parse(String(result.stdout || '').trim());
  } catch (err) {
    return { ...base, error: `Could not parse database inspect output: ${err.message}` };
  }

  const w1Candles = parsed.w1Candles;
  const readyForWeeklyScan = typeof w1Candles === 'number' && w1Candles > 0;

  return {
    ...base,
    readable: Boolean(parsed.readable),
    totalCandles: parsed.totalCandles,
    w1Candles,
    suggestions: parsed.suggestions,
    mapRanges: parsed.mapRanges,
    readyForWeeklyScan,
    error: readyForWeeklyScan
      ? undefined
      : 'No W1 candles found for XAUUSD. Copy a VPS database that includes weekly candle history.',
  };
}

module.exports = {
  inspectDatabaseFile,
};
