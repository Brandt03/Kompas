#!/bin/zsh
# Exports Sure transactions (+ accounts, goals, budgets) to data.json for the dashboard pages served by Caddy at
# https://localhost/forbrug/ (Forbrug), /forbrug/scenarier/ and /forbrug/su/ (SU-vagt).
# Run by launchd every 5 min (~/Library/LaunchAgents/local.sure.dashboard-export.plist).
set -euo pipefail
export PATH=/opt/homebrew/bin:$PATH
cd "$(dirname "$0")/.."
# Sure runs on demand (Kompas.app) - skip quietly while it is stopped
colima status >/dev/null 2>&1 || exit 0
tmp=$(mktemp)
docker compose exec -T db psql -U sure_user -d sure_production -At -v ON_ERROR_STOP=1 -c "
select json_build_object(
  'generated_at', to_char(now() at time zone 'Europe/Copenhagen', 'YYYY-MM-DD\"T\"HH24:MI:SS'),
  'last_sync', (select to_char(max(completed_at) at time zone 'Europe/Copenhagen', 'YYYY-MM-DD\"T\"HH24:MI:SS') from syncs where status = 'completed'),
  -- for the Scenarier page: where the money is now, the savings goals and the monthly budget
  'accounts', (select coalesce(json_agg(json_build_object('name', name, 'balance', balance, 'classification', classification) order by name), '[]'::json)
               from accounts where status = 'active'),
  'goals', (select coalesce(json_agg(json_build_object('name', name, 'target', target_amount, 'target_date', target_date) order by created_at), '[]'::json)
            from goals where state = 'active'),
  'budgets', (select coalesce(json_agg(json_build_object('month', to_char(b.start_date, 'YYYY-MM'), 'spending', b.budgeted_spending, 'income', b.expected_income,
                'variable', (select bc.budgeted_spending from budget_categories bc join categories c on c.id = bc.category_id
                             where bc.budget_id = b.id and c.parent_id is null and c.name = 'Variable udgifter')) order by b.start_date), '[]'::json)
              from budgets b),
  'transactions', coalesce(json_agg(json_build_object(
      'date', e.date, 'amount', e.amount, 'name', e.name, 'account', a.name,
      'category', c.name, 'group', coalesce(p.name, c.name), 'merchant', m.name
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
