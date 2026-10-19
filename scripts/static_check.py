"""Dependency-free release preflight. Does NOT substitute for Django/MySQL integration tests."""
from pathlib import Path
import ast
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []
files = list(ROOT.rglob("*.py"))
for file in files:
    try:
        ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    except SyntaxError as exc:
        errors.append(str(exc))

schema = (ROOT / "mysql/01_schema_mysql.sql").read_text(encoding="utf-8")
routines = (ROOT / "mysql/02_programmability.sql").read_text(encoding="utf-8")
expected_tables = ["monitor_sensor", "monitor_rule", "monitor_reading", "monitor_alert",
                   "monitor_alert_audit", "monitor_daily_summary"]
for table in expected_tables:
    if not re.search(r"CREATE TABLE IF NOT EXISTS\s+" + table + r"\s*\(", schema):
        errors.append(f"Missing DDL table {table}")

kinds = {
    "triggers": r"CREATE TRIGGER\s+\w+",
    "procedures": r"CREATE PROCEDURE\s+\w+",
    "functions": r"CREATE FUNCTION\s+\w+",
    "views": r"CREATE OR REPLACE VIEW\s+\w+",
    "cursor": r"DECLARE\s+\w+\s+CURSOR FOR",
}
expected = {"triggers":4, "procedures":4, "functions":2, "views":4, "cursor":1}
for kind, pattern in kinds.items():
    n = len(re.findall(pattern, routines, flags=re.IGNORECASE))
    if n != expected[kind]:
        errors.append(f"Expected {expected[kind]} {kind}; found {n}")

required = [".env.example", "README.md", "requirements.txt", "frontend/app.py",
            "backend/monitor/migrations/0001_initial.py", "backend/monitor/processor.py",
            "scripts/load_test.py", "docs/HANDOVER.md"]
for name in required:
    if not (ROOT / name).is_file():
        errors.append(f"Missing required file {name}")

if errors:
    print("STATIC PREFLIGHT FAILED")
    print("\n".join(errors))
    sys.exit(1)
print(f"STATIC PREFLIGHT PASSED: {len(files)} Python files, {len(expected_tables)} SQL tables, "
      f"{expected['triggers']} triggers, {expected['procedures']} procedures, "
      f"{expected['functions']} functions, {expected['views']} views, {expected['cursor']} cursor.")
print("NOTICE: Django imports, migrations, MySQL SQL execution, Streamlit and load targets are NOT tested here.")
