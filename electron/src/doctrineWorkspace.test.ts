import fs from 'fs';
import os from 'os';
import path from 'path';
import { createRequire } from 'module';
import { describe, expect, it } from 'vitest';

const requireCjs = createRequire(import.meta.url);
const {
  instrumentWorkspacePaths,
  refreshInstrumentWorkspace,
} = requireCjs('../electron/doctrineWorkspace.cjs');

function createLiveDatabase(databasePath: string, marker: string) {
  const { DatabaseSync } = requireCjs('node:sqlite');
  const db = new DatabaseSync(databasePath);
  db.exec(`
    CREATE TABLE raw_ranges(id INTEGER PRIMARY KEY, marker TEXT);
    CREATE TABLE raw_events(id INTEGER PRIMARY KEY, marker TEXT);
    CREATE TABLE master_map_ranges(canonical_range_id TEXT PRIMARY KEY);
    CREATE TABLE master_map_outputs(symbol TEXT PRIMARY KEY, output_json TEXT);
  `);
  db.prepare('INSERT INTO raw_ranges VALUES (?,?)').run(1, marker);
  db.prepare('INSERT INTO raw_events VALUES (?,?)').run(1, marker);
  db.prepare('INSERT INTO master_map_outputs VALUES (?,?)').run('XAUUSD', '{}');
  db.close();
}

describe('instrument doctrine workspace', () => {
  it('uses one workspace per live library and instrument, not per case', () => {
    const root = path.join(os.tmpdir(), 'fxtm-doctrine-paths');
    const live = path.join(root, 'range-library.sqlite3');
    const first = instrumentWorkspacePaths(live, 'XAUUSD', root);
    const second = instrumentWorkspacePaths(live, 'xauusd', root);
    expect(first).toEqual(second);
    expect(first.analysisDatabasePath).toContain('xauusd-');
  });

  it('refreshes live evidence while retaining doctrine approval memory', async () => {
    const { DatabaseSync } = requireCjs('node:sqlite');
    const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'fxtm-doctrine-refresh-'));
    const live = path.join(folder, 'live.sqlite3');
    const workspace = path.join(folder, 'workspace.sqlite3');
    createLiveDatabase(live, 'first');
    await refreshInstrumentWorkspace(live, workspace);

    const approved = new DatabaseSync(workspace);
    approved.exec(`
      CREATE TABLE doctrine_scripts(
        script_id TEXT PRIMARY KEY, script_key TEXT, display_name TEXT, description TEXT,
        execution_order INTEGER, status TEXT, current_approved_version_id TEXT,
        created_at TEXT, updated_at TEXT
      );
    `);
    approved.prepare('INSERT INTO doctrine_scripts VALUES (?,?,?,?,?,?,?,?,?)').run(
      'script-1', 'weekly_structure', 'Weekly structure', null, 10,
      'APPROVED', 'version-1', 'created', 'updated',
    );
    approved.exec(`
      CREATE TABLE inherited_doctrine_enrichments(
        target_layer TEXT, target_namespace TEXT, canonical_range_id TEXT,
        symbol TEXT, case_ref TEXT, payload_json TEXT
      );
    `);
    approved.prepare('INSERT INTO inherited_doctrine_enrichments VALUES (?,?,?,?,?,?)').run(
      'DAILY', 'daily_structure', 'daily-662', 'XAUUSD', 'case:live', '{"bos_direction":"BOS_UP"}',
    );
    approved.close();

    fs.rmSync(live);
    createLiveDatabase(live, 'second');
    await refreshInstrumentWorkspace(live, workspace);

    const refreshed = new DatabaseSync(workspace, { readOnly: true });
    expect(refreshed.prepare('SELECT marker FROM raw_ranges WHERE id=1').get().marker).toBe('second');
    expect(refreshed.prepare('SELECT status FROM doctrine_scripts WHERE script_id=?').get('script-1').status)
      .toBe('APPROVED');
    expect(refreshed.prepare(
      'SELECT canonical_range_id FROM inherited_doctrine_enrichments WHERE case_ref=?',
    ).get('case:live').canonical_range_id).toBe('daily-662');
    refreshed.close();
  });
});
