-- Optional: tables for build_outputs.py --supabase (run once in your own Supabase SQL editor).
-- gads_daily and gads_audit_findings reference gads_accounts, so the script writes accounts first.
create table if not exists gads_accounts (
  customer_id text primary key,
  descriptive_name text,
  currency_code text,
  time_zone text,
  is_manager boolean default false,
  client_name_hint text,
  active boolean default true,
  last_seen timestamptz default now()
);

create table if not exists gads_daily (
  customer_id text references gads_accounts(customer_id),
  campaign_id text,
  campaign_name text,
  campaign_status text,
  date date,
  impressions bigint,
  clicks bigint,
  cost_micros bigint,
  conversions numeric,
  conversions_value numeric,
  avg_cpc_micros bigint,
  search_impression_share numeric,   -- raw 0-1 fraction as Google returns it
  search_lost_is_rank numeric,
  search_lost_is_budget numeric,
  currency_code text,
  unique (customer_id, campaign_id, date)
);

create table if not exists gads_audit_findings (
  run_id text,
  customer_id text references gads_accounts(customer_id),
  severity text check (severity in ('critical','warning','info')),
  code text,
  title text,
  detail text,
  metric_value numeric,
  recommended_action text,
  status text default 'open' check (status in ('open','actioned','dismissed')),
  created_at timestamptz default now(),
  unique (run_id, customer_id, code)
);
