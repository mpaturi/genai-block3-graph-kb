import os
import sys
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

load_dotenv()

DATA_DIR = "data/raw"
EXPORT_PATH = "data/export/graph_export.jsonl"

PASS = "PASS"
FAIL = "FAIL"


def check(label, actual, expected):
    status = PASS if actual == expected else FAIL
    print(f"  [{status}] {label}: expected {expected}, got {actual}")
    return status == PASS


def main():
    results = []

    # --- Credentials ---
    try:
        URI = os.environ["NEO4J_URI"]
        USER = os.environ["NEO4J_USER"]
        PASSWORD = os.environ["NEO4J_PASSWORD"]
        DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")
    except KeyError as e:
        print(f"ERROR: Missing environment variable {e}. Check your .env file.", file=sys.stderr)
        sys.exit(1)

    # --- Neo4j connectivity ---
    try:
        driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
        driver.verify_connectivity()
        print(f"  [{PASS}] Neo4j reachable at {URI}")
        results.append(True)
    except (ServiceUnavailable, AuthError) as e:
        print(f"  [{FAIL}] Neo4j not reachable: {e}")
        sys.exit(1)

    try:
        # --- Expected counts from CSVs ---
        persons = pd.read_csv(f"{DATA_DIR}/person.csv")
        # Drop null year_of_birth — loader skips these rows
        persons = persons.dropna(subset=["year_of_birth"])
        # Loader uses MERGE on person_id so duplicate person rows collapse to one node
        expected_patients = persons["person_id"].nunique()
        valid_pids = set(persons["person_id"].unique())

        conditions = pd.read_csv(f"{DATA_DIR}/condition_occurrence.csv")
        conditions = conditions.dropna(subset=["condition_concept_id", "person_id", "condition_start_date"])
        expected_conditions = conditions["condition_concept_id"].nunique()  # before filter
        # Only count relationships for patients that were actually loaded
        conditions = conditions[conditions["person_id"].isin(valid_pids)]
        expected_has_condition = conditions.drop_duplicates(
            subset=["person_id", "condition_concept_id", "condition_start_date"]
        ).shape[0]

        drugs = pd.read_csv(f"{DATA_DIR}/drug_exposure.csv")
        drugs = drugs.dropna(subset=["drug_concept_id", "person_id", "drug_exposure_start_date"])
        expected_drugs = drugs["drug_concept_id"].nunique()  # before filter
        drugs = drugs[drugs["person_id"].isin(valid_pids)]
        expected_prescribed = drugs.drop_duplicates(
            subset=["person_id", "drug_concept_id", "drug_exposure_start_date"]
        ).shape[0]

        visits = pd.read_csv(f"{DATA_DIR}/visit_occurrence.csv")
        # Sum only visits for loaded patients
        visits = visits[visits["person_id"].isin(valid_pids)]
        expected_visit_total = len(visits)

        # --- Neo4j counts ---
        with driver.session(database=DATABASE) as session:
            actual_patients   = session.run("MATCH (p:Patient)   RETURN count(p) AS n").single()["n"]
            actual_conditions = session.run("MATCH (c:Condition) RETURN count(c) AS n").single()["n"]
            actual_drugs      = session.run("MATCH (d:Drug)      RETURN count(d) AS n").single()["n"]
            actual_has_cond   = session.run("MATCH ()-[r:HAS_CONDITION]->() RETURN count(r) AS n").single()["n"]
            actual_prescribed = session.run("MATCH ()-[r:PRESCRIBED]->()   RETURN count(r) AS n").single()["n"]
            # Sum of visit_count across all patients must equal total rows in visit_occurrence.csv
            actual_visit_total = session.run(
                "MATCH (p:Patient) RETURN sum(p.visit_count) AS n"
            ).single()["n"]

    finally:
        driver.close()

    # --- Comparisons ---
    print("\nNode counts:")
    results.append(check("Patient nodes",   actual_patients,   expected_patients))
    results.append(check("Condition nodes", actual_conditions, expected_conditions))
    results.append(check("Drug nodes",      actual_drugs,      expected_drugs))

    print("\nRelationship counts:")
    results.append(check("HAS_CONDITION", actual_has_cond,   expected_has_condition))
    results.append(check("PRESCRIBED",    actual_prescribed, expected_prescribed))

    print("\nVisit counts:")
    results.append(check(
        "sum(Patient.visit_count) == visit_occurrence.csv rows",
        actual_visit_total,
        expected_visit_total,
    ))

    # --- JSONL export ---
    print("\nExport file:")
    if not os.path.exists(EXPORT_PATH):
        print(f"  [{FAIL}] {EXPORT_PATH} does not exist")
        results.append(False)
    else:
        with open(EXPORT_PATH, "rb") as f:
            export_count = sum(1 for _ in f)
        results.append(check(f"{EXPORT_PATH} record count", export_count, actual_patients))

    # --- Summary ---
    print()
    if all(results):
        print("All checks PASSED.")
        sys.exit(0)
    else:
        failed = results.count(False)
        print(f"{failed} check(s) FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
