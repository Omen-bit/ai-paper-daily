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
-- (dropped first so a changed result list can be applied by rerunning this file)
drop function if exists public.match_papers(extensions.vector, int, date);
create or replace function public.match_papers(
  query_embedding extensions.vector(384),
  match_count int default 20,
  since date default null
) returns table (
  id text, title text, authors text[], categories text[], submitted date, first_seen date,
  featured boolean, code_url text, similarity float
)
language sql stable set search_path = '' as $$
  select p.id, p.title, p.authors, p.categories, p.submitted, p.first_seen, p.featured, p.code_url,
         1 - (p.embedding operator(extensions.<=>) query_embedding) as similarity
  from public.papers p
  where p.embedding is not null and (since is null or p.first_seen >= since)
  order by p.embedding operator(extensions.<=>) query_embedding
  limit least(match_count, 50);
$$;

-- Keyword search for Project Scout. Exact terms such as "Whisper" or "LoRA" are
-- found by words even when meaning search ranks them low.
alter table public.papers add column if not exists fts tsvector
  generated always as (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, ''))) stored;
create index if not exists papers_fts_idx on public.papers using gin (fts);

-- Hybrid search: the closest papers by meaning and the best keyword matches,
-- merged with reciprocal rank fusion (k = 60). Any of the query's words can
-- match (OR), so a long description still finds papers.
drop function if exists public.hybrid_papers(extensions.vector, text, int);
create or replace function public.hybrid_papers(
  query_embedding extensions.vector(384),
  query_text text,
  match_count int default 30
) returns table (
  id text, title text, authors text[], categories text[], submitted date, first_seen date,
  featured boolean, code_url text, hf_upvotes int, similarity float, rrf float
)
language sql stable set search_path = '' as $$
  with q as (
    select case when plainto_tsquery('english', query_text)::text = '' then null
                else to_tsquery('english', replace(plainto_tsquery('english', query_text)::text, ' & ', ' | ')) end as tsq
  ),
  semantic as (
    select p.id, row_number() over (order by p.embedding operator(extensions.<=>) query_embedding) as r
    from public.papers p
    where p.embedding is not null
    order by p.embedding operator(extensions.<=>) query_embedding
    limit least(match_count, 60)
  ),
  keyword as (
    select p.id, row_number() over (order by pg_catalog.ts_rank_cd(p.fts, q.tsq) desc) as r
    from public.papers p, q
    where q.tsq is not null and p.fts operator(pg_catalog.@@) q.tsq
    order by pg_catalog.ts_rank_cd(p.fts, q.tsq) desc
    limit least(match_count, 60)
  ),
  fused as (
    select coalesce(s.id, k.id) as id,
           coalesce(1.0 / (60 + s.r), 0) + coalesce(1.0 / (60 + k.r), 0) as rrf
    from semantic s full outer join keyword k on s.id = k.id
  )
  select p.id, p.title, p.authors, p.categories, p.submitted, p.first_seen, p.featured, p.code_url, p.hf_upvotes,
         case when p.embedding is null then 0 else 1 - (p.embedding operator(extensions.<=>) query_embedding) end as similarity,
         f.rrf
  from fused f join public.papers p on p.id = f.id
  order by f.rrf desc
  limit least(match_count, 60);
$$;
grant execute on function public.hybrid_papers(extensions.vector, text, int) to anon, authenticated;

-- For you: papers close to the average of what this browser has read
drop function if exists public.recommend_papers(text[], int, date);
create or replace function public.recommend_papers(
  read_ids text[],
  match_count int default 12,
  since date default (current_date - 30)
) returns table (
  id text, title text, authors text[], categories text[], submitted date, first_seen date,
  featured boolean, code_url text, similarity float
)
language sql stable set search_path = '' as $$
  with taste as (
    select extensions.avg(embedding) as v
    from public.papers
    where id = any(read_ids[1:50]) and embedding is not null
  )
  select p.id, p.title, p.authors, p.categories, p.submitted, p.first_seen, p.featured, p.code_url,
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

-- Anonymous site-wide counts that test whether the papers section is worth
-- choosing over Hugging Face: clicks on our pick vs the trending card, the
-- "Seen this already?" answers, new vs returning visitors, where each day's
-- first visit came from (src_*), and sign-ups (subscribe_rss, subscribe_email).
-- Totals per day only, no visitor data. Read them with site_report().
create table if not exists public.site_stats (
  day   date not null default current_date,
  event text not null,
  n     integer not null default 0,
  primary key (day, event)
);
alter table public.site_stats enable row level security;

create or replace function public.bump_site(what text)
returns void
language plpgsql security definer set search_path = '' as $$
begin
  if what !~ '^(visit_(new|return_7d|return_old)|click_(pick|trending|runner_up|most_read)|seen_(pick|trending|runner_up|most_read)_(yes|no)|scout_(click|save|dismiss|more|case|brief)|breakdown_load|out_(pdf|arxiv|hf|code)|src_(direct|google|bing|duckduckgo|hn|reddit|x|linkedin|github|producthunt|discord|telegram|newsletter|rss|other)|subscribe_(rss|email|confirmed))$' then
    raise exception 'unknown site event %', what;
  end if;
  insert into public.site_stats as s (day, event, n) values (current_date, what, 1)
  on conflict (day, event) do update set n = s.n + 1;
end $$;

-- Totals over the last few days. In the SQL editor: select * from site_report(28);
create or replace function public.site_report(days int default 28)
returns table (event text, total bigint)
language sql stable security definer set search_path = '' as $$
  select s.event, sum(s.n) from public.site_stats s
  where s.day > current_date - days
  group by s.event order by s.event;
$$;
revoke all on function public.bump_site(text) from public, anon, authenticated;
revoke all on function public.site_report(int) from public, anon, authenticated;
grant execute on function public.bump_site(text) to service_role;
grant execute on function public.site_report(int) to service_role;

-- Full text for "Ask this paper". A paper is read from arXiv the first time someone
-- asks about it (or in advance for the daily picks), split into sections, and kept.
-- Papers nobody asks about for 30 days are removed by prune_fulltext().
-- RLS on with no policies: only the functions (secret key) can read or write these.
create table if not exists public.paper_fulltext (
  paper_id    text primary key,
  status      text not null check (status in ('ready', 'none')),  -- none: no readable full text
  source      text,
  n_sections  integer not null default 0,
  fetched_at  timestamptz not null default now(),
  last_asked  timestamptz
);
alter table public.paper_fulltext enable row level security;

create table if not exists public.paper_sections (
  paper_id  text not null references public.paper_fulltext(paper_id) on delete cascade,
  idx       integer not null,
  heading   text not null default '',
  body      text not null,
  tsv       tsvector generated always as
              (setweight(to_tsvector('english', heading), 'A') || to_tsvector('english', body)) stored,
  primary key (paper_id, idx)
);
alter table public.paper_sections enable row level security;
create index if not exists paper_sections_tsv on public.paper_sections using gin (tsv);

-- The passages of one paper that best match a question. Any word of the question may
-- match (OR), ranked by how well. With no match, the paper's opening passages.
create or replace function public.match_sections(pid text, q text, n int default 5)
returns table (idx int, heading text, body text, rank real)
language plpgsql security definer set search_path = '' as $$
declare
  words text := replace(plainto_tsquery('english', coalesce(q, ''))::text, ' & ', ' | ');
  query tsquery;
begin
  update public.paper_fulltext set last_asked = now() where paper_id = pid;
  if words <> '' then
    query := to_tsquery('english', words);
    return query
      select s.idx, s.heading, s.body, ts_rank_cd(s.tsv, query)
      from public.paper_sections s
      where s.paper_id = pid and s.tsv @@ query
      order by 4 desc, s.idx
      limit least(n, 10);
    if found then return; end if;
  end if;
  return query
    select s.idx, s.heading, s.body, 0::real
    from public.paper_sections s
    where s.paper_id = pid
    order by s.idx
    limit least(n, 10);
end $$;

-- The full breakdown on each paper page: the paper's own contributions, results
-- tables, limitations and conclusion, copied from arXiv's HTML version by plain
-- code, plus at most one short AI summary. Made once per paper and kept.
-- RLS on with no policies: only the functions (secret key) can read or write it.
create table if not exists public.paper_breakdown (
  paper_id    text primary key,
  status      text not null check (status in ('ready', 'none')),  -- none: no usable web version
  data        jsonb,
  summary     text,
  summary_at  timestamptz,
  made_at     timestamptz not null default now()
);
alter table public.paper_breakdown enable row level security;
create index if not exists paper_breakdown_summary_at on public.paper_breakdown (summary_at);

-- Forget papers nobody has asked about lately. Papers with no readable full text are
-- retried after a week, since arXiv sometimes adds the HTML version later.
create or replace function public.prune_fulltext(days int default 30)
returns integer
language plpgsql security definer set search_path = '' as $$
declare gone int;
begin
  delete from public.paper_fulltext
  where coalesce(last_asked, fetched_at) < now() - make_interval(days => days)
     or (status = 'none' and fetched_at < now() - interval '7 days');
  get diagnostics gone = row_count;
  -- Breakdowns are kept, except "no web version" ones, which are tried again after a week
  delete from public.paper_breakdown where status = 'none' and made_at < now() - interval '7 days';
  return gone;
end $$;
revoke all on function public.match_sections(text, text, int) from public, anon, authenticated;
revoke all on function public.prune_fulltext(int) from public, anon, authenticated;
grant execute on function public.match_sections(text, text, int) to service_role;
grant execute on function public.prune_fulltext(int) to service_role;

-- Company case studies (data/cases.json), so Scout can suggest teams that built something
-- like the visitor's project. The pipeline writes rows; the embed function fills the vector.
create table if not exists public.cases (
  url        text primary key,
  company    text not null,
  title      text not null,
  published  date,
  problem    text not null default '',      -- the Case studies topic, e.g. rag, agents, cost
  summary    text not null default '',
  issue      text not null default '',
  result     text not null default '',
  tags       text[] not null default '{}',
  embedding  extensions.vector(384),        -- gte-small over title, problem, solution and tags
  updated_at timestamptz not null default now()
);
create index if not exists cases_missing_embedding_idx on public.cases (url) where embedding is null;
-- Case study finder tags (case_sources.TECHNIQUES, INDUSTRIES, BUILD_DETAILS); empty until a post is tagged
alter table public.cases add column if not exists techniques text[];
alter table public.cases add column if not exists industry text;
alter table public.cases add column if not exists build_details jsonb;
alter table public.cases add column if not exists build_score smallint;
alter table public.cases enable row level security;
drop policy if exists "Anyone can read cases" on public.cases;
create policy "Anyone can read cases" on public.cases for select using (true);
grant select on public.cases to anon, authenticated;

-- Clear the vector when the text changes, so it gets embedded again
create or replace function public.cases_touch() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  if tg_op = 'UPDATE' and (new.title is distinct from old.title or new.summary is distinct from old.summary
     or new.issue is distinct from old.issue or new.tags is distinct from old.tags)
     and new.embedding::text is not distinct from old.embedding::text then
    new.embedding := null;
  end if;
  return new;
end $$;
drop trigger if exists cases_touch on public.cases;
create trigger cases_touch before insert or update on public.cases
  for each row execute function public.cases_touch();

-- Scout: the case studies closest in meaning to a project. A few hundred rows, so no index is needed.
drop function if exists public.match_cases(extensions.vector, int);
create or replace function public.match_cases(
  query_embedding extensions.vector(384),
  match_count int default 12
) returns table (
  url text, company text, title text, published date, problem text, summary text, issue text, result text,
  tags text[], similarity float
)
language sql stable set search_path = '' as $$
  select c.url, c.company, c.title, c.published, c.problem, c.summary, c.issue, c.result, c.tags,
         1 - (c.embedding operator(extensions.<=>) query_embedding) as similarity
  from public.cases c
  where c.embedding is not null
  order by c.embedding operator(extensions.<=>) query_embedding
  limit least(match_count, 30);
$$;
grant execute on function public.match_cases(extensions.vector, int) to anon, authenticated;

-- Write-ups readers suggest for the Case studies page (supabase/functions/suggest writes them,
-- src/case_suggestions.py checks and publishes them, supabase/functions/suggest-admin lists and
-- reviews them for the owner). Nobody else can read or write: RLS is on with no policies, and only
-- the service role (the functions and the pipeline) is granted access.
create table if not exists public.case_suggestions (
  id            bigint generated always as identity primary key,
  url           text not null,
  canonical_url text not null,
  note          text not null default '',
  credit        text not null default '',
  status        text not null default 'new',
  checks        jsonb not null default '{}'::jsonb,   -- link_works, about_ai, not_on_site, has_build_details, announcement, ...
  topic         text,
  techniques    text[],
  industry      text,
  build_details jsonb,
  build_score   smallint,
  title         text,
  company       text,
  problem       text,
  solution      text,
  card          jsonb,                                -- the record the pipeline publishes to data/cases.json
  created_at    timestamptz not null default now(),
  reviewed_at   timestamptz,
  ip_hash       text not null default ''
);
alter table public.case_suggestions drop constraint if exists case_suggestions_status_check;
alter table public.case_suggestions add constraint case_suggestions_status_check
  check (status in ('new', 'checked', 'approved', 'rejected', 'duplicate'));
alter table public.case_suggestions drop constraint if exists case_suggestions_text_check;
alter table public.case_suggestions add constraint case_suggestions_text_check
  check (char_length(url) <= 2000 and char_length(note) <= 280 and char_length(credit) <= 40);
-- One open suggestion per post; a rejected one can be suggested again
create unique index if not exists case_suggestions_open_url on public.case_suggestions (canonical_url)
  where status in ('new', 'checked', 'approved', 'duplicate');
create index if not exists case_suggestions_status_idx on public.case_suggestions (status, created_at);
alter table public.case_suggestions enable row level security;
revoke all on public.case_suggestions from anon, authenticated;
grant all on public.case_suggestions to service_role;
