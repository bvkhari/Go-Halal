-- Go Halal bot storage. RLS is on with no policies: only the service-role key
-- (kept in .env on the server, never in git) can read or write.

create table public.trades (
  id          bigint generated always as identity primary key,
  time        timestamptz not null default now(),
  mode        text not null check (mode in ('paper', 'live')),
  side        text not null check (side in ('BUY', 'SELL')),
  code        text not null,
  qty         numeric not null,
  limit_price numeric not null,
  reason      text,
  status      text
);

create table public.equity_snapshots (
  id     bigint generated always as identity primary key,
  time   timestamptz not null default now(),
  mode   text not null check (mode in ('paper', 'live')),
  equity numeric not null,
  cash   numeric not null
);

create table public.bot_events (
  id      bigint generated always as identity primary key,
  time    timestamptz not null default now(),
  mode    text,
  message text not null
);

create index trades_time_idx on public.trades (time desc);
create index equity_time_idx on public.equity_snapshots (time desc);
create index bot_events_time_idx on public.bot_events (time desc);

alter table public.trades enable row level security;
alter table public.equity_snapshots enable row level security;
alter table public.bot_events enable row level security;
