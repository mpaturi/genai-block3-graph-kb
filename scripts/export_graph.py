import os
import orjson
from dotenv import load_dotenv
from neo4j import GraphDatabase
from tqdm import tqdm

load_dotenv()

URI = os.environ["NEO4J_URI"]
USER = os.environ["NEO4J_USER"]
PASSWORD = os.environ["NEO4J_PASSWORD"]
DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

EXPORT_PATH = "data/export/graph_export.jsonl"

# Single round-trip: fetch each Patient with all connected conditions and drugs.
EXPORT_QUERY = """
MATCH (p:Patient)
OPTIONAL MATCH (p)-[:HAS_CONDITION]->(c:Condition)
OPTIONAL MATCH (p)-[:PRESCRIBED]->(d:Drug)
RETURN p.person_id           AS person_id,
       p.year_of_birth_band  AS year_of_birth_band,
       p.gender              AS gender,
       p.visit_count         AS visit_count,
       p.latest_sbp          AS latest_sbp,
       p.latest_bmi          AS latest_bmi,
       p.latest_glucose      AS latest_glucose,
       p.latest_hba1c        AS latest_hba1c,
       collect(DISTINCT c.condition_name) AS conditions,
       collect(DISTINCT d.drug_name)      AS drugs
ORDER BY person_id
"""


def build_text(row):
    """Build a natural-language sentence ready for embedding in Block 4."""
    conditions = ", ".join(row["conditions"]) if row["conditions"] else "none"
    drugs = ", ".join(row["drugs"]) if row["drugs"] else "none"

    # Only mention a lab if the patient has a value for it — order matches the
    # spec example: HbA1c, Glucose, SBP, BMI
    lab_parts = []
    if row["latest_hba1c"] is not None:
        lab_parts.append(f"HbA1c {row['latest_hba1c']:g}%")
    if row["latest_glucose"] is not None:
        lab_parts.append(f"Glucose {row['latest_glucose']:g} mg/dL")
    if row["latest_sbp"] is not None:
        lab_parts.append(f"SBP {row['latest_sbp']:g} mmHg")
    if row["latest_bmi"] is not None:
        lab_parts.append(f"BMI {row['latest_bmi']:g}")
    labs_sentence = f" Latest labs: {', '.join(lab_parts)}." if lab_parts else ""

    return (
        f"Patient {row['person_id']}, born in the {row['year_of_birth_band']}, "
        f"{row['gender']}. "
        f"Conditions: {conditions}. "
        f"Drugs: {drugs}. "
        f"Visits: {row['visit_count']}."
        f"{labs_sentence}"
    )


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        with driver.session(database=DATABASE) as session:
            records = list(session.run(EXPORT_QUERY))
    finally:
        driver.close()

    with open(EXPORT_PATH, "wb") as f:
        for record in tqdm(records, desc="Exporting"):
            row = record.data()
            doc = {
                "id": f"patient_{row['person_id']}",
                "text": build_text(row),
                "metadata": {
                    "person_id": row["person_id"],
                    "year_of_birth_band": row["year_of_birth_band"],
                    "gender": row["gender"],
                    "condition_count": len(row["conditions"]),
                    "conditions": row["conditions"],
                    "drug_count": len(row["drugs"]),
                    "drugs": row["drugs"],
                    "visit_count": row["visit_count"],
                    "latest_sbp": row["latest_sbp"],
                    "latest_bmi": row["latest_bmi"],
                    "latest_glucose": row["latest_glucose"],
                    "latest_hba1c": row["latest_hba1c"],
                },
            }
            f.write(orjson.dumps(doc) + b"\n")

    print(f"Exported {len(records)} records to {EXPORT_PATH}")


if __name__ == "__main__":
    main()
