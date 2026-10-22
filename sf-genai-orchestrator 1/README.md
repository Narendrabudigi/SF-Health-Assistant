# SF Gen AI Orchestrator

Turns the ML notebooks' insight JSON into a report for every metric of every module (RCM, ONB2, OFB2, EC, ECP): a **diagnosis and
action plan** (BRD sections) for a breached metric, a **summary** for a healthy one, and a **set-up plan** for a metric that could not be
calculated because mandatory fields are missing. One generic pipeline serves all of them: it is keyed on `(module, metric_name)` and has
no per-metric or per-module code. LLM reliability (quota and token exhaustion, rate limits, outages, bad keys) is handled by **LiteLLM**.

```
sf-pipeline
  1 run the ML notebooks (notebooks/, then notebooks_custom/)  ->  Supabase table ML_Notebook_Insights
  2 only if every notebook succeeded: the LLM step (sf-orchestrate)
        load the run's insights, validate, skip what is cached
        system prompt + insight  ->  LiteLLM:  gemini/A -> gemini/B -> groq/A -> groq/B
        check the answer in code (re-ask the model if it fails), add roles, hours and totals in code
        save the report  ->  Supabase table LLM_Reports  ->  website / BRD download
  3 every step is recorded in three dashboard tables (see "Dashboard")
```

## Run

```bash
python -m venv .venv && .venv\Scripts\activate         # Windows; on macOS/Linux: source .venv/bin/activate
pip install -e ".[notebooks,dev]"                      # once; "notebooks" = the libraries the ML notebooks import
cp .env.example .env                                   # fill in; never commit .env

sf-pipeline --dry-run                                  # list the notebooks that would run
sf-pipeline                                            # notebooks, then the LLM step (industry, then custom standards if any)
sf-pipeline --only rcm_time_to_hire --skip-llm         # one notebook, no LLM step (to try a new notebook)
sf-orchestrate --dry-run                               # the LLM step on its own: prints the prompts; no LLM calls, no LLM keys needed
sf-orchestrate                                         # today's insights, all modules
sf-orchestrate --module ONB2 --metric OnboardingCompletionDays --run-date 2026-09-29 --force
pytest
```

Exit codes: `0` ok, `1` some notebooks or reports failed or no insights were found, `2` configuration error.
On SAP BTP / Cloud Foundry set the variables on the app instead of shipping a `.env` (real environment variables win over `.env`).

## The notebooks

A notebook is a `.py` file in `notebooks/` that runs on its own (`python notebook.py`) and writes its insights to the table
`INSIGHTS_TABLE`. `sf-pipeline` starts each one as a separate process, keeps everything it prints in
`logs/<run-date>/<notebook>.log`, and judges it by its exit code. If any notebook fails, the LLM step is not run. Adding a notebook means
putting its file in the folder; nothing in the code changes.

## Custom standards

A client can upload its own benchmarks (`SF Health Monitoring Custom Standards.xlsx`, columns `Module`, `Metric Name`, `Industry Benchmark`,
`Unit`) to the bucket `SF_Health_Raw_Data`. They have their own notebooks (`notebooks_custom/`), their own insights table
(`CUSTOM_INSIGHTS_TABLE`, written by those notebooks) and their own reports table (`CUSTOM_REPORTS_TABLE`, `sql/llm_reports_custom.sql`).
The JSON is the same; the report calls the benchmark "your custom standard" instead of "industry standard" (the prompts are the same files,
the wording is changed by code, so there is only one set to maintain).

```bash
sf-pipeline                          # industry standards, then the custom standards if the file has values
sf-pipeline --standards industry     # industry only
sf-pipeline --standards custom       # custom only (notebooks_custom, then the LLM step for the custom tables)
sf-orchestrate --standards custom    # the LLM step only, for the custom tables
```

What runs is decided by the file, read from the bucket at the start of the custom part:

- no file, or no benchmark value at all: no custom notebook and no custom LLM step; the exit code stays 0
- a module with no value: its notebooks are skipped (a notebook belongs to the module its file name starts with: `EC Notebook1.py`; a
  notebook whose name starts with no module code runs whenever anything of the custom part runs)
- a metric with no value: the custom notebook must skip that metric and write no row for it; the log lists these metrics

A failure in one part never stops the other; the exit code is the worst of the two. The notebooks see `PIPELINE_STANDARDS=industry|custom`.
A cell that Excel turned into a date (a 5 shown as 1900-01-05) is reported in the log: format such cells as numbers.
From Python (for example the FastAPI backend): `from sf_orchestrator.pipeline import run_pipeline; run_pipeline("custom")`.

## What the report contains

For a breached metric the BRD has nine sections. Only the narrative ones are written by the LLM; everything that can be lifted from the
ML insight is **not generated**, so the website renders it from the insight row directly.

| BRD section | Source |
|---|---|
| Header, 1 Metric Snapshot, 3 Trend Analysis, 4 Root Cause table | Website, from the ML JSON |
| Target outcome line, 8 Success Criteria and Monitoring | Website, from the ML JSON (value, standard, variance, health state, trend direction) |
| 2 Diagnosis | LLM: `diagnosis` |
| 5 Business and Operational Impact | LLM: `businessImpact` |
| 7 Execution Workstreams | LLM: `workstreams` (each fixes factors F1..F3, or sets up data) |
| 6 Plan of Action | LLM writes `activities`; code adds `plan`: phases, role names, hours per phase and role, `totalHours`, `durationWeeks` |
| 9 Assumptions and Risks | LLM writes the assumptions and risks it can reason about; **code adds one Risk row for every empty field and every failed data check**, in fixed wording |

`LLM_Reports.report` therefore holds: `metricName`, `healthState`, `factors` (the notebook's `rca.factors`, unchanged, with ids
`F1..` added by code so the root-cause table and the "fixes factors" column use the same ids), `diagnosis`, `businessImpact`,
`workstreams`, `plan`, `assumptionsAndRisks`.

A **healthy** metric gets a summary of one or two paragraphs (`HEALTHY_SUMMARIES=false` skips them). A metric that **could not be
calculated** because mandatory fields are missing gets a plan to set those fields up (`SETUP_REPORTS=false` skips them).

The root-cause table can be built from `rca.factors` alone: stage factors (no `segment`) show `avgFactorValue`, attribute factors show
`segment` and `segmentAvgValue`, and every row shows `impactPct`. A "vs company average" column is `segmentAvgValue - companyValue`.

Plain hyphens and spaces replace the special ones models like to emit. Code checks every answer and re-asks the model
(`LLM_REPAIR_ATTEMPTS`) when: the JSON is invalid, internal wording leaks into the text (code-style names such as
`ApplicationToInterviewDuration`, `INTERVIEW_DATE` or `TimeToHire`, "JSON", "ML insight", algorithm names), a workstream points at an
unknown factor, a factor is not fixed by any workstream, a phase is empty, or the configuration phase has no staging test / user
acceptance testing activity for the QA role. A workstream without activities is dropped by code. Role names are built from the module
(see `MODULES` in `reports.py`); the model only picks `consultant`, `processOwner` or `qaUat`.

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | The database. The service-role key is server-side only |
| `INSIGHTS_TABLE`, `REPORTS_TABLE` | The tables of the industry standards: the notebooks' insights (read) and the reports (written, `sql/llm_reports.sql`). Names are case-sensitive |
| `CUSTOM_INSIGHTS_TABLE`, `CUSTOM_REPORTS_TABLE` | The same for the custom standards; set both or neither |
| `GEMINI_API_KEY`, `GROQ_API_KEY` | One key per vendor, shared by that vendor's models |
| `LLM_CHAIN` | Ordered failover chain of LiteLLM model strings (`gemini/<id>` or `groq/<id>`) |
| `LLM_REASONING_EFFORT` (`low`) | Caps the model's hidden thinking, which is billed as output tokens: `minimal`, `low`, `medium`, `high`, `disable`, or empty for the model's own default |
| `LLM_NUM_RETRIES` (2) | Retries on the same model for 503 "high demand", 5xx and timeouts, before falling back |
| `LLM_RATE_LIMIT_RETRIES` (1) | For a 429: wait as long as the provider asks (up to 60 s), then retry the same model |
| `LLM_RETRY_WAIT_SECONDS` (10) | Minimum wait between retries of the same model (max 60) |
| `LLM_ALLOWED_FAILS` (2), `LLM_COOLDOWN_SECONDS` (120) | Failures per minute before a model is skipped, and for how long |
| `LLM_REPAIR_ATTEMPTS` (1) | Re-asks when the model's answer is rejected by the checks |
| `LLM_TEMPERATURE`, `LLM_MAX_TOKENS` (16384, includes reasoning tokens), `LLM_TIMEOUT_SECONDS`, `ORCHESTRATOR_CONCURRENCY` (1: one metric at a time), `LOG_LEVEL` | Tuning |
| `NOTEBOOKS_DIR`, `NOTEBOOK_TIMEOUT_MINUTES`, `NOTEBOOK_CONCURRENCY`, `NOTEBOOK_PYTHON`, `LOGS_DIR` | The notebooks that `sf-pipeline` runs, and where their output is kept |
| `DASHBOARD_TRACKING` (true) | Record the runs for the dashboard |

Recommended chain (checked against the vendors' model lists on 1 Oct 2026):

```
LLM_CHAIN=gemini/gemini-3.8-flash,gemini/gemini-3.7-flash,groq/openai/gpt-oss-120b,groq/openai/gpt-oss-20b
```

## Who handles what

| Situation | Handled by | Behavior |
|---|---|---|
| 503 "high demand", 5xx, timeout | LiteLLM | Wait `LLM_RETRY_WAIT_SECONDS`, retry the same model up to `LLM_NUM_RETRIES` times, then go to the next model |
| 429 rate limit, for example Groq's tokens per minute | LiteLLM | Wait as long as the provider says (up to 60 s), retry the same model `LLM_RATE_LIMIT_RETRIES` time, then the next model |
| Quota used up, bad key, bad request, anything else | LiteLLM | No retry: straight to the next model of `LLM_CHAIN` |
| A model keeps failing | LiteLLM | Cooldown: skipped for `LLM_COOLDOWN_SECONDS`, then tried again |
| Answer fails the checks (see "What the report contains") | This project | Re-ask with the reason (`LLM_REPAIR_ATTEMPTS`), then fail that metric |
| Output cut off by the token limit | This project | Fail with a clear message (raise `LLM_MAX_TOKENS`) |
| One metric fails | This project | Stored as `failed`; the run continues; never overwrites a good report |
| The reports table cannot be used | This project | Checked before the first model call; the run stops with the reason |

## What you see in the log

Every failed attempt is logged in plain words: the model, the reason, and what happens next. The last line says which model answered.

```
WARNING RCM/TimeToHire: gemini/gemini-3.8-flash failed (503: This model is currently experiencing high demand.). Retry 1 of 2 in about 10s.
WARNING RCM/TimeToHire: gemini/gemini-3.8-flash failed (503: This model is currently experiencing high demand.). Retry 2 of 2 in about 10s.
WARNING RCM/TimeToHire: gemini/gemini-3.8-flash failed (503: This model is currently experiencing high demand.). Giving up on this model.
WARNING RCM/TimeToHire: report generated by gemini/gemini-3.7-flash (after 1 fallback)
```

"Giving up on this model" means the next model of the chain is tried. When the answer is rejected by the checks you see
`the answer was rejected (<reason>). Asking again (1 of 1).` Secrets are never printed. The stored report keeps the counts in
`llm_meta` (`fallbacks`, `retries`, `repairs`, tokens, time).

## The notebook JSON

`MetricInsight` in `schemas.py` mirrors the notebook format: `generatedAt`, `module`, `metricName`, `unit`, `higherIsBetter`,
`companyValue`, `industryStandardValue`, `healthState`, `variance`, `trendAnalysis` (nested year > quarter > month), `forecast`
(`predictedValue`, bounds, `predictedHealthState`), `rca` (`applicable`, `breachValue`, `factors`), `dataQuality`, `modelAccuracy`,
`missingConfigurations`.

- The prompt gets the trend as short lists of yearly averages and of the same periods one year apart, with incomplete periods left out
  of the comparisons; `generatedAt` and `module` are not sent (the module goes in as a tag). The website keeps using the original nested JSON.
- `dataQuality` and `modelAccuracy` are passed through as they are, so new checks or models need no code change.
- A top-level field the orchestrator does not know is dropped and **logged as a warning**, never silently.
- A module in the JSON that differs from the stored row fails that metric (the staffing roles depend on the module).

## Abbreviations in field names

The notebooks send field names in code style (`appExpCtc`). The model rewrites them in business words, so the program tells it the exact
wording for the abbreviations it knows: the request carries a `<glossary>` block (`appExpCtc = applicant expected CTC`), and the prompts
say to use it exactly and never to guess an abbreviation that is not listed. To add one, edit the glossary at the top of
`src/sf_orchestrator/reports.py`: `FIELDS` for a whole field name, `TOKENS` for a part of a name with a single meaning. Reports that
mention the field are written again on the next run.

## Other behavior

- **Cache:** a report is cached by a hash of (prompt + module + insight + glossary), so reruns only generate what is missing, failed or
  changed; `--force` overrides. Editing a prompt therefore regenerates every report once.
- **Privacy:** only fields declared in `schemas.py` reach the LLM (raw records and similar are dropped; tested).
- **Secrets:** exact secret values are redacted from stored and logged error text.

## Layout

```
src/sf_orchestrator/
  config.py       settings from .env + startup validation
  store.py        Supabase: read the insights, save the reports, read the custom standards file
  schemas.py      input contract (ML JSON) and the LLM's output contract
  llm.py          LiteLLM Router from LLM_CHAIN + re-ask on rejected answers
  reports.py      the glossary, the checks and completion of the model's draft, and the run (prompt -> model -> report)
  pipeline.py     the two commands: sf-pipeline (notebooks, then the LLM step) and sf-orchestrate (the LLM step)
  dashboard.py    run recording for the dashboard, and the API behind it (sf-dashboard)
  prompts/        system.md (breach), healthy.md (summary), setup.md (set-up plan)
sql/              llm_reports.sql, llm_reports_custom.sql (reports tables), dashboard.sql (dashboard tables)
notebooks/        the ML notebooks (industry standards)      notebooks_custom/  the company's own standards
dashboard/        the React app
tests/            one file per area; tests/samples holds the sample insight JSON
```

Tests: `store` (tables, against a fake Supabase over HTTP), `config`, `schemas` (contracts), `checks` (draft checks and completion),
`reports` (a whole run with a fake model), `llm` (the real LiteLLM router with mocked providers), `pipeline` (notebooks and custom
standards), `dashboard` (recording and API), `prompts` (guards the rules written in the prompt files).

## Change points

| Change | Edit |
|---|---|
| Models, order, or fallbacks | `LLM_CHAIN` in `.env` |
| ML JSON field names | `MetricInsight` in `schemas.py` |
| What the LLM writes | `BrdDraft` in `schemas.py` and the output contract in `prompts/system.md` (a test fails if they drift) |
| Role names, phase wording | `MODULES`, `PHASES` and `PHASES_SETUP` in `reports.py` |
| An abbreviation in a field name | `FIELDS` or `TOKENS` in `reports.py` |
| Prompt behavior | `prompts/*.md` (the hash is part of the cache key, so reports regenerate) |
| New module | one line in `MODULES` (optional; unknown modules get generic role names) |

## Before go-live

1. Run once with real keys. Tests use LiteLLM's mock mode, so live Gemini and Groq calls are untested here.
2. Run the real notebook output through `sf-orchestrate --dry-run` and check the log for "fields ... are not used" warnings.
3. Keep LiteLLM pinned to a tested range (`pyproject.toml`) and upgrade deliberately; it moves fast.

## Dashboard

A web page that shows everything the orchestrator does: notebooks running, every model call (answered, failed, retried, rejected, with
its input and output tokens), every metric's outcome, warnings and errors. With no run in progress it shows the last run. Runs can also
be started and stopped from it.

How it fits together: the program records each run in three Supabase tables (`sql/dashboard.sql`). A small local API (`sf-dashboard`)
reads them and starts and stops runs. The React app in `dashboard/` talks only to that API, so no Supabase key is ever in the browser.
Prompts and answers are sent to the browser only when you expand a model call.

One-time setup:

1. Run `sql/dashboard.sql` in the Supabase SQL editor.
2. `pip install -e ".[dashboard]"`
3. `cd dashboard && npm install`

Every day:

- Terminal 1: `sf-dashboard` (serves the API on http://127.0.0.1:8765)
- Terminal 2: `cd dashboard && npm run dev`, then open http://localhost:5173
- Or build once with `npm run build` and open http://127.0.0.1:8765 (one terminal).

Notes:

- Runs started from a terminal, a scheduler or Cloud Foundry also appear: the page reads the tables, not the process.
- The API has no login and listens on 127.0.0.1 only. Do not expose it on a network as it is.
- The tables hold prompts and answers. Only the service-role key can read them (row level security is on, with no policy).
- Recording is best effort and never breaks a run. Turn it off with `DASHBOARD_TRACKING=false`.
- A run that stops reporting for 90 seconds is shown as "Stalled".
- The column `cached_tokens` shows how many input tokens the provider reported as served from its cache. It stays empty when the provider
  reports none.