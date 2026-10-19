# Load test report — measurement template, not a fabricated result

**Target stated by the challenge:** system designed for a burst of 10,000 readings arriving in one second.

## Status on generation

**Not yet benchmarked against live MySQL/Django/Streamlit.** The authoring environment does not have a running MySQL server and cannot install Django packages over the network. No live throughput or 1-second pass claim is made.

## Reproducible test

1. Configure MySQL 8.x and Django, create/activate `library-floor-2`, and start `python manage.py runserver`.
2. Start `python manage.py run_alert_worker` in a separate terminal if you also want to measure background queue drain.
3. Run `python scripts/load_test.py --count 10000 --repeat 3` from repo root.
4. Save resulting `results/load_test.json` and database query counts, as well as local host hardware, MySQL version/configuration and network type.
5. Separately measure time from reading persisted until worker processing completes; compare pending queue lengths before/after.

## Report table (populate with real results)

| Test | Target | Measured | Pass/Fail |
|---|---|---|---|
| Batch ingestion HTTP payload | 10,000 readings | Pending test | Pending |
| Client elapsed for one batch | ≤ 1.000 s | Pending test | Pending |
| DB durability | 10,000 unique IDs persisted | Pending test | Pending |
| Ingest retry | No duplicate readings | Pending test | Pending |
| Worker processing | Pending queue eventually drains | Pending test | Pending |
| MySQL audit | Trigger rows on insert/transition | Pending test | Pending |
| Repeated burst stability | No 500s, stable timings | Pending test | Pending |

## Interpretation

One 10,000-item HTTP request is **not** proof of 10,000 readings per second sustained. The measured wall duration includes Python payload serialization, HTTP transfer, validation and DB write; actual API service capacity requires additional tests with concurrency, multiple sensors, and realistic hardware. Do not confuse worker throughput and ingest throughput. If the 1-second burst fails, optimize instrumented bottlenecks before reporting success (e.g. database roundtrips, batch size, MySQL tuning, and serializer overhead).
