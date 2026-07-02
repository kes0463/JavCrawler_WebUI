const { contextBridge, ipcRenderer, webUtils } = require("electron");

function getPathForFile(file) {
  try {
    if (webUtils?.getPathForFile) return webUtils.getPathForFile(file);
  } catch {}
  return file?.path || "";
}

contextBridge.exposeInMainWorld("javstory", {
  pickFolders: () => ipcRenderer.invoke("harvest:pick-folders"),
  getPathForFile,
  isElectron: true,
  windowControls: {
    minimize: () => ipcRenderer.invoke("window:minimize"),
    maximize: () => ipcRenderer.invoke("window:maximize"),
    close: () => ipcRenderer.invoke("window:close"),
    isMaximized: () => ipcRenderer.invoke("window:is-maximized"),
    onMaximizedChange: (callback) => {
      const listener = (_event, maximized) => callback(maximized);
      ipcRenderer.on("window:maximized-changed", listener);
      return () => ipcRenderer.removeListener("window:maximized-changed", listener);
    },
  },
});
