PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS projects (
  id          TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  cover_asset TEXT,
  created_at  REAL NOT NULL,
  updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  role        TEXT NOT NULL,
  content     TEXT NOT NULL,
  genspec     TEXT,
  created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id, created_at);

CREATE TABLE IF NOT EXISTS assets (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,
  path        TEXT NOT NULL,
  width       INTEGER,
  height      INTEGER,
  parent_id   TEXT,
  meta        TEXT,
  created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id, created_at);

CREATE TABLE IF NOT EXISTS jobs (
  id              TEXT PRIMARY KEY,
  project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  mode            TEXT NOT NULL,
  genspec         TEXT NOT NULL,
  status          TEXT NOT NULL,
  progress        REAL DEFAULT 0,
  comfy_prompt_id TEXT,
  result_asset    TEXT,
  error           TEXT,
  created_at      REAL NOT NULL,
  updated_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id, created_at);

CREATE TABLE IF NOT EXISTS model_cache (
  model_id    TEXT PRIMARY KEY,
  file        TEXT NOT NULL,
  size_bytes  INTEGER,
  ready       INTEGER NOT NULL DEFAULT 0,
  updated_at  REAL NOT NULL
);
