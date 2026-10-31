-- AI Papers Daily: Supabase schema (Phase 2)
-- Paste this whole file into Supabase > SQL Editor > New query, then press Run.
-- It is safe to run again: every statement checks before it creates.

create extension if not exists vector with schema extensions;

-- One row per paper. The pipeline writes rows; the public can only read them.
create table if not exists public.papers (
  id          text primary key,              -- arXiv ID without version, e.g. 2610.41200
  title       text not null,
  abstract    text not null default '',
  authors     text[] not null default '{}',
  categories  text[] not null default '{}',  -- our topic slugs, e.g. {llms,efficient-ai}
  submitted   date,
  first_seen  date,                          -- the day our pipeline first saw it
  featured    boolean not null default false,
  hf_upvotes  integer not null default 0,
  code_url    text,
  source      text,
  embedding   extensions.vector(384),        -- gte-small, filled by the embed function
  updated_at  timestamptz not null default now()
);

create index if not exists papers_first_seen_idx on public.papers (first_seen desc);
create index if not exists papers_embedding_idx on public.papers
  using hnsw (embedding extensions.vector_cosine_ops);
-- Lets the embed function find rows that still need a vector, fast
create index if not exists papers_missing_embedding_idx on public.papers (id) where embedding is null;

alter table public.papers enable row level security;
drop policy if exists "Anyone can read papers" on public.papers;
create policy "Anyone can read papers" on public.papers for select using (true);
-- No insert/update/delete policy: only the secret key (the pipeline) can write.
grant select on public.papers to anon, authenticated;

-- Clear the vector when the text changes, so it gets embedded again
create or replace function public.papers_touch() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  if tg_op = 'UPDATE' and (new.title is distinct from old.title or new.abstract is distinct from old.abstract)
     and new.embedding::text is not distinct from old.embedding::text then
    new.embedding := null;
  end if;
  return new;
end $$;

drop trigger if exists papers_touch on public.papers;
create trigger papers_touch before insert or update on public.papers
  for each row execute function public.papers_touch();

-- Search by meaning: nearest papers to a query vector
create or replace function public.match_papers(
  query_embedding extensions.vector(384),
  match_count int default 20,
  since date default null
) returns table (
  id text, title text, authors text[], categories text[], first_seen date,
  featured boolean, code_url text, similarity float
)
language sql stable set search_path = '' as $$
  select p.id, p.title, p.authors, p.categories, p.first_seen, p.featured, p.code_url,
         1 - (p.embedding operator(extensions.<=>) query_embedding) as similarity
  from public.papers p
  where p.embedding is not null and (since is null or p.first_seen >= since)
  order by p.embedding operator(extensions.<=>) query_embedding
  limit least(match_count, 50);
$$;

-- For you: papers close to the average of what this browser has read
create or replace function public.recommend_papers(
  read_ids text[],
  match_count int default 12,
  since date default (current_date - 30)
) returns table (
  id text, title text, authors text[], categories text[], first_seen date,
  featured boolean, code_url text, similarity float
)
language sql stable set search_path = '' as $$
  with taste as (
    select extensions.avg(embedding) as v
    from public.papers
    where id = any(read_ids[1:50]) and embedding is not null
  )
  select p.id, p.title, p.authors, p.categories, p.first_seen, p.featured, p.code_url,
         1 - (p.embedding operator(extensions.<=>) taste.v) as similarity
  from public.papers p, taste
  where taste.v is not null and p.embedding is not null
    and not (p.id = any(read_ids)) and p.first_seen >= since
  order by p.embedding operator(extensions.<=>) taste.v
  limit least(match_count, 30);
$$;

-- Per-visitor request counts for the public functions (search, Project Scout).
-- RLS on with no policies: only the functions, using the secret key, can touch it.
create table if not exists public.rate_limits (
  bucket     text not null,
  window_at  timestamptz not null,
  hits       integer not null default 0,
  primary key (bucket, window_at)
);
alter table public.rate_limits enable row level security;

-- Count one hit and say whether the caller is still under the limit
create or replace function public.hit_rate_limit(bucket_key text, max_hits int, window_minutes int default 60)
returns boolean
language plpgsql security definer set search_path = '' as $$
declare
  w timestamptz := date_trunc('hour', now())
    + floor(extract(minute from now()) / window_minutes) * make_interval(mins => window_minutes);
  n int;
begin
  insert into public.rate_limits as r (bucket, window_at, hits) values (bucket_key, w, 1)
  on conflict (bucket, window_at) do update set hits = r.hits + 1
  returning hits into n;
  delete from public.rate_limits where window_at < now() - interval '1 day';
  return n <= max_hits;
end $$;
revoke all on function public.hit_rate_limit(text, int, int) from public, anon, authenticated;
grant execute on function public.hit_rate_limit(text, int, int) to service_role;
grant execute on function public.match_papers(extensions.vector, int, date) to anon, authenticated;
grant execute on function public.recommend_papers(text[], int, date) to anon, authenticated;

-- Anonymous reading counts and feedback, one row per paper per day.
-- No visitor data is kept: only totals. Only the functions (secret key) can write or read it.
create table if not exists public.paper_stats (
  paper_id   text not null,
  day        date not null default current_date,
  views      integer not null default 0,
  useful     integer not null default 0,
  not_useful integer not null default 0,
  primary key (paper_id, day)
);
alter table public.paper_stats enable row level security;

create or replace function public.bump_stat(pid text, what text)
returns void
language plpgsql security definer set search_path = '' as $$
begin
  if what not in ('view', 'useful', 'not_useful') then
    raise exception 'unknown stat %', what;
  end if;
  insert into public.paper_stats as s (paper_id, day, views, useful, not_useful)
  values (pid, current_date, (what = 'view')::int, (what = 'useful')::int, (what = 'not_useful')::int)
  on conflict (paper_id, day) do update set
    views = s.views + (what = 'view')::int,
    useful = s.useful + (what = 'useful')::int,
    not_useful = s.not_useful + (what = 'not_useful')::int;
end $$;

-- The most viewed papers of the last few days, for the "Most read" slot
create or replace function public.most_read(days int default 7, n int default 20)
returns table (paper_id text, views bigint, useful bigint, not_useful bigint)
language sql stable security definer set search_path = '' as $$
  select s.paper_id, sum(s.views), sum(s.useful), sum(s.not_useful)
  from public.paper_stats s
  where s.day > current_date - days and s.paper_id <> 'scout'
  group by s.paper_id
  order by sum(s.views) desc, sum(s.useful) desc
  limit least(n, 100);
$$;
revoke all on function public.bump_stat(text, text) from public, anon, authenticated;
revoke all on function public.most_read(int, int) from public, anon, authenticated;
grant execute on function public.bump_stat(text, text) to service_role;
grant execute on function public.most_read(int, int) to service_role;
