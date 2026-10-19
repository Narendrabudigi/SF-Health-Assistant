# Supabase source dataset mapping

The UI gets dataset contents through the backend from the configured Supabase Storage bucket. The backend does not need code edits when uploaded dataset names or folders change.

For predictable module and metric matching, upload a JSON manifest to the dataset bucket. Start with `DATASET_MANIFEST.example.json`, replace its placeholder paths with the actual object paths, and upload it to the path configured by `SUPABASE_DATASET_MANIFEST_PATH` (default: `dataset_manifest.json`).

Each entry supports:

- `module`: module ID or display name, such as `ec`, `onb`, or `Employee Central`.
- `modules`: optional list of additional module aliases.
- `metrics`: metric names/codes that use this file. Use `metric_aliases` or `metric_codes` for the same purpose.
- `default: true`: use this file for other metrics in that module. This suits modules with one shared dataset.
- `path`: path to an `.xlsx` or `.csv` object inside the bucket.
- `sheet`: optional worksheet name for Excel files.

Use one metric entry per Employee Central source file when its metrics use different datasets. If file names already contain recognizable module/metric names, the backend can also discover them automatically when no manifest entry matches. If names are arbitrary, add or update a manifest entry; no application-code change is needed.

Only bucket and manifest location belong in `backend/.env`:

```dotenv
SUPABASE_DATASET_BUCKET_NAME=SF_Health_Raw_Data
SUPABASE_DATASET_MANIFEST_PATH=dataset_manifest.json
```

Change these only when the bucket or manifest object itself moves. Change dataset object paths in the manifest when individual files move or are renamed. Do not put the per-metric mapping JSON in environment variables; keeping it as a file in Supabase makes edits and review much easier.
