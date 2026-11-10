/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Set to "1" to serve the meta fixture instead of calling the backend. */
  readonly VITE_USE_FIXTURES?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
