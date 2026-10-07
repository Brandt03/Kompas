#!/bin/zsh
# Rebuilds the Excel reports from Sure into $SURE_EXCEL (e.g. a OneDrive folder):
#   Regnskab <år>.xlsx              current year, with the budget from "Budget <år>.xlsx" alongside
#   Tidligere år/Regnskab <år>      every earlier year since the first month with a balance
#                                   (so re-categorising old posts lands there too)
#   Tidligere år/Oversigt alle år   every year side by side
# Run by kompas-start.sh (after the bank sync) and kompas-stop.sh. Log: dashboard/excel.log
set -euo pipefail
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
PY=${SURE_PYTHON:-python3}   # needs openpyxl
cd "$(dirname "$0")/.."
BUDGET="${SURE_EXCEL:-$HOME/Budget}"
OLD="$BUDGET/Tidligere år"
Y=$(date +%Y)

colima status >/dev/null 2>&1 || exit 0   # Sure is stopped
[ -d "$BUDGET" ] || { echo "$(date '+%F %T') Mappen findes ikke: $BUDGET"; exit 1; }
mkdir -p "$OLD"

sql() { docker compose exec -T db psql -U sure_user -d sure_production -At -F';' -v ON_ERROR_STOP=1 -c "$1"; }
sql "select extract(year from e.date)::int, extract(month from e.date)::int, coalesce(p.name, c.name, '(ingen)'), coalesce(c.name, '(ingen)'), t.kind, round(sum(e.amount), 2)
     from entries e join transactions t on t.id = e.entryable_id and e.entryable_type = 'Transaction'
     left join categories c on c.id = t.category_id left join categories p on p.id = c.parent_id
     where not e.excluded and t.kind <> 'funds_movement' group by 1, 2, 3, 4, 5 order by 1, 2, 3, 4;" > scripts/monthly.csv
sql "select distinct on (date_trunc('month', b.date)) extract(year from b.date)::int, extract(month from b.date)::int,
            (select sum(b2.balance) from balances b2 where b2.date = b.date)
     from balances b order by date_trunc('month', b.date), b.date desc;" > scripts/balances.csv

$PY scripts/yearly_excel.py "$BUDGET" "$Y" --budget "$BUDGET/Budget $Y.xlsx"
FIRST=$(head -n 1 scripts/balances.csv | cut -d';' -f1)   # year of the first month with a balance
$PY scripts/yearly_excel.py "$OLD" $(seq "$FIRST" $((Y - 1)))
$PY scripts/yearly_overview.py "$OLD"

# New year: last year's report now lives in "Tidligere år" – drop the stale copy next to the budgets
[ -f "$BUDGET/Regnskab $((Y - 1)).xlsx" ] && rm -f "$BUDGET/Regnskab $((Y - 1)).xlsx"
echo "$(date '+%F %T') Excel opdateret"
