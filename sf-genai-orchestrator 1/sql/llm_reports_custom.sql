-- LLM_Reports_Custom: ONE row per metric (the newest), written by the Gen AI orchestrator for the company's own (custom) standards.
--
-- HOW TO RUN: Supabase > SQL Editor > New query > paste this whole file > Run.
-- It works on a database without the table AND on a table you already have (also one that still keeps a row for every day),
-- and it is safe to run again.
--
-- What it does to a table that already exists:
--   1. Keeps only ONE row for each module + metric_name: the newest succeeded report (or, if there is none, the newest row).
--      All the older rows are DELETED. This is what you asked for: no reports of earlier days.
--   2. Replaces the old rule 'one row per run_date + module + metric_name' by 'one row per module + metric_name'.
--   From then on the orchestrator's save REPLACES the row of the metric. run_date says which day's insight the report is made from.
--
-- The name keeps its capital letters because it is written in double quotes. In your own SQL you must always write
-- "LLM_Reports_Custom" with the quotes. The orchestrator reads the name from CUSTOM_REPORTS_TABLE in .env, so it must match exactly.

-- 1. The table (created only if it does not exist yet)
create table if not exists public."LLM_Reports_Custom" (
  id           uuid        primary key default gen_random_uuid(),
  run_date     date        not null,
  module       text        not null,
  metric_name  text        not null,
  status       text        not null,
  provider     text,
  model        text,
  report       jsonb,
  error        text,
  llm_meta     jsonb       not null default '{}'::jsonb,
  prompt_sha   text        not null,
  generated_at timestamptz not null,

  constraint llm_reports_custom_one_row_per_metric unique (module, metric_name),
  constraint llm_reports_custom_status_is_known check (status in ('succeeded', 'failed')),
  constraint llm_reports_custom_report_matches_status check (
    (status = 'succeeded' and report is not null and error is null)
    or (status = 'failed' and report is null and error is not null)
  )
);

-- 2. The same rules for a table that already existed without them (each statement can be run again)
alter table public."LLM_Reports_Custom"
  alter column id           set default gen_random_uuid(),
  alter column run_date     set not null,
  alter column module       set not null,
  alter column metric_name  set not null,
  alter column status       set not null,
  alter column llm_meta     set default '{}'::jsonb,
  alter column llm_meta     set not null,
  alter column prompt_sha   set not null,
  alter column generated_at set not null;

-- 3. Keep one row per metric: the newest succeeded report (a failed row only if the metric has no succeeded one)
delete from public."LLM_Reports_Custom" t
using (
  select id,
         row_number() over (
           partition by module, metric_name
           order by (status = 'succeeded') desc, run_date desc, generated_at desc
         ) as rn
  from public."LLM_Reports_Custom"
) ranked
where t.id = ranked.id and ranked.rn > 1;

-- 4. The rules
do $$
declare
  t constant regclass := 'public."LLM_Reports_Custom"'::regclass;
  old record;
begin
  if not exists (select 1 from pg_constraint where conrelid = t and contype = 'p') then
    alter table public."LLM_Reports_Custom" add primary key (id);
  end if;
  -- the old rule: any unique rule that includes run_date (one row per day) is removed
  for old in
    select c.conname
    from pg_constraint c
    join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any (c.conkey)
    where c.conrelid = t and c.contype = 'u' and a.attname = 'run_date'
  loop
    execute format('alter table public."LLM_Reports_Custom" drop constraint %I', old.conname);
  end loop;
  -- the new rule: one row per module + metric_name. This is what makes the orchestrator's save REPLACE the row.
  if not exists (select 1 from pg_constraint where conrelid = t and conname = 'llm_reports_custom_one_row_per_metric') then
    alter table public."LLM_Reports_Custom" add constraint llm_reports_custom_one_row_per_metric unique (module, metric_name);
  end if;
  if not exists (select 1 from pg_constraint where conrelid = t and conname = 'llm_reports_custom_status_is_known') then
    alter table public."LLM_Reports_Custom" add constraint llm_reports_custom_status_is_known check (status in ('succeeded', 'failed'));
  end if;
  if not exists (select 1 from pg_constraint where conrelid = t and conname = 'llm_reports_custom_report_matches_status') then
    alter table public."LLM_Reports_Custom" add constraint llm_reports_custom_report_matches_status check (
      (status = 'succeeded' and report is not null and error is null)
      or (status = 'failed' and report is null and error is not null)
    );
  end if;
end $$;

-- 5. Descriptions (they show up in the Supabase table editor)
comment on table public."LLM_Reports_Custom" is 'Reports written by the Gen AI orchestrator for the company''s own (custom) standards: one row per metric, the newest.';
comment on column public."LLM_Reports_Custom".id           is 'Row id, generated by the database.';
comment on column public."LLM_Reports_Custom".run_date     is 'The day of the insight the report was made from (the newest run that produced a new report).';
comment on column public."LLM_Reports_Custom".module       is 'Module code: RCM, ONB2, OFB2, EC or ECP.';
comment on column public."LLM_Reports_Custom".metric_name  is 'File-safe key of the metric, for example FullAndFinalSettlementTimeliness. The readable name is report->>metricName.';
comment on column public."LLM_Reports_Custom".status       is 'succeeded or failed.';
comment on column public."LLM_Reports_Custom".provider     is 'Which vendor answered: gemini or groq.';
comment on column public."LLM_Reports_Custom".model        is 'Which model answered.';
comment on column public."LLM_Reports_Custom".report       is 'The complete JSON the report consists of, exactly as produced. Nothing is split out of it, so new fields never need a new column.';
comment on column public."LLM_Reports_Custom".error        is 'Why the report could not be made. Empty for succeeded rows.';
comment on column public."LLM_Reports_Custom".llm_meta     is 'fallbacks, retries, repairs, inputTokens, outputTokens, latencyMs, inputHash (fingerprint of insight + prompt: an unchanged insight is not sent to a model again) and insightId (path of the insight file).';
comment on column public."LLM_Reports_Custom".prompt_sha   is 'Version of the prompt that wrote the report.';
comment on column public."LLM_Reports_Custom".generated_at is 'When the report was generated (UTC).';

-- 6. The website reads the succeeded reports.
drop index if exists public.llm_reports_custom_latest_idx;
drop view if exists public."LLM_Reports_Custom_Latest";
create view public."LLM_Reports_Custom_Latest" with (security_invoker = true) as
select * from public."LLM_Reports_Custom" where status = 'succeeded';

comment on view public."LLM_Reports_Custom_Latest" is 'The succeeded reports, one per metric: what the website reads.';

-- 7. Security: with row level security on and no policy, only the server key (secret / service_role) can read or write.
alter table public."LLM_Reports_Custom" enable row level security;

-- Only if the website reads the table directly with the PUBLIC key (publishable / anon), remove the two dashes below.
-- create policy "website can read succeeded custom reports" on public."LLM_Reports_Custom"
--   for select to anon, authenticated using (status = 'succeeded');