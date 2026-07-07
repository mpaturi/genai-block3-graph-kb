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

# All name lookups below use Block 1's synthetic integer concept IDs (not standard OMOP vocab).
# Source: genai-block1-batch-pipeline/src/concepts.py

# gender_concept_id -> human-readable gender
GENDER_NAMES = {
    1: "Male",
    2: "Female",
}

# race_concept_id -> human-readable race
RACE_NAMES = {
    1: "White",
    2: "Black",
    3: "Asian",
    4: "Hawaiian",
    5: "Native",
    6: "Other",
}

# condition_concept_id -> human-readable name
CONDITION_NAMES = {
    1: "Diabetes mellitus type 2",
    2: "Essential hypertension",
    3: "Hyperlipidemia",
}

# drug_concept_id -> drug name (from Block 1 src/concepts.py)
DRUG_NAMES = {
    1: "Metformin",
    2: "Humulin insulin",
    3: "Lisinopril",
    4: "Amlodipine",
    5: "Hydrochlorothiazide",
    6: "Simvastatin",
}


def create_constraints(session):
    """Create unique constraints and indexes so MERGE is safe and fast."""
    cmds = [
        "CREATE CONSTRAINT patient_id IF NOT EXISTS FOR (p:Patient) REQUIRE p.person_id IS UNIQUE",
        "CREATE CONSTRAINT condition_id IF NOT EXISTS FOR (c:Condition) REQUIRE c.condition_concept_id IS UNIQUE",
        "CREATE CONSTRAINT drug_id IF NOT EXISTS FOR (d:Drug) REQUIRE d.drug_concept_id IS UNIQUE",
        "CREATE INDEX patient_birth_band IF NOT EXISTS FOR (p:Patient) ON (p.year_of_birth_band)",
    ]
    for cmd in cmds:
        session.run(cmd)
    print("Constraints and indexes ready.")


def birth_band(year):
    """Convert a birth year to a decade band, e.g. 1975 -> '1970s'."""
    return f"{(int(year) // 10) * 10}s"


def merge_batches(session, query, rows, desc):
    """Send rows to Neo4j in chunks of BATCH_SIZE using UNWIND."""
    for i in tqdm(range(0, len(rows), BATCH_SIZE), desc=desc):
        session.run(query, rows=rows[i: i + BATCH_SIZE])


def load_patients(session):
    """Load Patient nodes with visit_count computed from visit_occurrence.csv."""
    persons = pd.read_csv(f"{DATA_DIR}/person.csv")
    visits = pd.read_csv(f"{DATA_DIR}/visit_occurrence.csv")

    # Drop rows missing year_of_birth — can't build a valid Patient node without it
    before = len(persons)
    persons = persons.dropna(subset=["year_of_birth"])
    dropped = before - len(persons)
    if dropped:
        print(f"  Skipped {dropped} person rows with null year_of_birth")

    # Count visits per person so we can store it directly on the Patient node
    visit_counts = visits.groupby("person_id").size().reset_index(name="visit_count")
    df = persons.merge(visit_counts, on="person_id", how="left")
    df["visit_count"] = df["visit_count"].fillna(0).astype(int)

    rows = [
        {
            "person_id": int(r["person_id"]),
            "year_of_birth": int(r["year_of_birth"]),
            "year_of_birth_band": birth_band(r["year_of_birth"]),
            "gender": GENDER_NAMES.get(int(r.get("gender_concept_id") or 0), "unknown"),
            "race": RACE_NAMES.get(int(r.get("race_concept_id") or 0), "unknown"),
            "visit_count": int(r["visit_count"]),
        }
        for r in df.to_dict("records")
    ]
    merge_batches(
        session,
        """
        UNWIND $rows AS r
        MERGE (p:Patient {person_id: r.person_id})
        SET p.year_of_birth      = r.year_of_birth,
            p.year_of_birth_band = r.year_of_birth_band,
            p.gender             = r.gender,
            p.race               = r.race,
            p.visit_count        = r.visit_count
        """,
        rows,
        "Patients",
    )


def load_conditions(session):
    """Load Condition nodes (3 distinct) and HAS_CONDITION relationships."""
    df = pd.read_csv(f"{DATA_DIR}/condition_occurrence.csv")
    df = df.dropna(subset=["condition_concept_id", "person_id", "condition_start_date"])

    # One Condition node per distinct concept_id — look up name from hardcoded dict
    distinct_ids = df["condition_concept_id"].unique().tolist()
    node_rows = [
        {
            "condition_concept_id": int(cid),
            "condition_name": CONDITION_NAMES.get(int(cid), str(int(cid))),
        }
        for cid in distinct_ids
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

    # HAS_CONDITION relationship — MERGE on (person_id, condition_concept_id, condition_start_date)
    # so re-running the loader never creates duplicate edges
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
        MATCH (p:Patient   {person_id: r.person_id})
        MATCH (c:Condition {condition_concept_id: r.condition_concept_id})
        MERGE (p)-[:HAS_CONDITION {condition_start_date: r.condition_start_date}]->(c)
        """,
        rel_rows,
        "HAS_CONDITION",
    )


def load_drugs(session):
    """Load Drug nodes (6 distinct) and PRESCRIBED relationships."""
    df = pd.read_csv(f"{DATA_DIR}/drug_exposure.csv")
    df = df.dropna(subset=["drug_concept_id", "person_id", "drug_exposure_start_date"])

    # One Drug node per distinct concept_id
    distinct_ids = df["drug_concept_id"].unique().tolist()
    node_rows = [
        {
            "drug_concept_id": int(did),
            "drug_name": DRUG_NAMES.get(int(did), str(int(did))),
        }
        for did in distinct_ids
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

    # PRESCRIBED relationship — MERGE on (person_id, drug_concept_id, drug_exposure_start_date)
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
        MATCH (d:Drug    {drug_concept_id: r.drug_concept_id})
        MERGE (p)-[:PRESCRIBED {drug_exposure_start_date: r.drug_exposure_start_date}]->(d)
        """,
        rel_rows,
        "PRESCRIBED",
    )


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    with driver.session(database=DATABASE) as session:
        create_constraints(session)
        load_patients(session)   # must run before relationships
        load_conditions(session)
        load_drugs(session)
    driver.close()
    print("Graph load complete.")


if __name__ == "__main__":
    main()
