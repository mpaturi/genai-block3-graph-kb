# Block 3: OMOP Clinical Graph Implementation Plan

**Goal:** Load Synthea-generated OMOP CSVs into a local Neo4j graph database, run 4 Cypher queries, and export patient subgraphs as JSONL for Block 4 RAG ingestion.

**Architecture:** Neo4j 5.18 Community runs in a Docker container. Python scripts use the official neo4j driver with `UNWIND`-based batch MERGE for idempotent loading. All scripts read credentials from `.env` via python-dotenv and are orchestrated by `scripts/run_all.py`.

**Tech Stack:** Python 3.11, Neo4j 5.18-community (Docker), neo4j driver ≥5.14.0, pandas ≥2.1.0, python-dotenv ≥1.0.0, orjson ≥3.9.0, tqdm ≥4.66.0

## Global Constraints

- Python 3.11
- Neo4j 5.18 Community (Docker image `neo4j:5.18-community`)
- All scripts load credentials via `python-dotenv` from `.env`
- `.env` is git-ignored; `.env.example` is committed
- `data/export/` is git-ignored; `data/raw/*.csv` are committed
- Use Cypher MERGE (not CREATE) for all node/relationship writes — loading must be idempotent
- No cloud services; Neo4j runs on `bolt://localhost:7687`

---

## File map

| File | Task | Purpose |
|---|---|---|
| `docker-compose.yml` | 1 | Neo4j 5.18 container |
| `.env.example` | 1 | Credentials template |
| `requirements.txt` | 1 | Pinned Python deps |
| `.gitignore` | 1 | Ignore `.env`, `data/export/*.jsonl` |
| `scripts/check_connection.py` | 2 | Smoke test Neo4j reachability |
| `scripts/load_graph.py` | 3 | OMOP CSV → Neo4j MERGE |
| `data/raw/*.csv` | 3 | Source OMOP data (manual copy) |
| `scripts/query_graph.py` | 4 | 4 Cypher queries → stdout |
| `scripts/export_graph.py` | 5 | Patient subgraphs → JSONL |
| `data/export/.gitkeep` | 5 | Keeps output dir in git |
| `scripts/run_all.py` | 6 | Orchestrates all steps |
| `scripts/verify.py` | 6 | Count checks vs. CSVs |
| `README.md` | 7 | Setup docs + schema diagram |

---

### Task 1: Docker + Python environment

**Files:** `docker-compose.yml`, `.env.example`, `requirements.txt`, `.gitignore`

**Interfaces:**
- Produces: running Neo4j at `bolt://localhost:7687`, Python env with all deps installed

**Key decisions:**
- Neo4j 5.18-community image with APOC plugin
- Credentials read from `.env` via `${NEO4J_USER}/${NEO4J_PASSWORD}` — no hardcoded values
- Healthcheck polls `cypher-shell` every 10s, up to 10 retries
- Docker Compose reads `.env` from project root automatically

- [x] Create `docker-compose.yml`, `.env.example`, `requirements.txt`; update `.gitignore`
- [x] `cp .env.example .env` and set password
- [x] `docker compose up -d` — wait for `running (healthy)`
- [x] Commit: `feat(setup): add Docker, env template, and Python deps`

---

### Task 2: Connection check script

**Files:** `scripts/check_connection.py`

**Interfaces:**
- Consumes: `.env` credentials, running Neo4j
- Produces: exits 0 and prints `Neo4j connection OK` on success; exits 1 with error on failure

**Key decisions:**
- Catches `ServiceUnavailable` and `AuthError` separately for clear error messages
- Runs `RETURN 1 AS ok` as the simplest possible connectivity test

- [x] Create `scripts/check_connection.py`
- [x] Run — confirm `Neo4j connection OK (bolt://localhost:7687)`
- [x] Commit: `feat(setup): add Neo4j connection smoke test`

---

### Task 3: Graph loader

**Files:** `scripts/load_graph.py`, `data/raw/*.csv`

**Interfaces:**
- Consumes: `data/raw/*.csv`, `.env`, running Neo4j
- Produces: Neo4j graph with Patient, Condition, Drug nodes; HAS_CONDITION, PRESCRIBED relationships; `visit_count` as property on Patient

**Key decisions:**
- UNWIND batch MERGE with `BATCH_SIZE=500` for performance
- Patients loaded first — nodes must exist before relationships
- Only 3 distinct Condition nodes and 6 distinct Drug nodes — Block 1 uses a curated whitelist of SNOMED/RxNorm codes mapped to small synthetic integers
- `condition_name` and `drug_name` resolved via hardcoded reverse-lookup dict in the loader (no `condition_source_value` column exists in the CSVs)
- Condition nodes deduped on `condition_concept_id` before MERGE
- Drug nodes deduped on `drug_concept_id` before MERGE
- `visit_count` computed as visit_occurrence.csv row count per `person_id`, stored on Patient
- HAS_CONDITION MERGE on `(person_id, condition_concept_id, condition_start_date)` — dedup-safe
- PRESCRIBED MERGE on `(person_id, drug_concept_id, drug_exposure_start_date)` — dedup-safe

- [x] Copy OMOP CSVs into `data/raw/` from Block 1
- [x] Run `wc -l data/raw/*.csv` — update Expected Graph Statistics in `docs/spec.md`
- [x] Create `scripts/load_graph.py`
- [x] Run loader — confirm progress bars complete with `Graph load complete.`
- [x] Re-run — confirm identical counts (idempotency)
- [x] Commit: `feat(load): add graph loader and OMOP source CSVs`

---

### Task 4: Query runner

**Files:** `scripts/query_graph.py`

**Interfaces:**
- Consumes: running Neo4j with loaded graph, `.env`
- Produces: 4 formatted result tables printed to stdout

**Key decisions:**
- All 4 queries defined as a dict — easy to add/remove
- Results printed as pandas DataFrames for readable tabular output
- Queries match spec exactly (see `docs/spec.md` Cypher queries section)

- [x] Create `scripts/query_graph.py`
- [x] Run — confirm 4 non-empty result tables printed
- [x] Commit: `feat(query): add 4 Cypher clinical queries`

---

### Task 5: JSONL exporter

**Files:** `scripts/export_graph.py`, `data/export/.gitkeep`

**Interfaces:**
- Consumes: running Neo4j with loaded graph, `.env`
- Produces: `data/export/graph_export.jsonl` — one JSON record per Patient

**Key decisions:**
- One Cypher query fetches all patient subgraphs in a single round trip
- `text` field is a natural-language sentence ready for embedding in Block 4
- Long text strings are not truncated — chunking deferred to Block 4
- `orjson` used for fast binary JSON serialisation
- `data/export/` is git-ignored; `.gitkeep` commits the empty directory

- [x] Create `data/export/.gitkeep`
- [x] Create `scripts/export_graph.py`
- [x] Run — confirm `Exported ~11,424 records to data/export/graph_export.jsonl`
- [x] Spot-check first record: `id`, `text`, `metadata` keys present; `text` is readable
- [x] Commit: `feat(export): add JSONL patient subgraph exporter`

---

### Task 6: Orchestrator and verification script

**Files:** `scripts/run_all.py`, `scripts/verify.py`

**Interfaces:**
- Consumes: all prior scripts, `.env`, `data/raw/*.csv`, running Neo4j
- Produces: `run_all.py` exits 0 if all steps pass; `verify.py` prints PASS/FAIL per check and exits 1 if any fail

**Key decisions:**
- `run_all.py` runs steps as subprocesses — each script stays independently runnable
- `verify.py` computes expected counts from CSVs at runtime — not hardcoded
- HAS_CONDITION count compared against distinct `(person_id, condition_concept_id, condition_start_date)` tuples
- PRESCRIBED count compared against distinct `(person_id, drug_concept_id, drug_exposure_start_date)` tuples
- `visit_count` per patient verified against visit_occurrence.csv grouped counts
- Exit code 1 on any failure — integrates with run_all.py failure detection

- [x] Create `scripts/run_all.py`
- [x] Create `scripts/verify.py`
- [x] Run `python scripts/verify.py` — all checks PASS
- [x] Run `python scripts/run_all.py` — `All steps completed successfully.`
- [x] Commit: `feat(verify): add orchestrator and verification script`

---

### Task 7: README

**Files:** `README.md`

**Interfaces:**
- Consumes: completed project
- Produces: README with setup steps and schema diagram

- [x] Write `README.md` — setup instructions, scripts table, schema diagram reference
- [x] Commit: `docs: add README with schema diagram and setup instructions`
