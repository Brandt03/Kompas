#!/bin/zsh
# Exports Sure transactions (+ accounts, goals, budgets) to data.json for the dashboard pages served by Caddy at
# https://localhost/forbrug/ (Forbrug), /forbrug/su/ (SU-vagt) and /forbrug/gennemgang/.
# Run by launchd every 5 min (~/Library/LaunchAgents/local.sure.dashboard-export.plist).
set -euo pipefail
export PATH=/opt/homebrew/bin:$PATH
cd "$(dirname "$0")/.."
# SU-vagt reads state/su.json; until something is saved it is an empty {} (the pages read that as
# "nothing saved"), so the browser doesn't log a 404 on every visit. ln never replaces a file Sure has written.
for name in su; do
  f=dashboard/public/state/$name.json
  [[ -e $f ]] && continue
  t=$(mktemp dashboard/public/state/.$name.XXXXXX)
  print '{}' > "$t"; chmod 644 "$t"
  ln "$t" "$f" 2>/dev/null || true
  rm -f "$t"
done
# Sure runs on demand (Kompas.app) - skip quietly while it is stopped
colima status >/dev/null 2>&1 || exit 0
tmp=$(mktemp)
docker compose exec -T db psql -U sure_user -d sure_production -At -v ON_ERROR_STOP=1 -c "
-- Faste betalinger (Forbrug): Sure's own recurring detection only finds a few, so they are found here. A payee is the
-- merchant, or the bank text without VD/BS and card numbers, within one category. Monthly: paid in at least 3 of the
-- 6 months up to its latest payment, at most 1.5 times a month on average. Yearly: every payment 300-400 days apart.
-- Either way the last three payments (yearly: two) are within 15 % of their median, so a shop you happen to visit
-- monthly drops out. Active while the latest payment is at most 45 days (yearly: 400) old; stopped ones stay a year.
with pay as (
  select e.date, e.amount, e.name, m.name as merchant, c.name as category, coalesce(p.name, c.name) as grp,
         coalesce(lower(m.name), lower(regexp_replace(trim(regexp_replace(regexp_replace(e.name, '^(VD|BS) +', ''), '[0-9]+', '', 'g')), ' +', ' ', 'g')))
           || '|' || coalesce(c.id::text, '') as key
  from entries e
  join transactions t on t.id = e.entryable_id and e.entryable_type = 'Transaction'
  join accounts a on a.id = e.account_id and a.status = 'active' and not a.exclude_from_reports
  left join categories c on c.id = t.category_id
  left join categories p on p.id = c.parent_id
  left join merchants m on m.id = t.merchant_id
  where not e.excluded and e.amount > 0
    and t.kind not in ('funds_movement', 'cc_payment', 'loan_payment', 'investment_contribution')
    and coalesce(p.name, c.name, '') not in ('Indtægter', 'Opsparing og investering')
),
ranked as (
  select pay.*, row_number() over (partition by key order by date desc) as nr,
         max(date) over (partition by key) as last,
         date - lag(date) over (partition by key order by date) as gap
  from pay
),
monthly as (
  select key from ranked
  where date_trunc('month', date) >= date_trunc('month', last) - interval '5 months'
  group by key
  having count(distinct date_trunc('month', date)) >= 3
     and count(*) <= 1.5 * count(distinct date_trunc('month', date))
),
yearly as (
  select key from ranked group by key
  having count(*) >= 2 and min(gap) between 300 and 400 and max(gap) <= 400
),
found as (
  select key, 'måned' as interval from monthly
  union all
  select key, 'år' from yearly where key not in (select key from monthly)
),
stats as (
  -- before: the usual amount until the latest payment (monthly: within the same 6 months), to show a price change
  select f.key, f.interval,
         percentile_cont(0.5) within group (order by r.amount) filter (where r.nr <= 3) as median3,
         min(r.amount) filter (where r.nr <= 3) as min3, max(r.amount) filter (where r.nr <= 3) as max3,
         percentile_cont(0.5) within group (order by r.amount) filter (where r.nr > 1
           and (f.interval = 'år' or date_trunc('month', r.date) >= date_trunc('month', r.last) - interval '5 months')) as before,
         count(*) as n, min(r.date) as first,
         sum(r.amount) filter (where r.date > current_date - 365) as year_kr
  from found f join ranked r using (key)
  group by f.key, f.interval
),
faste as (
  select r.name, r.merchant, r.category, r.grp, s.interval, r.amount, r.date as last, s.n, s.first, s.year_kr,
         case when abs(r.amount - s.before) > greatest(0.05 * s.before, 1) then s.before end as before,
         r.date >= current_date - case s.interval when 'måned' then 45 else 400 end as active,
         (r.date + case s.interval when 'måned' then interval '1 month' else interval '1 year' end)::date as next
  from stats s join ranked r on r.key = s.key and r.nr = 1
  where s.min3 >= 0.85 * s.median3 and s.max3 <= 1.15 * s.median3
)
select json_build_object(
  'generated_at', to_char(now() at time zone 'Europe/Copenhagen', 'YYYY-MM-DD\"T\"HH24:MI:SS'),
  -- completed_at is a timestamp without time zone holding UTC (Rails): mark it as UTC first, then convert to Danish time
  'last_sync', (select to_char((max(completed_at) at time zone 'UTC') at time zone 'Europe/Copenhagen', 'YYYY-MM-DD\"T\"HH24:MI:SS') from syncs where status = 'completed'),
  -- for the monthly review (gennemgang.py): where the money is now, the savings goals and the monthly budget
  'accounts', (select coalesce(json_agg(json_build_object('name', name, 'balance', balance, 'classification', classification) order by name), '[]'::json)
               from accounts where status = 'active'),
  'goals', (select coalesce(json_agg(json_build_object('name', g.name, 'target', g.target_amount, 'target_date', g.target_date,
              'accounts', (select coalesce(json_agg(a.name order by a.name), '[]'::json) from goal_accounts ga join accounts a on a.id = ga.account_id
                           where ga.goal_id = g.id)) order by g.created_at), '[]'::json)
            from goals g where g.state = 'active'),
  'budgets', (select coalesce(json_agg(json_build_object('month', to_char(b.start_date, 'YYYY-MM'), 'spending', b.budgeted_spending, 'income', b.expected_income,
                'variable', (select bc.budgeted_spending from budget_categories bc join categories c on c.id = bc.category_id
                             where bc.budget_id = b.id and c.parent_id is null and c.name = 'Variable udgifter')) order by b.start_date), '[]'::json)
              from budgets b),
  -- for the monthly review (gennemgang.py): every category's own budget per month (subcategories add up to their group)
  'budget_categories', (select coalesce(json_agg(json_build_object('month', to_char(b.start_date, 'YYYY-MM'), 'category', c.name,
                          'group', coalesce(p.name, c.name), 'budget', bc.budgeted_spending) order by b.start_date, c.name), '[]'::json)
                        from budget_categories bc join budgets b on b.id = bc.budget_id join categories c on c.id = bc.category_id
                        left join categories p on p.id = c.parent_id),
  -- Faste betalinger on Forbrug (see faste above): active first, the biggest on top; pr_maaned counts a yearly one as 1/12
  'faste', json_build_object(
    'pr_maaned', (select coalesce(sum(case interval when 'måned' then amount else amount / 12 end), 0) from faste where active),
    'betalinger', (select coalesce(json_agg(json_build_object(
        'navn', name, 'merchant', merchant, 'kategori', category, 'gruppe', grp, 'interval', interval,
        'beloeb', amount, 'foer', before, 'sidst', last, 'naeste', case when active then next end, 'aktiv', active,
        'antal', n, 'foerste', first, 'sidste_aar', year_kr
      ) order by active desc, case when active then amount end desc nulls last, last desc), '[]'::json)
      from faste where active or last >= current_date - 365)),
  -- for changing a category on Forbrug: every category with its group (parent), parents before their children
  'categories', (select coalesce(json_agg(json_build_object('id', c.id, 'name', c.name, 'group', coalesce(p.name, c.name))
                   order by coalesce(p.name, c.name), p.id is not null, c.name), '[]'::json)
                 from categories c left join categories p on p.id = c.parent_id),
  'transactions', coalesce(json_agg(json_build_object(
      'id', e.id, 'date', e.date, 'amount', e.amount, 'name', e.name, 'account', a.name,
      'category', c.name, 'group', coalesce(p.name, c.name), 'merchant', m.name,
      -- trips and events (scripts/tag.rb, or tagged in Sure); Forbrug groups the spending by them
      'tags', (select coalesce(json_agg(tg.name order by tg.name), '[]'::json) from taggings tgg join tags tg on tg.id = tgg.tag_id
               where tgg.taggable_type = 'Transaction' and tgg.taggable_id = t.id)
    ) order by e.date, e.created_at), '[]'::json)
)
from entries e
join transactions t on t.id = e.entryable_id and e.entryable_type = 'Transaction'
join accounts a on a.id = e.account_id and a.status = 'active' and not a.exclude_from_reports
left join categories c on c.id = t.category_id
left join categories p on p.id = c.parent_id
left join merchants m on m.id = t.merchant_id
where not e.excluded
  and t.kind not in ('funds_movement', 'cc_payment', 'loan_payment', 'investment_contribution');
" > "$tmp"
mv "$tmp" dashboard/public/data.json
chmod 644 dashboard/public/data.json
