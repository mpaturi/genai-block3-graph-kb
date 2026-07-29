# Block 3 Tasks

## Phase 1 — Spec (`phase-1-spec`)

- [x] Write `docs/spec.md`
- [x] Write `docs/plan.md`
- [x] Write `docs/tasks.md`
- [x] Commit `docs/spec.md`, `docs/plan.md`, `docs/tasks.md`, `docs/schema.svg` to branch `phase-1-spec`
- [x] Push `phase-1-spec` to GitHub and open PR1 (spec review)

## Phase 2 — Setup (`phase-2-setup`)

- [x] Create `docker-compose.yml` (Neo4j 5.18 + APOC, credentials from `.env`)
- [x] Create `.env.example`
- [x] Create `requirements.txt`
- [x] Update `.gitignore` (add `.env`, `data/export/*.jsonl`)
- [x] Install Python dependencies (`pip install -r requirements.txt`)
- [x] Start Neo4j and confirm healthy (`docker compose up -d`)
- [x] Create `scripts/check_connection.py`
- [x] Run connection smoke test — confirm `Neo4j connection OK`
- [x] Commit Phase 2 files to branch `phase-2-setup`

## Phase 3 — Load (`phase-3-load`)

- [x] Copy OMOP CSVs into `data/raw/` (person, condition_occurrence, drug_exposure, visit_occurrence)
- [x] Record actual row counts; update Expected Graph Statistics in `docs/spec.md`
- [x] Create `scripts/load_graph.py`
- [x] Run loader — confirm progress bars complete
- [x] Re-run loader — confirm idempotency (same counts)
- [x] Commit `scripts/load_graph.py` and `data/raw/*.csv` to branch `phase-3-load`

## Phase 4 — Query + Export (`phase-4-query-export`)

- [ ] Create `scripts/query_graph.py` (Q1–Q4)
- [ ] Run queries — confirm 4 result tables with non-empty rows
- [ ] Create `data/export/.gitkeep`
- [ ] Create `scripts/export_graph.py`
- [ ] Run exporter — confirm ~11,424 records in `data/export/graph_export.jsonl`
- [ ] Spot-check JSONL output (valid JSON, readable `text` field)
- [ ] Commit `scripts/query_graph.py`, `scripts/export_graph.py`, `data/export/.gitkeep`

## Phase 5 — Verify (`phase-5-verify`)

- [ ] Create `scripts/run_all.py`
- [ ] Create `scripts/verify.py`
- [ ] Run `python scripts/verify.py` — all checks PASS
- [ ] Run `python scripts/run_all.py` — all steps complete
- [ ] Write `README.md` (setup steps + schema diagram)
- [ ] Commit `scripts/run_all.py`, `scripts/verify.py`, `README.md`
- [ ] Push `phase-5-verify` to GitHub — PR2 ready for mentor review
