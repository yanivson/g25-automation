# G25 Automation

A fully deterministic pipeline for running genetic-distance (G25) optimization
against a local clone of the [Vahaduo](https://github.com/vahaduo/vahaduo)
browser engine.

No external API calls. No randomness. Every run from the same inputs produces
identical output.

---

## Contents

- [How it works](#how-it-works)
- [Installation](#installation)
- [Bootstrap](#bootstrap)
- [Input formats](#input-formats)
- [Quick start](#quick-start)
- [Step-by-step workflow](#step-by-step-workflow)
- [Interpretation profiles](#interpretation-profiles)
- [Artifacts written](#artifacts-written)
- [Configuration reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)

---

## How it works

```
Raw source file
      |
  g25-preprocess         filter by region, split into period buckets
      |
  g25-build-pool         reduce a period bucket to a candidate pool
      |                  (optional: deduplicate near-identical samples)
  g25-run                iterative optimization via local Vahaduo engine
      |
  results/runs/<id>/     artifact bundle
```

Or use the one-shot wrapper:

```
g25-full-run <target.csv> <source_raw.csv>
```

The optimizer is a rule-based loop: seed a panel, run the engine, classify
populations by percentage threshold, drop weak ones, add new candidates,
repeat until a stop condition is met. All decisions are deterministic.

---

## Installation

**Requirements:** Python 3.11+, git

```bash
git clone <this-repo>
cd g25_automation

pip install -e ".[dev]"
pip install scipy
python -m playwright install chromium
```

---

## Bootstrap

The Vahaduo engine must be cloned once before running:

```bash
python setup.py
```

This clones `https://github.com/vahaduo/vahaduo` into `data/vahaduo_engine/`
and verifies the Playwright browser is available.

To update the engine later:

```bash
python -c "from engine.setup import clone_or_update_vahaduo; from pathlib import Path; clone_or_update_vahaduo(Path('data/vahaduo_engine'))"
```

---

## Input formats

### Target file

A single-row G25 CSV with a header:

```
name,dim_1,dim_2,...,dim_25
MyTarget,0.1234,0.5678,...
```

- Exactly one data row.
- Comma or tab delimited (auto-detected).
- The `name` column may contain spaces.

### Source / raw file

A multi-row G25 CSV or TSV, one population per row:

```
Israel_MLBA_o,0.1234,0.5678,...
Italy_Imperial_o1.SG,0.2345,0.6789,...
```

- May or may not have a header row (auto-detected by column count).
- Comma or tab delimited (auto-detected).
- Population names use underscore notation: `Country_Period_variant`.

---

## Quick start

### One-shot run (recommended for new users)

```bash
g25-full-run data/targets/my_target.csv data/sources_raw/my_source.csv
```

With a named interpretation profile:

```bash
g25-full-run data/targets/my_target.csv data/sources_raw/my_source.csv \
    --profile eastmed_europe
```

Skip deduplication:

```bash
g25-full-run data/targets/my_target.csv data/sources_raw/my_source.csv \
    --no-dedup
```

Choose which population set to use as the candidate pool:

```bash
# Only populations matching the region filter (default)
g25-full-run data/targets/my_target.csv data/sources_raw/my_source.csv \
    --pool-source filtered

# All populations, ignoring region filter
g25-full-run data/targets/my_target.csv data/sources_raw/my_source.csv \
    --pool-source full
```

---

## Step-by-step workflow

### 1. Preprocess the source file

```bash
g25-preprocess data/sources_raw/my_source.csv
```

Outputs per-period CSVs to `data/sources_periods/`:
- `classical.csv`, `late_antiquity.csv`, `medieval.csv`, `undated.csv`, `out_of_range.csv`

Region filter and period ranges are configured in `config.yaml`.

### 2. Build a candidate pool

```bash
g25-build-pool data/sources_periods/classical.csv
```

Outputs `data/candidate_pools/classical_pool.csv`.

With deduplication disabled:

```bash
g25-build-pool data/sources_periods/classical.csv --no-dedup
```

The deduplication threshold is set in `config.yaml` under
`preprocessing.deduplication.distance_threshold`. The default (0.010)
clusters populations whose G25 Euclidean distance is below that value.

### 3. Run optimization

```bash
g25-run data/targets/my_target.csv data/candidate_pools/classical_pool.csv
```

With a named interpretation profile:

```bash
g25-run data/targets/my_target.csv data/candidate_pools/classical_pool.csv \
    --profile eastmed_europe
```

---

## Interpretation profiles

By default, the tool outputs sample-level percentages and country-level
(prefix) aggregation only. No ancestry assumptions are made.

An optional `--profile` flag enables a third layer: macro-region rollup with
human-readable labels. Profiles are YAML files in `interpretation_profiles/`.

**Available profiles:**

| Name | Covers |
|---|---|
| `eastmed_europe` | Levant, Anatolia, SE Europe, North Africa, Middle East, Southern/NW Europe |
| `northwest_europe` | British Isles, Scandinavia, Germanic, Central/Southern Europe |
| `minimal` | No mappings — every prefix is its own macro-region (safe fallback) |

**Run without profile (default):**

```
Top populations:
   28.60%  Israel_MLBA_o
   26.60%  Italy_Imperial_o1.SG
   ...

By region (prefix aggregation):
   41.80%  Italy
   28.60%  Israel
   ...
```

**Run with `--profile eastmed_europe`:**

```
Top populations:
   28.60%  Israel_MLBA_o
   ...

By region (prefix aggregation):
   41.80%  Italy
   28.60%  Israel
   ...

By macro-region:
   85.00%  Eastern Mediterranean  [East Mediterranean ancestry]
   15.00%  Southern Europe        [Southern European ancestry]

Summary:
  Best fit is driven mainly by Eastern Mediterranean proxies (85.0% combined).
  Country-level aggregation shows strongest affinity to Italy, Israel, Croatia, and Turkey.
  Best fit distance is 0.024338 (close fit).
  These are proxy populations and should not be read as literal recent ethnic percentages.
```

**Creating a custom profile:**

Copy `interpretation_profiles/minimal.yaml` and add your own mappings:

```yaml
prefix_to_region:
  MyCountry: MyRegion

region_to_macro:
  MyRegion: MyMacro

macro_to_label:
  MyMacro: My ancestry label
```

Unlisted entries pass through unchanged at each level — any profile works for
any target, even with partial coverage.

---

## Artifacts written

Every `g25-run` (and `g25-full-run`) writes a bundle to `results/runs/<run_id>/`:

| File | Always written | Description |
|---|---|---|
| `meta.json` | Yes | Run metadata: timestamp, config hash, stop reason, best distance, profile name |
| `target_used.csv` | Yes | Exact copy of the target file used |
| `preselection.csv` | When nearest-by-distance seeding | All candidates ranked by Euclidean distance to target |
| `iteration_NN_panel.txt` | Yes | Panel string sent to engine at iteration N |
| `iteration_NN_raw_output.txt` | Yes | Raw HTML returned by engine at iteration N |
| `iteration_NN_result.json` | Yes | Parsed result + diagnostics for iteration N |
| `run_summary.json` | Yes | Distance trajectory, all removed/added populations, per-iteration diagnostics |
| `best_result.json` | Yes | Sample-level populations at best iteration |
| `aggregated_result.json` | Yes | Country-level (prefix) aggregation at best iteration |
| `generic_summary.json` | Only with `--profile` | Macro-region rollup, summary sentences, profile name |

`g25-build-pool` with deduplication enabled also writes to
`data/candidate_clusters/`:

| File | Description |
|---|---|
| `<pool_name>_clusters.csv` | Every population mapped to its cluster ID and representative |
| `<pool_name>_representatives.csv` | Representative rows only (full G25 data) |

---

## Configuration reference

`config.yaml` controls all pipeline behaviour. Key sections:

```yaml
optimization:
  max_iterations: 20          # hard stop
  stop_distance: 0.02         # early stop if distance reaches this
  remove_percent_below: 5.0   # drop populations scoring below this %
  strong_percent_at_or_above: 10.0  # always keep populations at or above this %
  max_sources_per_panel: 20   # panel size cap
  max_initial_panel_size: 40  # seed cap for first iteration

  # Streak-based early stopping (0 = disabled)
  stop_if_no_improvement_iterations: 3
  stop_if_panel_repeats: 2
  stop_if_all_new_candidates_zero: 2

  # Seeding strategy
  initial_panel_strategy: nearest_by_distance   # or: alphabetical
  nearest_seed_count: 40

preprocessing:
  region_filter:
    allowed_keywords: [Anatolia, Turkey, Europe, Levant, ...]
    exclusion_keywords: []

  deduplication:
    enabled: true
    distance_threshold: 0.010   # Euclidean distance over 25 dims
                                # 0.010 = calibrated baseline for ancient DNA panels
                                # 0.0015 is too conservative (produces 0 merges)

  periods:
    classical:      [-500, 200]
    late_antiquity: [200,  800]
    medieval:       [800,  1500]
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'scipy'`**

```bash
pip install scipy
```

**`ModuleNotFoundError: No module named 'playwright'`**

```bash
pip install playwright
python -m playwright install chromium
```

**`[ERROR] Config file not found: config.yaml`**

Run commands from the project root directory (where `config.yaml` lives), or
pass `--config /path/to/config.yaml` explicitly.

**`[ERROR] Interpretation profile 'xyz' not found`**

Profile files live in `interpretation_profiles/`. The error message lists
available profile names. Check spelling or create a new profile YAML.

**`deduplication: 1916 candidates -> 1916 representatives (1916 clusters)`**

Your `distance_threshold` is below the minimum nearest-neighbor distance in
your dataset. Run the calibration snippet below to find an appropriate value:

```python
import numpy as np
from scipy.spatial.distance import cdist
from preprocessing.loader import load_g25_file

pool = load_g25_file("data/candidate_pools/your_pool.csv")
dims = [f"dim_{i}" for i in range(1, 26)]
D = cdist(pool[dims].to_numpy(), pool[dims].to_numpy())
np.fill_diagonal(D, np.inf)
nn = D.min(axis=1)
print(f"Min NN distance: {nn.min():.6f}")
print(f"p5 NN distance:  {np.percentile(nn, 5):.6f}")
```

Set `distance_threshold` to a value slightly above the `Min NN distance`.

**Engine not found / clone fails**

Check your internet connection and that `git` is on your PATH. Then:

```bash
python setup.py
```

**Run produces very poor distance (> 0.10)**

- The region filter may be too broad or narrow for this target.
  Adjust `allowed_keywords` in `config.yaml`.
- Try `--pool-source full` in `g25-full-run` to use all populations.
- Increase `max_initial_panel_size` or `nearest_seed_count` in `config.yaml`.

**Run stops after 1 iteration with `panel_repeat_streak`**

This is expected when the optimizer converges immediately — the first panel
already contains the best possible candidates. The distance reported is
correct. If you want more exploration, temporarily increase
`stop_if_panel_repeats` or set it to `0` in `config.yaml`.
