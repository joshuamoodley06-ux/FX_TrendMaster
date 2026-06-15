// Preload bridge for the Python Analyst integration.
// Exposes a minimal, channel-fixed API as window.analyst.
// No node APIs leak into the renderer; contextIsolation stays on.

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
