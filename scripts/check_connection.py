import os
import sys
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

# Load credentials from .env
load_dotenv()


def main():
    try:
        # Read credentials — raises KeyError if any variable is missing from .env
        URI = os.environ["NEO4J_URI"]
        USER = os.environ["NEO4J_USER"]
        PASSWORD = os.environ["NEO4J_PASSWORD"]
        DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

        # Open a driver connection using the Bolt protocol
        driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
        driver.verify_connectivity()

        # Run the simplest possible query to confirm the database is responsive
        with driver.session(database=DATABASE) as session:
            result = session.run("RETURN 1 AS ok")
            assert result.single()["ok"] == 1

        driver.close()
        print(f"Neo4j connection OK ({URI})")

    except KeyError as e:
        # A required variable is missing from .env
        print(f"ERROR: Missing environment variable {e}. Check your .env file.", file=sys.stderr)
        sys.exit(1)

    except ServiceUnavailable as e:
        # Neo4j is not running or the URI is wrong
        print(f"ERROR: Neo4j not reachable at {URI}: {e}", file=sys.stderr)
        sys.exit(1)

    except AuthError as e:
        # Wrong username or password
        print(f"ERROR: Authentication failed for user '{USER}': {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
