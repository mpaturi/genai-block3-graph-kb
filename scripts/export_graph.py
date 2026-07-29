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
       collect(DISTINCT c.condition_name) AS conditions,
       collect(DISTINCT d.drug_name)      AS drugs
ORDER BY person_id
"""


def build_text(row):
    """Build a natural-language sentence ready for embedding in Block 4."""
    conditions = ", ".join(row["conditions"]) if row["conditions"] else "none"
    drugs = ", ".join(row["drugs"]) if row["drugs"] else "none"
    return (
        f"Patient {row['person_id']}, born in the {row['year_of_birth_band']}, "
        f"{row['gender']}. "
        f"Conditions: {conditions}. "
        f"Drugs: {drugs}. "
        f"Visits: {row['visit_count']}."
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
                    "drug_count": len(row["drugs"]),
                    "visit_count": row["visit_count"],
                },
            }
            f.write(orjson.dumps(doc) + b"\n")

    print(f"Exported {len(records)} records to {EXPORT_PATH}")


if __name__ == "__main__":
    main()
