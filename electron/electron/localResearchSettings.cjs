const fs = require('fs');
const path = require('path');
const { app } = require('electron');

const SETTINGS_FILE = 'local-research-settings.json';

function settingsPath() {
  return path.join(app.getPath('userData'), SETTINGS_FILE);
}

function researchFolder() {
  return path.join(app.getPath('documents'), 'FXTM_Research');
}

function defaultDatabasePath() {
  return path.join(researchFolder(), 'raw_mapping_v159.db');
}

function readResearchSettings() {
  try {
    const raw = fs.readFileSync(settingsPath(), 'utf8');
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeResearchSettings(patch) {
  const current = readResearchSettings();
  const next = { ...current, ...patch, updatedAt: new Date().toISOString() };
  fs.mkdirSync(path.dirname(settingsPath()), { recursive: true });
  fs.writeFileSync(settingsPath(), JSON.stringify(next, null, 2), 'utf8');
  return next;
}

function resolveActiveDatabasePath(explicit) {
  if (explicit) return path.resolve(explicit);
  const saved = readResearchSettings().databasePath;
  if (saved && fs.existsSync(saved)) return path.resolve(saved);
  return defaultDatabasePath();
}

function ensureResearchFolder() {
  const folder = researchFolder();
  fs.mkdirSync(folder, { recursive: true });
  return folder;
}

module.exports = {
  SETTINGS_FILE,
  settingsPath,
  researchFolder,
  defaultDatabasePath,
  readResearchSettings,
  writeResearchSettings,
  resolveActiveDatabasePath,
  ensureResearchFolder,
};
