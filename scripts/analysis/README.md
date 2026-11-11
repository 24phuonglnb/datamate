# scripts/analysis

One-off analysis scripts used to study the official data. They are **not** part of
the inference pipeline and must never be imported from `src/`.

`revenue_check.py` contains a hand-written column mapping keyed on business id. That
is fine for analysis (it stands in for the output of an automatic mapping step) but
would violate the competition rules if it reached `src/`.

All scripts expect the official zips unzipped under `data/` (`data/train`,
`data/public_test`); `data/` is not committed.

| Script | What it shows |
|---|---|
| `revenue_check.py` | Monthly revenue recomputed from cleaned ledgers vs. train answers, with and without fill-down / de-duplication |
| `intent_tagger.py` | Approximate intent label per question (regex rules), counts and samples |
| `profile_raw.py` | First rows of every raw file, sheet and SQLite table |
| `load_all.py` | Result of `src.cleaning.load_business` for every shop, flags suspicious headers |
