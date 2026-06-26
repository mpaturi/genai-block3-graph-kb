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

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `requirements.txt`
- Modify: `.gitignore`

**Interfaces:**
- Produces: running Neo4j at `bolt://localhost:7687`, Python env with all deps installed

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  neo4j:
    image: neo4j:5.18-community
    container_name: neo4j-omop
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=${NEO4J_USER}/${NEO4J_PASSWORD}
      - NEO4J_PLUGINS=["apoc"]
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u ${NEO4J_USER} -p ${NEO4J_PASSWORD} 'RETURN 1' || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10

volumes:
  neo4j_data:
  neo4j_logs:
```

> Docker Compose reads `.env` from the project root automatically — `${NEO4J_USER}` and `${NEO4J_PASSWORD}` are substituted at `docker compose up` time. No hardcoded credentials anywhere.

- [ ] **Step 2: Create `.env.example`**

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=neo4j
```

- [ ] **Step 3: Create `requirements.txt`**

```
neo4j>=5.14.0
pandas>=2.1.0
pyarrow>=14.0.0
python-dotenv>=1.0.0
orjson>=3.9.0
tqdm>=4.66.0
```

- [ ] **Step 4: Update `.gitignore`**

Add these lines if not already present:
```
.env
data/export/*.jsonl
```

- [ ] **Step 5: Install Python dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 6: Create `.env` from template (local only)**

```bash
cp .env.example .env
```

- [ ] **Step 7: Start Neo4j**

```bash
docker compose up -d
```

Expected output includes: `Container neo4j-omop  Started`

- [ ] **Step 8: Wait for healthy status**

```bash
docker compose ps
```

Expected: `neo4j-omop` shows `running (healthy)`. If not yet healthy, wait 15s and re-run.

- [ ] **Step 9: Commit**

```bash
git add docker-compose.yml .env.example requirements.txt .gitignore
git commit -m "feat(setup): add Docker, env template, and Python deps"
```

---

### Task 2: Connection check script

**Files:**
- Create: `scripts/check_connection.py`

**Interfaces:**
- Consumes: `.env` with `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`
- Produces: exits 0 and prints `Neo4j connection OK` on success; exits 1 with error on failure

- [ ] **Step 1: Create `scripts/check_connection.py`**

```python
import os
import sys
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

load_dotenv()

URI = os.environ["NEO4J_URI"]
USER = os.environ["NEO4J_USER"]
PASSWORD = os.environ["NEO4J_PASSWORD"]
DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")


def main():
    try:
        driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
        driver.verify_connectivity()
        with driver.session(database=DATABASE) as session:
            result = session.run("RETURN 1 AS ok")
            assert result.single()["ok"] == 1
        driver.close()
        print(f"Neo4j connection OK ({URI})")
    except ServiceUnavailable as e:
        print(f"ERROR: Neo4j not reachable at {URI}: {e}", file=sys.stderr)
        sys.exit(1)
    except AuthError as e:
        print(f"ERROR: Authentication failed for user '{USER}': {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the connection check**

```bash
python scripts/check_connection.py
```

Expected: `Neo4j connection OK (bolt://localhost:7687)`

- [ ] **Step 3: Commit**

```bash
git add scripts/check_connection.py
git commit -m "feat(setup): add Neo4j connection smoke test"
```

---

### Task 3: Graph loader

**Files:**
- Create: `scripts/load_graph.py`
- Create: `data/raw/person.csv` (manual copy from Block 1/2)
- Create: `data/raw/condition_occurrence.csv` (manual copy from Block 1/2)
- Create: `data/raw/drug_exposure.csv` (manual copy from Block 1/2)
- Create: `data/raw/visit_occurrence.csv` (manual copy from Block 1/2)

**Interfaces:**
- Consumes: `data/raw/*.csv`, `.env`, running Neo4j
- Produces: Neo4j graph with Patient, Condition, Drug, Visit nodes and HAS_CONDITION, PRESCRIBED, HAD_VISIT relationships

- [ ] **Step 1: Copy OMOP CSVs into `data/raw/`**

Manually copy from Block 1/2 output (adjust source path as needed):
```bash
cp /path/to/block1/data/person.csv data/raw/
cp /path/to/block1/data/condition_occurrence.csv data/raw/
cp /path/to/block1/data/drug_exposure.csv data/raw/
cp /path/to/block1/data/visit_occurrence.csv data/raw/
```

Record actual row counts and update Expected Graph Statistics in `docs/spec.md`:
```bash
wc -l data/raw/*.csv
```

- [ ] **Step 2: Verify concept name fields are populated**

Run in a Python REPL before writing the loader:
```python
import pandas as pd
co = pd.read_csv("data/raw/condition_occurrence.csv")
de = pd.read_csv("data/raw/drug_exposure.csv")
print("condition_source_value null %:", co["condition_source_value"].isna().mean())
print("drug_source_value null %:", de["drug_source_value"].isna().mean())
```

If null % is high, the fallback to concept_id applies automatically in the loader (no code change needed).

- [ ] **Step 3: Create `scripts/load_graph.py`**

```python
import os
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase
from tqdm import tqdm

load_dotenv()

URI = os.environ["NEO4J_URI"]
USER = os.environ["NEO4J_USER"]
PASSWORD = os.environ["NEO4J_PASSWORD"]
DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

BATCH_SIZE = 500
DATA_DIR = "data/raw"


def create_constraints(session):
    cmds = [
        "CREATE CONSTRAINT patient_id IF NOT EXISTS FOR (p:Patient) REQUIRE p.person_id IS UNIQUE",
        "CREATE CONSTRAINT condition_id IF NOT EXISTS FOR (c:Condition) REQUIRE c.condition_concept_id IS UNIQUE",
        "CREATE CONSTRAINT drug_id IF NOT EXISTS FOR (d:Drug) REQUIRE d.drug_concept_id IS UNIQUE",
        "CREATE CONSTRAINT visit_id IF NOT EXISTS FOR (v:Visit) REQUIRE v.visit_occurrence_id IS UNIQUE",
        "CREATE INDEX patient_birth_band IF NOT EXISTS FOR (p:Patient) ON (p.year_of_birth_band)",
    ]
    for cmd in cmds:
        session.run(cmd)
    print("Constraints and indexes ready.")


def birth_band(year):
    return f"{(int(year) // 10) * 10}s"


def merge_batches(session, query, rows, desc):
    for i in tqdm(range(0, len(rows), BATCH_SIZE), desc=desc):
        session.run(query, rows=rows[i : i + BATCH_SIZE])


def load_patients(session):
    df = pd.read_csv(f"{DATA_DIR}/person.csv")
    rows = [
        {
            "person_id": int(r["person_id"]),
            "year_of_birth": int(r["year_of_birth"]),
            "year_of_birth_band": birth_band(r["year_of_birth"]),
            "gender": str(r.get("gender_source_value", "unknown") or "unknown"),
            "race": str(r.get("race_source_value", "unknown") or "unknown"),
        }
        for r in df.to_dict("records")
    ]
    merge_batches(
        session,
        """
        UNWIND $rows AS r
        MERGE (p:Patient {person_id: r.person_id})
        SET p.year_of_birth = r.year_of_birth,
            p.year_of_birth_band = r.year_of_birth_band,
            p.gender = r.gender,
            p.race = r.race
        """,
        rows,
        "Patients",
    )


def load_conditions(session):
    df = pd.read_csv(f"{DATA_DIR}/condition_occurrence.csv")
    deduped = df.drop_duplicates(subset=["condition_concept_id"])
    node_rows = [
        {
            "condition_concept_id": int(r["condition_concept_id"]),
            "condition_name": (
                str(r["condition_source_value"]).strip()
                if r.get("condition_source_value") and str(r["condition_source_value"]).strip()
                else str(int(r["condition_concept_id"]))
            ),
        }
        for r in deduped.to_dict("records")
    ]
    merge_batches(
        session,
        """
        UNWIND $rows AS r
        MERGE (c:Condition {condition_concept_id: r.condition_concept_id})
        SET c.condition_name = r.condition_name
        """,
        node_rows,
        "Conditions",
    )
    rel_rows = [
        {
            "person_id": int(r["person_id"]),
            "condition_concept_id": int(r["condition_concept_id"]),
            "condition_start_date": str(r["condition_start_date"]),
        }
        for r in df.to_dict("records")
    ]
    merge_batches(
        session,
        """
        UNWIND $rows AS r
        MATCH (p:Patient {person_id: r.person_id})
        MATCH (c:Condition {condition_concept_id: r.condition_concept_id})
        MERGE (p)-[:HAS_CONDITION {condition_start_date: r.condition_start_date}]->(c)
        """,
        rel_rows,
        "HAS_CONDITION",
    )


def load_drugs(session):
    df = pd.read_csv(f"{DATA_DIR}/drug_exposure.csv")
    deduped = df.drop_duplicates(subset=["drug_concept_id"])
    node_rows = [
        {
            "drug_concept_id": int(r["drug_concept_id"]),
            "drug_name": (
                str(r["drug_source_value"]).strip()
                if r.get("drug_source_value") and str(r["drug_source_value"]).strip()
                else str(int(r["drug_concept_id"]))
            ),
        }
        for r in deduped.to_dict("records")
    ]
    merge_batches(
        session,
        """
        UNWIND $rows AS r
        MERGE (d:Drug {drug_concept_id: r.drug_concept_id})
        SET d.drug_name = r.drug_name
        """,
        node_rows,
        "Drugs",
    )
    rel_rows = [
        {
            "person_id": int(r["person_id"]),
            "drug_concept_id": int(r["drug_concept_id"]),
            "drug_exposure_start_date": str(r["drug_exposure_start_date"]),
        }
        for r in df.to_dict("records")
    ]
    merge_batches(
        session,
        """
        UNWIND $rows AS r
        MATCH (p:Patient {person_id: r.person_id})
        MATCH (d:Drug {drug_concept_id: r.drug_concept_id})
        MERGE (p)-[:PRESCRIBED {drug_exposure_start_date: r.drug_exposure_start_date}]->(d)
        """,
        rel_rows,
        "PRESCRIBED",
    )


def load_visits(session):
    df = pd.read_csv(f"{DATA_DIR}/visit_occurrence.csv")
    rows = [
        {
            "visit_occurrence_id": int(r["visit_occurrence_id"]),
            "person_id": int(r["person_id"]),
            "visit_start_date": str(r["visit_start_date"]),
            "visit_type": str(r.get("visit_source_value", "unknown") or "unknown"),
        }
        for r in df.to_dict("records")
    ]
    merge_batches(
        session,
        """
        UNWIND $rows AS r
        MERGE (v:Visit {visit_occurrence_id: r.visit_occurrence_id})
        SET v.visit_start_date = r.visit_start_date,
            v.visit_type = r.visit_type
        """,
        rows,
        "Visits",
    )
    merge_batches(
        session,
        """
        UNWIND $rows AS r
        MATCH (p:Patient {person_id: r.person_id})
        MATCH (v:Visit {visit_occurrence_id: r.visit_occurrence_id})
        MERGE (p)-[:HAD_VISIT]->(v)
        """,
        rows,
        "HAD_VISIT",
    )


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session(database=DATABASE) as session:
        create_constraints(session)
        load_patients(session)
        load_conditions(session)
        load_drugs(session)
        load_visits(session)
    driver.close()
    print("Graph load complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the loader**

```bash
python scripts/load_graph.py
```

Expected: progress bars for Patients, Conditions, HAS_CONDITION, Drugs, PRESCRIBED, Visits, HAD_VISIT — ending with `Graph load complete.`

- [ ] **Step 5: Verify node counts in Neo4j Browser**

Open `http://localhost:7474`, log in with credentials from your `.env`, run:
```cypher
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count ORDER BY label
```

Expected: non-zero counts for Patient, Condition, Drug, Visit.

- [ ] **Step 6: Verify idempotency**

```bash
python scripts/load_graph.py
```

Expected: identical node/relationship counts as Step 5. No duplicates.

- [ ] **Step 7: Commit**

```bash
git add scripts/load_graph.py data/raw/
git commit -m "feat(load): add graph loader and OMOP source CSVs"
```

---

### Task 4: Query runner

**Files:**
- Create: `scripts/query_graph.py`

**Interfaces:**
- Consumes: running Neo4j with loaded graph, `.env`
- Produces: 4 formatted result tables printed to stdout

- [ ] **Step 1: Create `scripts/query_graph.py`**

```python
import os
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.environ["NEO4J_URI"]
USER = os.environ["NEO4J_USER"]
PASSWORD = os.environ["NEO4J_PASSWORD"]
DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

QUERIES = {
    "Q1 — Top 10 most common conditions": """
        MATCH (p:Patient)-[:HAS_CONDITION]->(c:Condition)
        RETURN c.condition_name AS condition, count(p) AS patient_count
        ORDER BY patient_count DESC
        LIMIT 10
    """,
    "Q2 — Drug-condition co-occurrence (top 20)": """
        MATCH (p:Patient)-[:HAS_CONDITION]->(c:Condition),
              (p)-[:PRESCRIBED]->(d:Drug)
        RETURN c.condition_name AS condition,
               d.drug_name AS drug,
               count(p) AS patient_count
        ORDER BY patient_count DESC
        LIMIT 20
    """,
    "Q3 — High-burden patients (conditions + drugs)": """
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
    """,
    "Q4 — Patients with the most visits": """
        MATCH (p:Patient)-[:HAD_VISIT]->(v:Visit)
        RETURN p.person_id AS patient_id,
               count(v) AS visit_count
        ORDER BY visit_count DESC
        LIMIT 10
    """,
}


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session(database=DATABASE) as session:
        for name, cypher in QUERIES.items():
            print(f"\n{'=' * 60}")
            print(name)
            print("=" * 60)
            result = session.run(cypher)
            df = pd.DataFrame([r.data() for r in result])
            print(df.to_string(index=False))
    driver.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the queries**

```bash
python scripts/query_graph.py
```

Expected: 4 result tables printed. Q1 shows clinical condition names and counts. Q2 shows drug-condition pairs. Q3 shows patients sorted by combined burden. Q4 shows patients ranked by visit count.

- [ ] **Step 3: Commit**

```bash
git add scripts/query_graph.py
git commit -m "feat(query): add 4 Cypher clinical queries"
```

---

### Task 5: JSONL exporter

**Files:**
- Create: `scripts/export_graph.py`
- Create: `data/export/.gitkeep`

**Interfaces:**
- Consumes: running Neo4j with loaded graph, `.env`
- Produces: `data/export/graph_export.jsonl` — one JSON record per Patient

- [ ] **Step 1: Create `data/export/` with a `.gitkeep`**

```bash
mkdir -p data/export
```

Create `data/export/.gitkeep` (empty file). Confirm `.gitignore` already has `data/export/*.jsonl`.

- [ ] **Step 2: Create `scripts/export_graph.py`**

```python
import os
import orjson
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase
from tqdm import tqdm

load_dotenv()

URI = os.environ["NEO4J_URI"]
USER = os.environ["NEO4J_USER"]
PASSWORD = os.environ["NEO4J_PASSWORD"]
DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

OUTPUT_PATH = Path("data/export/graph_export.jsonl")


def fetch_patient_subgraphs(session):
    result = session.run("""
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_CONDITION]->(c:Condition)
        OPTIONAL MATCH (p)-[:PRESCRIBED]->(d:Drug)
        OPTIONAL MATCH (p)-[:HAD_VISIT]->(v:Visit)
        RETURN p.person_id AS person_id,
               p.year_of_birth_band AS year_of_birth_band,
               p.gender AS gender,
               collect(DISTINCT c.condition_name) AS conditions,
               collect(DISTINCT d.drug_name) AS drugs,
               count(DISTINCT v) AS visit_count
        ORDER BY p.person_id
    """)
    return list(result)


def build_record(row):
    person_id = row["person_id"]
    band = row["year_of_birth_band"] or "unknown"
    gender = row["gender"] or "unknown"
    conditions = [c for c in row["conditions"] if c]
    drugs = [d for d in row["drugs"] if d]
    visit_count = row["visit_count"]

    condition_str = ", ".join(conditions) if conditions else "no recorded conditions"
    drug_str = ", ".join(drugs) if drugs else "no recorded drugs"
    text = (
        f"Patient {person_id}, born in the {band}, {gender}. "
        f"Conditions: {condition_str}. "
        f"Drugs: {drug_str}. "
        f"Visits: {visit_count}."
    )
    return {
        "id": f"patient_{person_id}",
        "text": text,
        "metadata": {
            "person_id": person_id,
            "year_of_birth_band": band,
            "gender": gender,
            "condition_count": len(conditions),
            "drug_count": len(drugs),
            "visit_count": visit_count,
        },
    }


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session(database=DATABASE) as session:
        rows = fetch_patient_subgraphs(session)
    driver.close()

    with OUTPUT_PATH.open("wb") as f:
        for row in tqdm(rows, desc="Exporting patients"):
            f.write(orjson.dumps(build_record(row)) + b"\n")

    print(f"Exported {len(rows)} records to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the exporter**

```bash
python scripts/export_graph.py
```

Expected: `Exported ~1000 records to data/export/graph_export.jsonl`

- [ ] **Step 4: Spot-check the output**

```bash
python -c "
import orjson, pathlib
lines = pathlib.Path('data/export/graph_export.jsonl').read_bytes().splitlines()
print(f'{len(lines)} records')
print(orjson.loads(lines[0]))
"
```

Expected: record count ~1000, first record has `id`, `text`, and `metadata` keys. `text` is a readable sentence.

- [ ] **Step 5: Commit**

```bash
git add scripts/export_graph.py data/export/.gitkeep
git commit -m "feat(export): add JSONL patient subgraph exporter"
```

---

### Task 6: Orchestrator and verification script

**Files:**
- Create: `scripts/run_all.py`
- Create: `scripts/verify.py`

**Interfaces:**
- Consumes: all prior scripts, `.env`, `data/raw/*.csv`, running Neo4j
- Produces: `run_all.py` exits 0 if all steps pass; `verify.py` prints PASS/FAIL per check and exits 1 if any fail

- [ ] **Step 1: Create `scripts/run_all.py`**

```python
import subprocess
import sys

STEPS = [
    ("Pre-flight: connection check", ["python", "scripts/check_connection.py"]),
    ("Load graph",                   ["python", "scripts/load_graph.py"]),
    ("Run queries",                  ["python", "scripts/query_graph.py"]),
    ("Export JSONL",                 ["python", "scripts/export_graph.py"]),
    ("Verify",                       ["python", "scripts/verify.py"]),
]


def main():
    for label, cmd in STEPS:
        print(f"\n>>> {label}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"FAILED at: {label}", file=sys.stderr)
            sys.exit(1)
    print("\nAll steps completed successfully.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create `scripts/verify.py`**

```python
import os
import sys
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.environ["NEO4J_URI"]
USER = os.environ["NEO4J_USER"]
PASSWORD = os.environ["NEO4J_PASSWORD"]
DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

DATA_DIR = Path("data/raw")
EXPORT_PATH = Path("data/export/graph_export.jsonl")

passed = 0
failed = 0


def check(label, actual, expected):
    global passed, failed
    ok = actual == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: got {actual}, expected {expected}")
    if ok:
        passed += 1
    else:
        failed += 1


def count(session, query):
    return session.run(query).single()[0]


def row_count(filename):
    return len(pd.read_csv(DATA_DIR / filename))


def distinct_count(filename, column):
    return pd.read_csv(DATA_DIR / filename)[column].nunique()


def main():
    person_count = row_count("person.csv")
    condition_rows = row_count("condition_occurrence.csv")
    condition_distinct = distinct_count("condition_occurrence.csv", "condition_concept_id")
    drug_rows = row_count("drug_exposure.csv")
    drug_distinct = distinct_count("drug_exposure.csv", "drug_concept_id")
    visit_rows = row_count("visit_occurrence.csv")

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        driver.verify_connectivity()
    except Exception as e:
        print(f"[FAIL] Neo4j not reachable: {e}", file=sys.stderr)
        sys.exit(1)

    print("[PASS] Neo4j is reachable")
    passed += 1

    with driver.session(database=DATABASE) as session:
        check("Patient node count",       count(session, "MATCH (p:Patient) RETURN count(p)"),          person_count)
        check("Condition node count",     count(session, "MATCH (c:Condition) RETURN count(c)"),        condition_distinct)
        check("Drug node count",          count(session, "MATCH (d:Drug) RETURN count(d)"),             drug_distinct)
        check("HAS_CONDITION rel count",  count(session, "MATCH ()-[r:HAS_CONDITION]->() RETURN count(r)"), condition_rows)
        check("PRESCRIBED rel count",     count(session, "MATCH ()-[r:PRESCRIBED]->() RETURN count(r)"),    drug_rows)
        check("HAD_VISIT rel count",      count(session, "MATCH ()-[r:HAD_VISIT]->() RETURN count(r)"),     visit_rows)

    driver.close()

    if not EXPORT_PATH.exists():
        print(f"[FAIL] {EXPORT_PATH} does not exist")
        failed += 1
    else:
        jsonl_count = sum(1 for _ in EXPORT_PATH.open("rb"))
        check("Export record count matches Patient nodes", jsonl_count, person_count)

    print(f"\n{passed} passed, {failed} failed")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run verify.py standalone**

```bash
python scripts/verify.py
```

Expected: all checks PASS, `0 failed`.

- [ ] **Step 4: Run end-to-end via run_all.py**

```bash
python scripts/run_all.py
```

Expected: all steps complete, `All steps completed successfully.`

- [ ] **Step 5: Commit**

```bash
git add scripts/run_all.py scripts/verify.py
git commit -m "feat(verify): add orchestrator and verification script"
```

---

### Task 7: README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: completed project
- Produces: README with setup steps and graph schema diagram

- [ ] **Step 1: Write `README.md`**

```markdown
# Block 3: OMOP Clinical Graph Knowledge Base

A local Neo4j graph database built from Synthea-generated OMOP clinical data.
Models patients, conditions, drugs, and visits as a property graph — enabling
relationship-heavy queries that flat tables cannot answer efficiently.
Runs 4 Cypher queries answering real clinical questions (most common conditions,
drug-condition co-occurrence, high-burden patients, most-visited patients) and
exports patient subgraphs as JSONL for Block 4 RAG ingestion.

## Graph schema

![Graph Schema](docs/schema.svg)

```
(Patient)-[:HAS_CONDITION {condition_start_date}]->(Condition)
(Patient)-[:PRESCRIBED {drug_exposure_start_date}]->(Drug)
(Patient)-[:HAD_VISIT]->(Visit)
```

| Label | Key properties |
|---|---|
| `Patient` | `person_id`, `year_of_birth_band`, `gender`, `race` |
| `Condition` | `condition_concept_id`, `condition_name` |
| `Drug` | `drug_concept_id`, `drug_name` |
| `Visit` | `visit_occurrence_id`, `visit_start_date`, `visit_type` |

## Setup

**Prerequisites:** Docker Desktop, Python 3.11

1. Copy OMOP CSVs into `data/raw/`:
   `person.csv`, `condition_occurrence.csv`, `drug_exposure.csv`, `visit_occurrence.csv`

2. Configure credentials:
   ```bash
   cp .env.example .env
   ```

3. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   ```

4. Start Neo4j:
   ```bash
   docker compose up -d
   ```

5. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

6. Run the full pipeline:
   ```bash
   python scripts/run_all.py
   ```

## Scripts

| Script | Purpose |
|---|---|
| `scripts/check_connection.py` | Smoke test — verify Neo4j is reachable |
| `scripts/load_graph.py` | Load OMOP CSVs into Neo4j (idempotent MERGE) |
| `scripts/query_graph.py` | Run 4 Cypher queries and print results |
| `scripts/export_graph.py` | Export patient subgraphs → `data/export/graph_export.jsonl` |
| `scripts/verify.py` | Verify node/relationship counts match source CSVs |
| `scripts/run_all.py` | Run all steps in sequence |

## Output

`data/export/graph_export.jsonl` — one JSON record per patient for Block 4 RAG ingestion.

## AI-assisted workflow

Built with Claude Code (claude-sonnet-4-6) as a pair programmer.
Spec, plan, and all scripts were developed collaboratively with AI assistance.
```

- [ ] **Step 2: Commit README**

```bash
git add README.md
git commit -m "docs: add README with schema diagram and setup instructions"
```
