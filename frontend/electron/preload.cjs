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
});
