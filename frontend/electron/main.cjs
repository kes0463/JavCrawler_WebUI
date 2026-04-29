const { app, BrowserWindow, shell } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const net = require("net");

const API_PORT = 8765;
const IS_DEV = process.env.NODE_ENV === "development";

let apiProcess = null;
let mainWindow = null;

// ── FastAPI 서버 시작 ─────────────────────────────────────────────

function findPython() {
  const candidates = [
    path.join(__dirname, "../../venv/Scripts/python.exe"),
    path.join(__dirname, "../../venv/bin/python"),
    "python",
  ];
  return candidates[0]; // venv 우선
}

function startApiServer() {
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
    },
    show: false,
  });

  const url = IS_DEV
    ? "http://localhost:5173"
    : `file://${path.join(__dirname, "../dist/index.html")}`;

  mainWindow.loadURL(url);

  mainWindow.once("ready-to-show", () => mainWindow.show());

  // 외부 링크는 기본 브라우저로
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

// ── 앱 생명주기 ──────────────────────────────────────────────────

app.whenReady().then(async () => {
  startApiServer();
  try {
    await waitForPort(API_PORT);
  } catch (e) {
    console.error("[Electron] API 서버 응답 없음:", e.message);
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
