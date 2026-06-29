/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  javstory?: {
    pickFolders?: () => Promise<string[]>;
    getPathForFile?: (file: File) => string;
    isElectron?: boolean;
  };
}
