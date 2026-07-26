# Add the NASA Dataset Here

Place **one** supported input inside this `ai/dataset` folder:

## Option A — Recommended
Copy the downloaded cleaned NASA battery dataset ZIP directly here. Do not rename its internal files. The archive must contain a `metadata.csv` file and a `data/` directory (possibly inside a `cleaned_dataset/` folder).

## Option B — Extracted folder
Extract the archive and copy the complete `cleaned_dataset` folder here so the path is:

```
ai/dataset/cleaned_dataset/metadata.csv
ai/dataset/cleaned_dataset/data/00001.csv
...
```

## Option C — Prepared cycle-level CSV
Copy a file called `nasa_cycle_level.csv` here. It must contain:

- `battery_id`
- `cycle_index`
- `rul_cycles`
- all feature columns listed in `ai/config.py`

Then run `CHECK_DATASET.bat`, followed by `TRAIN_AI_MODEL.bat`.
