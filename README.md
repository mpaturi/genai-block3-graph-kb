# Block 3: OMOP Clinical Graph Knowledge Base

A local Neo4j graph database built from Synthea-generated OMOP clinical data.
Models patients, conditions, drugs, and visits as a property graph — enabling
relationship-heavy queries that flat tables cannot answer efficiently.
Runs 4 Cypher queries answering real clinical questions (most common conditions,
drug-condition co-occurrence, high-burden patients, most-visited patients) and
exports patient subgraphs as JSONL for Block 4 RAG ingestion.
