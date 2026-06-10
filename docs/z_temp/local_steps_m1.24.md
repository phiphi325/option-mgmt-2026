# Local Steps — M1.24 golden `expected.json` generation

Branch: `feat/m1.24-master-decision-goldens` (PR #3)

---

## 1. Create the branch from main

The remote branch `feat/m1.24-master-decision-goldens` no longer exists.
Create it fresh from `main`:

```bash
git fetch origin
git checkout main && git pull
git checkout -b feat/m1.24-master-decision-goldens
```

---

## 2. Install `uv` (once, if not present)

```bash
sudo snap install astral-uv --classic
hash -r   # refresh shell path
```

## 3. Verify prerequisites

```bash
cd packages/engine
uv run python -c "import engine; print(engine.__version__)"
# must print: 1.7.0
```

---

## 3. Sync deps + regenerate all 12 fixtures

```bash
uv sync --dev
uv run python scripts/regenerate_decision_goldens.py --all
```

Expect 12 `ok:` lines in the output. Any `SKIP` line means an `inputs.json` needs fixing — see the troubleshooting section in `test_06092026.md`.

---

## 4. Spot-check each `expected.json`

Open each `tests/fixtures/master_decisions/<slug>/expected.json` and confirm:

- `recommendation.matched_rule.id` and emit action match the table in `test_06092026.md`
- `engine_version == "1.7.0"`, `weights_version == "v2.0"`
- `ticker == "MSFT"`, `inputs_hash` starts with `sha256:`

---

## 5. Idempotency check

```bash
uv run pytest tests/test_regenerate_decision_goldens_idempotent.py -q
```

All tests must pass (byte-identical output on a second regen).

---

## 6. Full suite + lint

```bash
uv run pytest -q
uv run ruff check .
uv run mypy --strict engine
```

---

## 7. Commit and push

```bash
git add tests/fixtures/master_decisions/*/expected.json
git commit -m "feat(M1.24): regenerate expected.json for all 12 fixtures"
git push
```

---

## 8. Finish the PR

- Confirm CI is **5/5 green** on the pushed commit.
- Flip PR #3 from **draft → ready-for-review**.
- Squash-merge.

---

_Summary of `test_06092026.md`. See that file for troubleshooting details._
