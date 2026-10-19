# V1 release verification

## Checked during package generation

- Python AST/syntax check of all 28 Python source files: **PASS**.
- Schema completeness check: **PASS** for all six application tables.
- SQL object declaration check: **PASS** for 4 triggers, 4 procedures, 2 functions, 4 views, 1 cursor.
- Django model-to-initial-migration field-name alignment: **PASS** for six model classes.
- README, environment example, frontend source, worker, API tests, static preflight, handover: present.

Re-run syntax + declaration checks from the project root:

```powershell
python scripts/static_check.py
python -m compileall -q backend frontend scripts
```

## Not verified yet (must test on Windows + MySQL)

- Installing Django/DRF/Streamlit dependencies and starting their processes.
- Django's `manage.py check`, migration check and test suite.
- Executing MySQL DDL, triggers, stored procedures, cursor routine and views.
- Real network requests and Streamlit user interactions.
- MySQL 10k-ingest burst and worker-drain times.

The generation environment cannot install Python packages over the network and has no MySQL server. These are deployment-gate checks, not assumed successes. Next step is `python manage.py migrate`, followed by the MySQL routine import and `python manage.py test`, as described in `README.md`.
