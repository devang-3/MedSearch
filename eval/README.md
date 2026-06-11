# Automated bandit training loop

Fully scripted feedback loop — **no UI clicks required**. Oracle labels come from auto-generated typo benchmarks.

## One-command flow (dev subset)

From the `MedSearch/` folder:

```bash
pip install -r requirements-search.txt

# Step 1 — generate typo benchmark from CSV
python eval/build_typo_benchmark.py --limit 5000

# Step 2 — baseline metrics (fixed merge = X%)
python eval/run_baseline.py --limit 5000 --policy fixed

# Step 3 — train LinUCB + before/after report
python eval/train_bandit_loop.py --limit 5000 --episodes 1500

# Step 4 — eval trained policy alone
python eval/run_baseline.py --limit 5000 --policy linucb
```

Results land in `eval/results.json`. Trained policy in `policy/state.json`.

## What each step does

| Step | Script | Output |
|------|--------|--------|
| 1 | `build_typo_benchmark.py` | `eval/typo_benchmark.jsonl` — `(query, target)` pairs |
| 2 | `run_baseline.py --policy fixed` | Top-1 / top-3 / MRR for legacy merge |
| 3 | `train_bandit_loop.py` | Trains LinUCB with oracle reward, saves policy |
| 4 | `run_baseline.py --policy linucb` | Metrics for learned merge |

## Oracle reward

| Target rank | Reward (`graded` mode) |
|-------------|------------------------|
| 1 | 1.0 |
| 2–3 | 0.5 |
| else | 0.0 |

Training loop per episode:

```
query → 5 matchers → features → LinUCB picks arm → weighted merge
     → oracle_reward(rank, target) → update LinUCB
```

## Full dataset (overnight)

```bash
python eval/build_typo_benchmark.py
python eval/train_bandit_loop.py --episodes 5000
```

Omit `--limit` to index all ~254k medicines (slow first build).

## Key files

```
policy/features.py      # context vector
policy/rank.py          # merge arms + prefix safety pin
policy/bandit.py        # LinUCB save/load
eval/oracle.py          # reward + metrics
eval/runner.py          # search + rank helpers
eval/build_typo_benchmark.py
eval/run_baseline.py
eval/train_bandit_loop.py
```

See `CONTEXTUAL_BANDIT_PLAN.md` for full architecture and resume guidance.
