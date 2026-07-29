import subprocess
import sys

# Use sys.executable so subprocesses run in the same venv as run_all.py itself.
PY = sys.executable

# Run all pipeline steps in order. Each script exits 1 on failure — run_all stops immediately.
STEPS = [
    ("Pre-flight: connection check", [PY, "scripts/check_connection.py"]),
    ("Step 1: load graph",           [PY, "scripts/load_graph.py"]),
    ("Step 2: run queries",          [PY, "scripts/query_graph.py"]),
    ("Step 3: export JSONL",         [PY, "scripts/export_graph.py"]),
    ("Step 4: verify counts",        [PY, "scripts/verify.py"]),
]


def main():
    for label, cmd in STEPS:
        print(f"\n>>> {label}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"\nFAILED at: {label} (exit code {result.returncode})")
            sys.exit(1)
    print("\nAll steps completed successfully.")


if __name__ == "__main__":
    main()
