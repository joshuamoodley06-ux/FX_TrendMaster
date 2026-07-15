// Preload bridge for the Python Analyst integration.
// Exposes minimal channel-fixed APIs; no Node APIs leak into the renderer.

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('analyst', {
  getPaths: () => ipcRenderer.invoke('analyst:getPaths'),
  checkPython: (pythonPath) => ipcRenderer.invoke('analyst:checkPython', { pythonPath }),
  writeInput: (fileName, content) => ipcRenderer.invoke('analyst:writeInput', { fileName, content }),
  run: (options) => ipcRenderer.invoke('analyst:run', options),
  rebuildCombined: (options) => ipcRenderer.invoke('analyst:rebuildCombined', options),
  cancel: () => ipcRenderer.invoke('analyst:cancel'),
  listWorkspace: () => ipcRenderer.invoke('analyst:listWorkspace'),
  readReport: (filePath) => ipcRenderer.invoke('analyst:readReport', { filePath }),
  runQuery: (options) => ipcRenderer.invoke('analyst:runQuery', options),
  writeMediatorQuery: (query) => ipcRenderer.invoke('analyst:writeMediatorQuery', { query }),
  getMediatorSettings: () => ipcRenderer.invoke('analyst:getMediatorSettings'),
  saveMediatorSettings: (payload) => ipcRenderer.invoke('analyst:saveMediatorSettings', payload),
  buildMediatorQuery: (payload) => ipcRenderer.invoke('analyst:buildMediatorQuery', payload),
  explainMediatorResult: (payload) => ipcRenderer.invoke('analyst:explainMediatorResult', payload),
  buildMediatorSql: (payload) => ipcRenderer.invoke('analyst:buildMediatorSql', payload),
  testAiConnection: (payload) => ipcRenderer.invoke('analyst:testAiConnection', payload),
  listAiModels: (payload) => ipcRenderer.invoke('analyst:listAiModels', payload),
  runSqlInspector: (options) => ipcRenderer.invoke('analyst:runSqlInspector', options),
  onLog: (callback) => {
    const handler = (_event, payload) => callback(payload);
    ipcRenderer.on('analyst:log', handler);
    return () => ipcRenderer.removeListener('analyst:log', handler);
  },
});

contextBridge.exposeInMainWorld('localResearch', {
  getPaths: () => ipcRenderer.invoke('local-research:getPaths'),
  getDatabaseStatus: (args) => ipcRenderer.invoke('local-research:getDatabaseStatus', args),
  pickDatabaseFile: () => ipcRenderer.invoke('local-research:pickDatabaseFile'),
  setDatabasePath: (args) => ipcRenderer.invoke('local-research:setDatabasePath', args),
  openResearchFolder: () => ipcRenderer.invoke('local-research:openResearchFolder'),
  pullVpsCandles: (args) => ipcRenderer.invoke('local-research:pull-vps-candles', args),
  runLocalResearchSeed: (args) => ipcRenderer.invoke('local-research:seed', args),
  runHistoricalRangeScan: (args) => ipcRenderer.invoke('local-research:historical-range-scan', args),
  runBatchRangePromote: (args) => ipcRenderer.invoke('local-research:batch-range-promote', args),
  runDetectorPerformance: (args) => ipcRenderer.invoke('local-research:detector-performance', args),
  runDetectorLocal: (args) => ipcRenderer.invoke('local-research:run-detector', args),
  listDetectorSuggestions: (args) => ipcRenderer.invoke('local-research:list-suggestions', args),
  listDetectorRun: (args) => ipcRenderer.invoke('local-research:list-detector-run', args),
  latestDetectorRun: (args) => ipcRenderer.invoke('local-research:latest-detector-run', args),
  reviewSuggestionLocal: (args) => ipcRenderer.invoke('local-research:review-suggestion', args),
  exportDetectionAudit: (args) => ipcRenderer.invoke('local-research:export-detection-audit', args),
  runRandomRangeAudit: (args) => ipcRenderer.invoke('local-research:random-range-audit', args),
  runRecordAuditVerdict: (args) => ipcRenderer.invoke('local-research:record-audit-verdict', args),
  runMappingAssistant: (args) => ipcRenderer.invoke('local-research:mapping-assistant', args),
});

contextBridge.exposeInMainWorld('localMappingBridge', {
  submit: (request) => ipcRenderer.invoke('local-mapping:submit', request),
  backendSucceeded: (editId, backendResponse, httpStatus) =>
    ipcRenderer.invoke('local-mapping:backend-succeeded', { editId, backendResponse, httpStatus }),
  backendFailed: (editId, details) =>
    ipcRenderer.invoke('local-mapping:backend-failed', { editId, ...(details || {}) }),
  getStatus: (editId) => ipcRenderer.invoke('local-mapping:get-status', { editId }),
  retry: (editId) => ipcRenderer.invoke('local-mapping:retry', { editId }),
  getMasterMap: (symbol = 'XAUUSD') => ipcRenderer.invoke('local-mapping:get-master-map', { symbol }),
  getPaths: () => ipcRenderer.invoke('local-mapping:get-paths'),
  resumePending: (limit) => ipcRenderer.invoke('local-mapping:resume-pending', { limit }),
});

contextBridge.exposeInMainWorld('electronAPI', {
  candles: {
    fetch: (symbolOrArgs, timeframe, range) => {
      const args = typeof symbolOrArgs === 'object' && symbolOrArgs !== null
        ? symbolOrArgs
        : { symbol: symbolOrArgs, timeframe, ...(range || {}) };
      return ipcRenderer.invoke('candles:fetch', args);
    },
    upsert: (args) => ipcRenderer.invoke('candles:upsert', args),
    status: (symbolOrArgs, timeframe) => {
      const args = typeof symbolOrArgs === 'object' && symbolOrArgs !== null
        ? symbolOrArgs
        : { symbol: symbolOrArgs, timeframe };
      return ipcRenderer.invoke('candles:status', args);
    },
  },
  ranges: {
    validate: (args) => ipcRenderer.invoke('ranges:validate', args),
    upsert: (args) => ipcRenderer.invoke('ranges:upsert', args),
    list: (args) => ipcRenderer.invoke('ranges:list', args),
  },
});
