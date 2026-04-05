const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

const BACKEND_PORT = 7842;
const VITE_DEV_URL = 'http://localhost:5173';
const IS_DEV = process.env.ELECTRON_DEV === '1';

let backendProcess = null;
let mainWindow = null;

// ── Backend spawning ──────────────────────────────────────────────────────────

function spawnBackend() {
  const scriptPath = path.join(__dirname, '..', 'backend', 'main.py');

  backendProcess = spawn('python3', [scriptPath], {
    env: { ...process.env },
    stdio: IS_DEV ? 'inherit' : 'pipe',
  });

  backendProcess.on('error', (err) => {
    console.error('[Electron] Failed to start backend:', err.message);
  });

  backendProcess.on('exit', (code, signal) => {
    console.log(`[Electron] Backend exited: code=${code} signal=${signal}`);
    backendProcess = null;
  });
}

// ── Health polling ────────────────────────────────────────────────────────────

function pollBackendHealth(retries = 30, intervalMs = 1000) {
  return new Promise((resolve, reject) => {
    let attempts = 0;

    function attempt() {
      attempts++;
      const req = http.get(
        `http://127.0.0.1:${BACKEND_PORT}/health`,
        (res) => {
          if (res.statusCode === 200) {
            console.log(`[Electron] Backend healthy after ${attempts} attempt(s)`);
            resolve();
          } else {
            retry();
          }
        }
      );
      req.on('error', retry);
      req.setTimeout(800, () => {
        req.destroy();
        retry();
      });
    }

    function retry() {
      if (attempts >= retries) {
        reject(new Error(`Backend did not become healthy after ${retries} attempts`));
      } else {
        setTimeout(attempt, intervalMs);
      }
    }

    attempt();
  });
}

// ── Window creation ───────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    show: false,
    backgroundColor: '#0f172a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (IS_DEV) {
    mainWindow.loadURL(VITE_DEV_URL);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(
      path.join(__dirname, '..', 'frontend', 'dist', 'index.html')
    );
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── IPC: proxy backend fetch requests from renderer ───────────────────────────

ipcMain.handle('backend:fetch', async (_event, urlPath, options = {}) => {
  // Only allow fetching from the local backend
  const url = `http://127.0.0.1:${BACKEND_PORT}${urlPath}`;
  let fetchFn;
  try {
    const mod = await import('node-fetch');
    fetchFn = mod.default;
  } catch {
    if (typeof globalThis.fetch === 'function') {
      fetchFn = globalThis.fetch;
    } else {
      throw new Error('No fetch implementation available (node-fetch not installed and globalThis.fetch absent)');
    }
  }
  const response = await fetchFn(url, options);
  const data = await response.json();
  return { status: response.status, data };
});

// ── App lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  // In dev mode the backend is already running via `npm run dev:backend`.
  // Only spawn it ourselves in production.
  if (!IS_DEV) {
    spawnBackend();
  }

  try {
    await pollBackendHealth();
  } catch (err) {
    console.error('[Electron] Backend health check failed:', err.message);
    if (!IS_DEV) {
      app.quit();
      return;
    }
    // In dev, continue anyway — something else may be wrong but we can still show the UI.
  }

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  if (backendProcess) {
    backendProcess.kill('SIGTERM');
    backendProcess = null;
  }
});
