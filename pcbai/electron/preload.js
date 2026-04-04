const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('pcbai', {
  // Proxy a fetch request through the main process to the local backend
  backendFetch: (urlPath, options) =>
    ipcRenderer.invoke('backend:fetch', urlPath, options),

  // Listen for KiCad board state updates pushed from the main process
  onKiCadUpdate: (callback) => {
    ipcRenderer.on('kicad:update', (_event, data) => callback(data));
  },

  // Remove all KiCad update listeners (call on component unmount)
  offKiCadUpdate: () => {
    ipcRenderer.removeAllListeners('kicad:update');
  },
});
