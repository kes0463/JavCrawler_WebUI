const { app, BrowserWindow, shell, ipcMain, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const net = require("net");

const API_PORT = Number(process.env.JAVSTORY_WEBAPI_PORT || 8765);
const VITE_PORT = Number(process.env.JAVSTORY_VITE_PORT || 5173);
const IS_DEV = process.env.NODE_ENV === "development";

let apiProcess = null;
let mainWindow = null;

if (IS_DEV) {
  // 이전 Electron 인스턴스와 캐시 잠금 충돌 방지
  app.setPath("userData", path.join(app.getPath("appData"), "javstory-electron-dev"));
  app.commandLine.appendSwitch("disable-gpu-shader-disk-cache");
}

// ── FastAPI 서버 시작 ─────────────────────────────────────────────

function findPython() {
  const candidates = [
    path.join(__dirname, "../../venv/Scripts/python.exe"),
    path.join(__dirname, "../../venv/bin/python"),
    "python",
  ];
  return candidates[0]; // venv 우선
}

function allowFrozenApi() {
  const v = (process.env.JAVSTORY_ALLOW_FROZEN_API || "0").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

function startApiServer() {
  if (!allowFrozenApi()) {
    if (IS_DEV) {
      console.log(
        `[API] webapi는 start_web.bat이 포트 ${API_PORT}에서 기동합니다 (legacy api/는 사용하지 않음).`
      );
    }
    return;
  }
  const python = findPython();
  const cwd = path.join(__dirname, "../..");

  apiProcess = spawn(
    python,
    ["-m", "uvicorn", "api.main:app", "--port", String(API_PORT), "--host", "127.0.0.1"],
    { cwd, stdio: IS_DEV ? "inherit" : "ignore" }
  );

  apiProcess.on("error", (err) => {
    console.error("[API] 시작 실패:", err.message);
  });
}

// ── 포트 열릴 때까지 대기 ────────────────────────────────────────

function waitForPort(port, timeout = 15000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    function check() {
      const socket = net.createConnection({ port, host: "127.0.0.1" });
      socket.on("connect", () => { socket.destroy(); resolve(); });
      socket.on("error", () => {
        socket.destroy();
        if (Date.now() - start > timeout) return reject(new Error("서버 시작 시간 초과"));
        setTimeout(check, 300);
      });
    }
    check();
  });
}

// ── BrowserWindow 생성 ───────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 600,
    backgroundColor: "#09090e",
    titleBarStyle: "hidden",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.cjs"),
    },
    show: false,
  });

  const url = IS_DEV
    ? `http://localhost:${VITE_PORT}`
    : `file://${path.join(__dirname, "../dist/index.html")}`;

  mainWindow.loadURL(url);

  mainWindow.once("ready-to-show", () => mainWindow.show());

  const notifyMaximized = () => {
    if (!mainWindow?.webContents) return;
    mainWindow.webContents.send("window:maximized-changed", mainWindow.isMaximized());
  };
  mainWindow.on("maximize", notifyMaximized);
  mainWindow.on("unmaximize", notifyMaximized);

  // 외부 링크는 기본 브라우저로
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

function registerWindowIpc() {
  ipcMain.handle("window:minimize", () => {
    const win = BrowserWindow.getFocusedWindow() ?? mainWindow;
    win?.minimize();
  });

  ipcMain.handle("window:maximize", () => {
    const win = BrowserWindow.getFocusedWindow() ?? mainWindow;
    if (!win) return false;
    if (win.isMaximized()) win.unmaximize();
    else win.maximize();
    return win.isMaximized();
  });

  ipcMain.handle("window:close", () => {
    const win = BrowserWindow.getFocusedWindow() ?? mainWindow;
    win?.close();
  });

  ipcMain.handle("window:is-maximized", () => {
    const win = BrowserWindow.getFocusedWindow() ?? mainWindow;
    return win?.isMaximized() ?? false;
  });
}

// ── 앱 생명주기 ──────────────────────────────────────────────────

app.whenReady().then(async () => {
  registerWindowIpc();

  ipcMain.handle("harvest:pick-folders", async () => {
    const cwd = path.join(__dirname, "../..");
    const python = findPython();
    const { spawnSync } = require("child_process");
    const result = spawnSync(
      python,
      ["-m", "javstory.utils.native_folder_picker"],
      { cwd, encoding: "utf-8", timeout: 600_000, windowsHide: false },
    );
    if (result.status === 0 && result.stdout) {
      try {
        const paths = JSON.parse(result.stdout.trim());
        if (Array.isArray(paths)) {
          return paths;
        }
      } catch {
        /* fall through */
      }
    }
    if (result.stderr) {
      console.error("[pick-folders]", result.stderr);
    }
    const win = BrowserWindow.getFocusedWindow() ?? mainWindow;
    const fallback = await dialog.showOpenDialog(win ?? undefined, {
      properties: ["openDirectory", "multiSelections"],
      title: "Harvest 큐에 추가할 폴더 선택 (Ctrl+클릭 다중 선택)",
    });
    if (fallback.canceled) return [];
    return fallback.filePaths;
  });

  startApiServer();
  if (allowFrozenApi()) {
    try {
      await waitForPort(API_PORT);
    } catch (e) {
      console.error("[Electron] API 서버 응답 없음:", e.message);
    }
  }
  createWindow();
});

app.on("window-all-closed", () => {
  if (apiProcess) apiProcess.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
