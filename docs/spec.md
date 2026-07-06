# Block 3 Specification

## Project title

Knowledge Base in a Graph DB — OMOP Clinical Graph for RAG

## Acceptance criteria

> **Project — Build a graph knowledge base**
> Acceptance criteria (done = all true):
> A relationship-heavy dataset (reuse Block 1–2 output where it fits) is modelled
> and loaded into Neo4j via a reproducible script; ≥3 meaningful queries answer
> real questions; schema diagram in README. This becomes the data source for the
> RAG project.

## Goal

Build a graph knowledge base from the OMOP clinical dataset so that:
- patient-condition-drug relationships are modelled as a graph in Neo4j
- the graph is loaded via a reproducible Python script
- ≥3 Cypher queries answer real clinical questions
- the graph is exported in a format ready for Block 4 RAG ingestion (Pinecone)
- Neo4j runs locally via Docker — no cloud infrastructure required

## Problem statement

Blocks 1 and 2 produced a clean partitioned dataset of OMOP clinical data. A flat
Parquet table is good for analytics but poor at answering relationship-heavy questions
like "which drugs are co-prescribed with diabetes?" or "which patients carry the
highest clinical burden?". A graph database models these relationships natively —
each patient, condition, and drug is a node; diagnoses and prescriptions are edges.
This structure makes relationship queries fast and expressive, and produces a richer
corpus for RAG than a flat table.

## Relationship to Blocks 1 and 2

Data source: `data/raw/*.csv` are the original Synthea-generated OMOP CSV files
from Block 1, copied manually into this repo. They are the same files uploaded
to S3 in Block 2.

Block 1 and 2 artifacts reused:
- `data/raw/*.csv` source files: person.csv, condition_occurrence.csv,
  drug_exposure.csv, visit_occurrence.csv
- OMOP schema and domain knowledge from Block 1 validation logic

Block 1 and 2 artifacts NOT reused:
- AWS Glue, S3, Athena, Terraform — all infrastructure stays in AWS;
  Block 3 runs fully locally
- PySpark — replaced by pandas for local CSV reading

## Architecture

```
Pre-flight:
scripts/check_connection.py  (verify Neo4j is reachable before any data operation)

Data pipeline:
OMOP CSVs (data/raw/)
       ↓
scripts/load_graph.py        (pandas → Neo4j driver → Cypher MERGE)
       ↓
Neo4j (Docker, bolt://localhost:7687)
       ↓
scripts/query_graph.py       (4 Cypher queries → results logged to stdout)
       ↓
scripts/export_graph.py      (patient subgraphs → data/export/graph_export.jsonl)
       ↓
Block 4 RAG pipeline (Pinecone ingestion)

Orchestration: scripts/run_all.py runs pre-flight + pipeline in sequence.
```

## Tech stack

| Component | Version |
|---|---|
| Neo4j | 5.18 Community + APOC |
| Python | 3.11 |
| neo4j (driver) | ≥5.14.0 |
| pandas | ≥2.1.0 |
| pyarrow | ≥14.0.0 — pandas CSV backend; also enables Parquet output if needed in Phase 4+ |
| python-dotenv | ≥1.0.0 |
| orjson | ≥3.9.0 |
| tqdm | ≥4.66.0 |

## Credentials and configuration

Neo4j connection config is stored in `.env` (git-ignored). `.env.example` is committed as a template.
Required variables: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`.
All scripts load credentials via `python-dotenv`.

## Graph schema

### Nodes

| Label | Properties | Source |
|---|---|---|
| `Patient` | `person_id`, `year_of_birth`, `year_of_birth_band`, `gender`, `race` | person.csv |
| `Condition` | `condition_concept_id`, `condition_name` | condition_occurrence.csv |
| `Drug` | `drug_concept_id`, `drug_name` | drug_exposure.csv |
| `Visit` | `visit_occurrence_id`, `visit_start_date`, `visit_type` | visit_occurrence.csv |

> **Note on concept names:** Synthea-generated OMOP CSVs include
> `condition_source_value` (human-readable condition name) in
> condition_occurrence.csv and `drug_source_value` (drug name) in
> drug_exposure.csv. These are used as `condition_name` and `drug_name`
> on nodes. If these fields are empty in the actual CSVs, fall back to
> `condition_concept_id` and `drug_concept_id` as the display value.
> Verify before Phase 3 begins.

### Relationships

| Relationship | From → To | Properties |
|---|---|---|
| `HAS_CONDITION` | Patient → Condition | `condition_start_date` |
| `PRESCRIBED` | Patient → Drug | `drug_exposure_start_date` |
| `HAD_VISIT` | Patient → Visit | — |

### Constraints and indexes

- Unique constraint on `Patient.person_id`
- Unique constraint on `Condition.condition_concept_id`
- Unique constraint on `Drug.drug_concept_id`
- Unique constraint on `Visit.visit_occurrence_id`
- Index on `Patient.year_of_birth_band`

## Expected graph statistics

These are the target counts verify.py checks against after a successful load.
Exact numbers confirmed from Block 1/2 source data:

| Metric | Expected |
|---|---|
| Patient nodes | ~1,000 (matches person.csv row count) |
| Condition nodes | ~400 distinct conditions |
| Drug nodes | ~300 distinct drugs |
| HAS_CONDITION relationships | distinct (person_id, condition_concept_id, condition_start_date) tuples in condition_occurrence.csv |
| PRESCRIBED relationships | distinct (person_id, drug_concept_id, drug_exposure_start_date) tuples in drug_exposure.csv |
| HAD_VISIT relationships | ~20,000 (matches visit_occurrence.csv rows) |
| Export records (JSONL) | matches Patient node count |

> **Note:** Exact counts must be confirmed by running `wc -l` on each CSV before
> Phase 3. Update this table with actual numbers at that time.

## Cypher queries

**Q1 — Top 10 most common conditions**
```cypher
MATCH (p:Patient)-[:HAS_CONDITION]->(c:Condition)
RETURN c.condition_name AS condition, count(p) AS patient_count
ORDER BY patient_count DESC
LIMIT 10
```

**Q2 — Drug-condition co-occurrence**
```cypher
MATCH (p:Patient)-[:HAS_CONDITION]->(c:Condition),
      (p)-[:PRESCRIBED]->(d:Drug)
RETURN c.condition_name AS condition,
       d.drug_name AS drug,
       count(p) AS patient_count
ORDER BY patient_count DESC
LIMIT 20
```

**Q3 — High-burden patients (most conditions + drugs combined)**
```cypher
MATCH (p:Patient)
OPTIONAL MATCH (p)-[:HAS_CONDITION]->(c:Condition)
OPTIONAL MATCH (p)-[:PRESCRIBED]->(d:Drug)
RETURN p.person_id AS patient_id,
       p.year_of_birth_band AS birth_band,
       count(DISTINCT c) AS condition_count,
       count(DISTINCT d) AS drug_count,
       count(DISTINCT c) + count(DISTINCT d) AS total_burden
ORDER BY total_burden DESC
LIMIT 10
```

**Q4 — Patients with the most visits**
```cypher
MATCH (p:Patient)-[:HAD_VISIT]->(v:Visit)
RETURN p.person_id AS patient_id,
       count(v) AS visit_count
ORDER BY visit_count DESC
LIMIT 10
```

## Export design (Block 4 RAG)

Each patient subgraph is serialized as a natural-language text summary and exported
as JSON Lines (one record per patient). Example record:

```json
{
  "id": "patient_123",
  "text": "Patient 123, born in the 1970s, male. Conditions: Type 2 diabetes mellitus, Essential hypertension. Drugs: Metformin, Lisinopril. Visits: 3.",
  "metadata": {
    "person_id": 123,
    "year_of_birth_band": "1970s",
    "gender": "M",
    "condition_count": 2,
    "drug_count": 2
  }
}
```

The `text` field gets embedded by Block 4; `metadata` enables filtered retrieval
in Pinecone.

## Phases

| Phase | Branch | Deliverables |
|---|---|---|
| 1 | `phase-1-spec` | `docs/spec.md`, `docs/plan.md`, `docs/tasks.md`, `docs/schema.svg` |
| 2 | `phase-2-setup` | `docker-compose.yml`, `.env.example`, `requirements.txt`, `scripts/check_connection.py` |
| 3 | `phase-3-load` | `scripts/load_graph.py`, `data/raw/*.csv` |
| 4 | `phase-4-query-export` | `scripts/query_graph.py`, `scripts/export_graph.py` |
| 5 | `phase-5-verify` | `scripts/run_all.py`, `scripts/verify.py`, `README.md` |

## Scope

- `data/raw/*.csv` are committed to git in this repo (unlike Block 2 where they
  lived in S3). File sizes are small (~5MB total for Synthea output) so committing
  is acceptable. `data/export/` is git-ignored (generated output).

Block 3 does not include:
- Cloud-hosted Neo4j (AuraDB) — local Docker only
- Additional embedding or vector operations — those belong to Block 4
- Real-time data loading or streaming
- Additional OMOP tables beyond person, condition_occurrence, drug_exposure, visit_occurrence

## Functional requirements

Block 3 must:
1. Run Neo4j locally via Docker (`docker compose up -d`).
2. Load OMOP data into Neo4j via a reproducible Python script.
3. Use MERGE statements for idempotent loading — re-running produces the same graph.
4. Create 4 Cypher queries answering real clinical questions.
5. Export patient subgraphs as JSONL for Block 4 RAG ingestion.
6. Document the graph schema in the README with a diagram.
7. Include a connection check script (smoke test).
8. All scripts runnable from a single command (`python scripts/run_all.py`).
9. Verification script (`scripts/verify.py`) must confirm:
   - Neo4j is reachable
   - Patient node count matches person.csv row count
   - Condition node count matches distinct condition_concept_id count in condition_occurrence.csv
   - Drug node count matches distinct drug_concept_id count in drug_exposure.csv
   - HAS_CONDITION relationship count matches distinct (person_id, condition_concept_id, condition_start_date) tuples in condition_occurrence.csv
   - PRESCRIBED relationship count matches distinct (person_id, drug_concept_id, drug_exposure_start_date) tuples in drug_exposure.csv
   - HAD_VISIT relationship count matches visit_occurrence.csv row count
   - `data/export/graph_export.jsonl` exists and record count matches Patient node count

## Success criteria

Block 3 is complete when:
- `docker compose up -d` starts Neo4j without errors
- `scripts/load_graph.py` loads all OMOP data idempotently
- 4 Cypher queries return meaningful clinical results
- `scripts/export_graph.py` produces `data/export/graph_export.jsonl`
- Schema diagram is in the README
- README documents the AI-assisted workflow
- `scripts/verify.py` passes all node/relationship count checks