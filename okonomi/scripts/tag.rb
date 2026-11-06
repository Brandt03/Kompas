# SPDX-License-Identifier: AGPL-3.0-only (runs inside Sure, so it is licensed like Sure)
#
# Puts a tag (a trip or an event, e.g. "Lissabon") on the spending between two dates, so Forbrug can show it as one.
# You ask for it in a chat; the dry run lists what would be tagged, you confirm, then it is applied.
# Spending = money out, outside the groups Faste udgifter, Indtægter and Opsparing og investering (rent and
# subscriptions are not part of a trip). Like Sure's own tag rule it adds the tag, keeps the others, and locks the
# tags so a rule can't change them. --fjern removes the tag from the same transactions instead.
#
# Usage (from the okonomi folder):
#   docker compose cp scripts/tag.rb web:/tmp/tag.rb
#   docker compose exec -T web bin/rails runner /tmp/tag.rb "Lissabon" 2026-05-03 2026-05-09 [options] [apply]
# Options: --uden <entry id>[,<id>…]  leave these out    --med <entry id>[,<id>…]  add these (any group or date)
#          --kun <entry id>[,<id>…]   exactly these (a trip picked by place, not by dates; then no dates)
#          --fjern                     remove the tag instead
# Default is a dry run, rolled back. The entry ids are the "id" in Forbrug's data.json and in the dry run.
APPLY = ARGV.delete("apply")
REMOVE = ARGV.delete("--fjern")
opt = ->(name) { i = ARGV.index(name) or return []; ARGV.slice!(i, 2).last.to_s.split(",") }
WITHOUT = opt.("--uden")
WITH = opt.("--med")
ONLY = opt.("--kun")
name, from, to = ARGV
abort "Brug: tag.rb <tag> (<fra YYYY-MM-DD> <til YYYY-MM-DD> [--uden ids] [--med ids] | --kun ids) [--fjern] [apply]" unless name && (ONLY.any? || (from && to))
OUTSIDE = [ "Faste udgifter", "Indtægter", "Opsparing og investering" ].freeze
KINDS = %w[funds_movement cc_payment loan_payment investment_contribution].freeze  # transfers, as in export.sh

family = Family.first
entries = family.entries.where(entryable_type: "Transaction", excluded: false).joins(:account)
  .where(accounts: { status: "active" })
if ONLY.any?
  picked = entries.where(id: ONLY).to_a.sort_by(&:date)
  missing = ONLY - picked.map(&:id)
  abort "Findes ikke (eller er udeladt i Sure): #{missing.join(', ')}" if missing.any?
else
  from, to = Date.iso8601(from), Date.iso8601(to)
  spend = entries.where(date: from..to).where("entries.amount > 0").select do |e|
    t = e.transaction
    group = t.category&.parent&.name || t.category&.name
    !KINDS.include?(t.kind) && !OUTSIDE.include?(group)
  end
  picked = (spend.reject { |e| WITHOUT.include?(e.id) } + entries.where(id: WITH).to_a).uniq.sort_by(&:date)
end

ActiveRecord::Base.transaction do
  tag = REMOVE ? family.tags.find_by(name: name) : family.tags.find_or_create_by!(name: name)
  abort "Intet tag hedder #{name}" unless tag
  picked.each do |e|
    t = e.transaction
    ids = REMOVE ? t.tag_ids - [ tag.id ] : (t.tag_ids + [ tag.id ]).uniq
    puts format("%s  %10.2f  %-34s %-28s %s", e.date, e.amount, e.name[0, 34], t.category&.name.to_s[0, 28], e.id)
    next if ids == t.tag_ids
    t.tag_ids = ids
    t.lock_attr!(:tag_ids)
  end
  puts "#{picked.size} posteringer, i alt #{picked.sum(&:amount).round(2)} kr. #{REMOVE ? 'uden' : 'med'} tagget #{name}"
  unless APPLY
    puts "Prøvekørsel – intet gemt. Tilføj apply for at gemme."
    raise ActiveRecord::Rollback
  end
end
