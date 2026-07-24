import fs from 'fs';
import os from 'os';
import path from 'path';
import { createRequire } from 'module';
import { describe, expect, it } from 'vitest';

const requireCjs = createRequire(import.meta.url);
const { refreshInstrumentWorkspace } = requireCjs('../electron/doctrineWorkspace.cjs');

function createLive(pathname: string, marker: string) {
  const { DatabaseSync } = requireCjs('node:sqlite');
  const database = new DatabaseSync(pathname);
  database.exec('CREATE TABLE raw_ranges(id INTEGER PRIMARY KEY,marker TEXT);');
  database.prepare('INSERT INTO raw_ranges VALUES (?,?)').run(1, marker);
  database.close();
}

describe('statistics report workspace persistence', () => {
  it('retains report snapshot history when live mapping evidence refreshes', async () => {
    const { DatabaseSync } = requireCjs('node:sqlite');
    const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'fxtm-statistics-workspace-'));
    const live = path.join(folder, 'live.sqlite3');
    const workspace = path.join(folder, 'workspace.sqlite3');
    createLive(live, 'first');
    await refreshInstrumentWorkspace(live, workspace);

    const analysis = new DatabaseSync(workspace);
    analysis.exec(`CREATE TABLE statistics_report_snapshots(
      report_id TEXT PRIMARY KEY,schema_version TEXT,symbol TEXT,case_ref TEXT,
      weekly_start TEXT,daily_start TEXT,structural_content_hash TEXT,generated_at TEXT,
      payload_json TEXT,json_path TEXT,weekly_csv_path TEXT,daily_csv_path TEXT,parent_csv_path TEXT
    )`);
    analysis.prepare(
      'INSERT INTO statistics_report_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
    ).run(
      'report-1',
      'weekly_daily_statistics_v1',
      'XAUUSD',
      'case:stats',
      '2023-01-29',
      '2024-10-27',
      'hash-1',
      '2026-07-24T00:00:00Z',
      '{}',
      'report.json',
      'weekly.csv',
      'daily.csv',
      'parents.csv',
    );
    analysis.close();

    fs.rmSync(live);
    createLive(live, 'second');
    await refreshInstrumentWorkspace(live, workspace);

    const refreshed = new DatabaseSync(workspace, { readOnly: true });
    expect(
      refreshed.prepare('SELECT marker FROM raw_ranges WHERE id=1').get().marker,
    ).toBe('second');
    expect(
      refreshed.prepare('SELECT report_id FROM statistics_report_snapshots').get().report_id,
    ).toBe('report-1');
    refreshed.close();
  });
});
