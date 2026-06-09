const { app, BrowserWindow } = require('electron');
const path = require('path');

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: '#05070d',
    title: 'FX TrendMaster Cockpit',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false
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

app.whenReady().then(createWindow);
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
