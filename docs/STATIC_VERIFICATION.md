# V2 source-verification report

## Checks performed in packaging environment

- `python -m compileall -q backend frontend scripts`: **PASS**.
- `python scripts/static_check.py`: **PASS**. It validates six table declarations, four triggers, four procedures, two functions, four views and one cursor declaration.
- Additional isolated pure-Python validation harness (with API-compatible stubs, NOT actual Django/DRF integration): **10,000 synthetic records normalized**, invalid decimal precision, excessive whole digits, non-finite values and bool rejected.
- V2 source and schema are separate from V1; no database migrations added.

## Important limitations

This workspace has no Django, DRF, Streamlit or running MySQL server. Therefore it **cannot** verify the new native MySQL upsert, actual API throughput, Windows Waitress deployment, browser flows or SQLite/Django test suite. User should run `python manage.py test monitor.tests -v 2` and local MySQL tests in the instructions before claiming any V2 runtime feature passes.

V1 real-world verification is recorded separately in `docs/V1_MEASURED_BASELINE.json`. No V2 live results have been produced here.
