-- The tables behind the orchestrator dashboard. Run this once in the Supabase SQL editor.
--
-- sf_dashboard_runs       one row per run (a pipeline run, or an LLM-only run): status, arguments, totals
-- sf_dashboard_events     what happened, in order: notebooks started and finished, every metric's outcome, warnings, errors
-- sf_dashboard_llm_calls  every call to a model: which model, how it ended (success, error, rejected answer), tokens, time,
--                         and the prompt and the answer (the dashboard shows them only when you expand a call)
--
-- Only the service-role key (the orchestrator and the dashboard API) can read and write them: row level security is on and
-- there is no policy, so the website's public key cannot see prompts or answers.

create table if not exists public.sf_dashboard_runs (
  id            uuid primary key default gen_random_uuid(),
  started_at    timestamptz not null default now(),
  finished_at   timestamptz,
  heartbeat_at  timestamptz,
  status        text not null default 'queued'
                check (status in ('queued', 'running', 'succeeded', 'failed', 'stopped')),
  kind          text not null default 'pipeline' check (kind in ('pipeline', 'llm')),
  standards     text,
  run_date      date,
  trigger       text not null default 'cli',          -- cli | dashboard
  args          jsonb not null default '{}'::jsonb,
  pid           integer,
  exit_code     integer,
  summary       jsonb not null default '{}'::jsonb
);
create index if not exists sf_dashboard_runs_started_idx on public.sf_dashboard_runs (started_at desc);

create table if not exists public.sf_dashboard_events (
  id        bigint generated always as identity primary key,
  run_id    uuid not null references public.sf_dashboard_runs (id) on delete cascade,
  ts        timestamptz not null default now(),
  level     text not null default 'info' check (level in ('debug', 'info', 'warning', 'error')),
  kind      text not null,                            -- for example notebook_finished, metric_generated, log
  stage     text,                                     -- industry | custom
  module    text,
  metric    text,
  message   text not null,
  data      jsonb not null default '{}'::jsonb
);
create index if not exists sf_dashboard_events_run_idx on public.sf_dashboard_events (run_id, id);

create table if not exists public.sf_dashboard_llm_calls (
  id             uuid primary key default gen_random_uuid(),
  run_id         uuid not null references public.sf_dashboard_runs (id) on delete cascade,
  ts             timestamptz not null default now(),
  module         text,
  metric         text,
  round          integer not null default 0,          -- 0 = first ask, 1 = asked again after a rejected answer, ...
  provider       text,
  model          text,
  outcome        text not null check (outcome in ('success', 'error', 'rejected')),
  status_code    integer,
  error_class    text,
  error_message  text,
  retry_info     text,                                -- for example "Retry 1 of 2 in about 10s." or "Giving up on this model."
  input_tokens   integer,
  output_tokens  integer,
  cached_tokens  integer,                             -- of the input tokens, how many the provider served from its prompt cache
  latency_ms     integer,
  messages       jsonb,                               -- what was sent
  response       text                                 -- what came back (empty for an error)
);
alter table public.sf_dashboard_llm_calls add column if not exists cached_tokens integer;  -- for tables created before this column existed
create index if not exists sf_dashboard_llm_calls_run_idx on public.sf_dashboard_llm_calls (run_id, ts);

alter table public.sf_dashboard_runs      enable row level security;
alter table public.sf_dashboard_events    enable row level security;
alter table public.sf_dashboard_llm_calls enable row level security;

notify pgrst, 'reload schema';