# CCTV AI Core Processing Engine

A standalone Python retail store intelligence engine: real-time video stream processing, object detection (YOLOv8), employee attendance tracking, phone-abuse detection, customer counting, and blacklist security alerts — all written to a local SQLite/JSON store, ready to bridge to Supabase or any external API.

## Run & Operate

### Python CCTV Engine (primary deliverable)

```bash
cd cctv
pip install -r requirements.txt

python engine.py                          # default webcam (falls back to synthetic)
python engine.py --source sample.mp4      # video file
python engine.py --source rtsp://...      # IP camera
python engine.py --no-gui                 # headless / server mode
python engine.py --model yolov8s.pt       # larger model
```

### Node.js workspace (supporting infrastructure)
- `pnpm --filter @workspace/api-server run dev` — run the Express API server (port from env)
- `pnpm run typecheck` — full TypeScript typecheck
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks from OpenAPI spec

## Stack

### Python Engine (`cctv/`)
- Python 3.10+, OpenCV, Ultralytics YOLOv8/v11, NumPy, SQLite3

### Node.js Workspace
- pnpm workspaces, Node.js 24, TypeScript 5.9, Express 5, Drizzle ORM + PostgreSQL, Zod

## Where things live

```
cctv/
├── engine.py          — Entry point & main loop (CCTVEngine class)
├── config.py          — All tunable parameters (zones, employees, thresholds)
├── data_store.py      — SQLite + JSON log persistence layer
├── requirements.txt   — pip dependencies
├── blacklist.json     — Auto-created on first run
├── local_telemetry.db — Auto-created SQLite events database
└── live_stream_events.json — Auto-created NDJSON event log
```

## Architecture decisions

- **Fallback chain**: Primary source → `FALLBACK_SOURCES` list → synthetic matrix frames. The engine NEVER crashes on missing hardware.
- **Mock embeddings**: 8-d cosine-similarity vectors used as face recognition proxies; any real face model (InsightFace, DeepFace) drops in by replacing `_extract_mock_embedding()` in `engine.py`.
- **Event schema designed for Supabase**: `{timestamp, event_type, details}` is the universal shape written to both SQLite and NDJSON; push to Supabase by setting `REMOTE_API_ENDPOINT` + `REMOTE_API_KEY` in `config.py`.
- **DataStore is the only I/O boundary**: All events funnel through `DataStore.log_event()` — swapping the backend requires changing only that class.
- **No GUI dependency at runtime**: `Visualiser` auto-detects `$DISPLAY`; headless mode works without X11.

## Product

Three parallel tracking routines per frame:
- **Employee tracking** — matches faces to roster, logs presence time and register-zone coverage, alerts on cashier absence.
- **Phone abuse detection** — YOLO cell-phone proximity to employees; 5-second sustained detection triggers a WARNING event.
- **Customer & security monitoring** — customer count in zone, periodic density scoring, blacklist face matching with configurable similarity threshold.

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- YOLO downloads model weights on first run (~6 MB for `yolov8n.pt`) — requires internet on first launch.
- Zone pixel coordinates in `config.py` assume `FRAME_WIDTH=960 × FRAME_HEIGHT=540`; recalibrate if you change resolution.
- Phone proximity matching is index-based (not tracked-ID-based) in the mock implementation — sufficient for demo, needs real person tracking IDs for production.
- Do not run `pnpm dev` at workspace root; use workflow names or `pnpm --filter`.

## Pointers

- See `cctv/README.md` for full usage, schema docs, integration guide, and employee/blacklist configuration instructions.
- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.
