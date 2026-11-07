/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_USE_MOCKS?: string;
  readonly VITE_POS_URL?: string;
  readonly VITE_APP_ENV?: string;
}

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_USE_MOCKS?: string;
  readonly VITE_POS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}