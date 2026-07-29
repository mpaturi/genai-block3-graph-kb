import os
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.environ["NEO4J_URI"]
USER = os.environ["NEO4J_USER"]
PASSWORD = os.environ["NEO4J_PASSWORD"]
DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

# Q1-Q4 from docs/spec.md
QUERIES = {
    "Q1 — Top 10 most common conditions": """
        MATCH (p:Patient)-[:HAS_CONDITION]->(c:Condition)
        RETURN c.condition_name AS condition, count(p) AS patient_count
        ORDER BY patient_count DESC
        LIMIT 10
    """,
    "Q2 — Drug-condition co-occurrence": """
        MATCH (p:Patient)-[:HAS_CONDITION]->(c:Condition),
              (p)-[:PRESCRIBED]->(d:Drug)
        RETURN c.condition_name AS condition,
               d.drug_name AS drug,
               count(p) AS patient_count
        ORDER BY patient_count DESC
        LIMIT 20
    """,
    "Q3 — High-burden patients (most conditions + drugs combined)": """
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
        MATCH (p:Patient)
        RETURN p.person_id AS patient_id,
               p.visit_count AS visit_count
        ORDER BY visit_count DESC
        LIMIT 10
    """,
}


def main():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        with driver.session(database=DATABASE) as session:
            for title, cypher in QUERIES.items():
                print(f"\n=== {title} ===")
                result = session.run(cypher)
                df = pd.DataFrame([r.data() for r in result])
                print(df.to_string(index=False))
    finally:
        driver.close()


if __name__ == "__main__":
    main()
