const fs = require('fs');
const path = require('path');
const fsp = fs.promises;

const PRESERVED_ANALYSIS_TABLES = new Set([
  'doctrine_scripts',
  'doctrine_script_versions',
  'doctrine_script_runs',
  'doctrine_validation_samples',
  'doctrine_range_processing',
  'doctrine_enrichments',
  'inherited_doctrine_enrichments',
  'weekly_script1_results',
  'weekly_script1_runs',
  'weekly_script1_validation_samples',
]);

function quoteIdentifier(value) {
  return `"${String(value).replace(/"/g, '""')}"`;
}

function quoteSqlString(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}

function instrumentWorkspacePaths(liveDatabasePath, symbol, analysisRoot) {
  const crypto = require('node:crypto');
  const normalizedSymbol = String(symbol || '').trim().toUpperCase();
  if (!normalizedSymbol) throw new Error('Doctrine workspace requires an instrument symbol.');
  const root = path.resolve(String(analysisRoot || ''));
  const identity = crypto.createHash('sha256')
    .update(`${path.resolve(liveDatabasePath)}|${normalizedSymbol}`)
    .digest('hex')
    .slice(0, 20);
  const stem = `${normalizedSymbol.toLowerCase()}-${identity}`;
  return {
    analysisDatabasePath: path.join(root, `${stem}.sqlite3`),
    outputPath: path.join(root, `${stem}.master-map.json`),
  };
}

async function backupDatabase(sourcePath, targetPath) {
  const { DatabaseSync, backup } = require('node:sqlite');
  const source = new DatabaseSync(path.resolve(sourcePath), { readOnly: true });
  try {
    await backup(source, path.resolve(targetPath));
  } finally {
    source.close();
  }
}

function copyPreservedTables(previousPath, refreshedPath) {
  if (!fs.existsSync(previousPath)) return [];
  const { DatabaseSync } = require('node:sqlite');
  const refreshed = new DatabaseSync(refreshedPath);
  const copied = [];
  try {
    refreshed.exec(`ATTACH DATABASE ${quoteSqlString(path.resolve(previousPath))} AS prior`);
    const rows = refreshed.prepare(
      "SELECT name, sql FROM prior.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
    ).all();
    for (const row of rows) {
      const name = String(row.name || '');
      const createSql = String(row.sql || '').trim();
      if (!PRESERVED_ANALYSIS_TABLES.has(name) || !createSql) continue;
      const identifier = quoteIdentifier(name);
      refreshed.exec(`DROP TABLE IF EXISTS main.${identifier}`);
      refreshed.exec(createSql);
      refreshed.exec(`INSERT INTO main.${identifier} SELECT * FROM prior.${identifier}`);
      copied.push(name);
    }
    refreshed.exec('DETACH DATABASE prior');
  } finally {
    refreshed.close();
  }
  return copied;
}

async function replaceAtomically(tempPath, targetPath) {
  const backupPath = `${targetPath}.previous`;
  await fsp.rm(backupPath, { force: true });
  if (fs.existsSync(targetPath)) await fsp.rename(targetPath, backupPath);
  try {
    await fsp.rename(tempPath, targetPath);
    await fsp.rm(backupPath, { force: true });
  } catch (error) {
    if (!fs.existsSync(targetPath) && fs.existsSync(backupPath)) {
      await fsp.rename(backupPath, targetPath);
    }
    throw error;
  }
}

async function refreshInstrumentWorkspace(liveDatabasePath, analysisDatabasePath) {
  const live = path.resolve(String(liveDatabasePath || ''));
  const workspace = path.resolve(String(analysisDatabasePath || ''));
  if (!live || !fs.existsSync(live)) throw new Error(`Range Library database does not exist: ${live}`);
  if (live === workspace) throw new Error('Doctrine workspace cannot be the live Range Library database.');
  await fsp.mkdir(path.dirname(workspace), { recursive: true });
  const temp = `${workspace}.refreshing`;
  await fsp.rm(temp, { force: true });
  await backupDatabase(live, temp);
  const copiedTables = copyPreservedTables(workspace, temp);
  await replaceAtomically(temp, workspace);
  return {
    analysisDatabasePath: workspace,
    copiedTables,
    created: copiedTables.length === 0,
  };
}

module.exports = {
  PRESERVED_ANALYSIS_TABLES,
  instrumentWorkspacePaths,
  refreshInstrumentWorkspace,
};
