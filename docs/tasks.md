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

- [x] Create `scripts/query_graph.py` (Q1–Q4)
- [x] Run queries — confirm 4 result tables with non-empty rows
- [x] Create `data/export/.gitkeep`
- [x] Create `scripts/export_graph.py`
- [x] Run exporter — confirm ~11,424 records in `data/export/graph_export.jsonl`
- [x] Spot-check JSONL output (valid JSON, readable `text` field)
- [x] Commit `scripts/query_graph.py`, `scripts/export_graph.py`, `data/export/.gitkeep`

## Phase 5 — Verify (`phase-5-verify`)

- [x] Create `scripts/run_all.py`
- [x] Create `scripts/verify.py`
- [x] Run `python scripts/verify.py` — all checks PASS
- [x] Run `python scripts/run_all.py` — all steps complete
- [x] Write `README.md` (setup steps + schema diagram)
- [x] Commit `scripts/run_all.py`, `scripts/verify.py`, `README.md`
- [x] Push `phase-5-verify` to GitHub — PR2 ready for mentor review

## Phase 6 — Data Expansion (`phase-6-data-expansion`)

- [x] Expand CONDITION_NAMES in `scripts/load_graph.py` from 3 to 11 conditions
- [x] Expand DRUG_NAMES in `scripts/load_graph.py` from 6 to 17 drugs
- [x] Add `data/raw/measurement.csv` (24,616 rows; 4 concept IDs: SBP, BMI, Glucose, HbA1c)
- [x] Add `load_measurements()` to `scripts/load_graph.py` — sets `latest_sbp`, `latest_bmi`, `latest_glucose`, `latest_hba1c` as Patient properties
- [x] Filter sentinel -1.0 values (`value_as_number > 0`) before sort/dedup
- [x] Use `MATCH` (not `MERGE`) so measurement rows for unloaded patients are skipped
- [x] Update `scripts/export_graph.py` EXPORT_QUERY to fetch 4 lab fields
- [x] Update `build_text()` to include "Latest labs:" sentence
- [x] Update `metadata` dict in export to include 4 lab fields
- [x] Run `python scripts/verify.py` — all 7 checks pass, 11,436 records confirmed
- [x] Update `docs/spec.md` and `docs/tasks.md` for Phase 6
- [x] Update `README.md` for Phase 6
- [x] Commit: `feat(phase6): expand to 11 conditions/17 drugs, add measurement data as Patient properties, update JSONL export with lab values`
- [x] Push `phase-6-data-expansion` and open PR
