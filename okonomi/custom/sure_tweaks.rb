# Small UI fixes on top of stock Sure, mounted read-only by compose.override.yml (like dashboard_tabs.rb).
# Every patch checks its anchor first and logs + skips if upstream has changed, so `docker compose pull`
# can never break the app – at worst a tweak silently turns itself off.
#
# 1. Budgets: a subcategory without its own budget shares the parent's pool, and upstream therefore
#    also shares the parent's "Over budget" status – every empty sibling showed "Over by 500,00 kr.".
#    Now a shared subcategory with no spending is never "over"; it is hidden like upstream already
#    does for on-track ones.
# 2. Cash-flow Sankey: nodes kept in a stable tree order (Surplus on top, siblings by size, children
#    grouped under their parent) instead of d3's free relaxation, which dropped e.g. a small fixed
#    expense below Surplus. Surplus sits in the category column, Monarch-style.
# 3. MTD/LM follow the SU month: SU is paid on the last banking day of the month before, so a calendar
#    MTD showed no income. "Current month" now starts on the latest SU payment (category "SU") from the
#    last week of a month, and "last month" ends the day before. The date comes from the transactions;
#    with no such payment, or a custom month start set in Sure, upstream's calendar month is used.
require "digest"
require "fileutils"

module SureTweaks
  module QuietSharedSubcategories
    def over_budget?
      return false if inherits_parent_budget? && !actual_spending.to_d.positive?
      super
    end
  end

  module SuMonth
    SU_CATEGORY = "SU"

    def current_month_for(family)
      return super if family.nil? || family.uses_custom_month_start?

      new(key: "current_month", start_date: SuMonth.start_for(family, Date.current), end_date: Date.current)
    end

    def last_month_for(family)
      return super if family.nil? || family.uses_custom_month_start?

      end_date = SuMonth.start_for(family, Date.current) - 1.day
      new(key: "last_month", start_date: SuMonth.start_for(family, end_date), end_date: end_date)
    end

    # Start of the SU month containing `date`: the latest SU payment from the last week of the
    # previous month (or of this month, once next month's SU has arrived), else the 1st.
    def self.start_for(family, date)
      bom = date.beginning_of_month
      su_ids = Transaction.joins(:category).where(categories: { family_id: family.id, name: SU_CATEGORY }).select(:id)
      dates = Entry.joins(:account).where(accounts: { family_id: family.id })
        .where(entryable_type: "Transaction", entryable_id: su_ids)
        .where(date: (bom - 7.days)..date).where("entries.amount < 0").distinct.pluck(:date)
      dates.select { |d| d < bom || d >= date.end_of_month - 6.days }.max || bom
    end
  end

  # pin_all_from directories win over single pins in importmap-rails, so an override has to be
  # merged in after the directories are expanded.
  module ImportmapOverrides
    def self.pins = (@pins ||= {})

    private

    def expanded_packages_and_directories
      super.tap do |paths|
        ImportmapOverrides.pins.each do |name, path|
          paths[name] = Importmap::Map::MappedFile.new(name: name, path: path, preload: true)
        end
      end
    end
  end

  SANKEY_ANCHOR = ".nodePadding(nodePadding)"
  SANKEY_ORDER_JS = <<~JS

    // --- sure_tweaks.rb: stable, Monarch-style node order -------------------------------
    // Walks the graph outwards from the Cash Flow node. Each node's key is its path of
    // sibling ranks (Surplus first, then largest first), so children stay grouped under
    // their parent in every column.
    function sureTweaksNodeOrder(nodes, links) {
      const root = nodes.findIndex((n) => n.id === "cash_flow_node");
      if (root < 0) return undefined;

      const neighbours = nodes.map(() => []);
      links.forEach((l) => {
        neighbours[l.source].push(l.target);
        neighbours[l.target].push(l.source);
      });

      const keys = new Map([[nodes[root].id, []]]);
      const queue = [root];
      while (queue.length) {
        const current = queue.shift();
        const children = [...new Set(neighbours[current])]
          .filter((i) => !keys.has(nodes[i].id))
          .sort((a, b) =>
            (nodes[b].id === "surplus_node") - (nodes[a].id === "surplus_node") ||
            nodes[b].value - nodes[a].value);
        children.forEach((i, rank) => {
          keys.set(nodes[i].id, keys.get(nodes[current].id).concat(rank));
          queue.push(i);
        });
      }

      return (a, b) => {
        const ka = keys.get(a.id) || [], kb = keys.get(b.id) || [];
        for (let i = 0; i < Math.min(ka.length, kb.length); i++) {
          if (ka[i] !== kb[i]) return ka[i] - kb[i];
        }
        return ka.length - kb.length;
      };
    }
  JS

  def self.install_sankey_override!
    source = Rails.root.join("app", "javascript", "controllers", "sankey_chart_controller.js")
    js = source.exist? && source.read
    unless js && js.scan(SANKEY_ANCHOR).size == 1 && js.include?("#generateSankeyData(nodes, links,")
      return Rails.logger.warn("[sure_tweaks] sankey anchor not found – Sankey tweak skipped")
    end

    patched = js.sub(SANKEY_ANCHOR,
      "#{SANKEY_ANCHOR}\n      .nodeAlign((node) => node.depth)\n      .nodeSort(sureTweaksNodeOrder(nodes, links))") + SANKEY_ORDER_JS

    dir = Rails.public_path.join("sure-tweaks")
    FileUtils.mkdir_p(dir)
    file = "sankey_chart_controller-#{Digest::SHA256.hexdigest(patched)[0, 12]}.js"
    File.write(dir.join(file), patched) unless dir.join(file).exist?

    ImportmapOverrides.pins["controllers/sankey_chart_controller"] = "/sure-tweaks/#{file}"
    Importmap::Map.prepend(ImportmapOverrides) unless Importmap::Map < ImportmapOverrides
  rescue => e
    Rails.logger.warn("[sure_tweaks] Sankey tweak skipped: #{e.class}: #{e.message}")
  end
end

Rails.application.config.to_prepare do
  if BudgetCategory.method_defined?(:inherits_parent_budget?)
    BudgetCategory.prepend(SureTweaks::QuietSharedSubcategories) unless BudgetCategory < SureTweaks::QuietSharedSubcategories
  else
    Rails.logger.warn("[sure_tweaks] BudgetCategory#inherits_parent_budget? missing – budget tweak skipped")
  end

  if Period.respond_to?(:current_month_for) && Period.respond_to?(:last_month_for) && Family.method_defined?(:uses_custom_month_start?)
    Period.singleton_class.prepend(SureTweaks::SuMonth) unless Period.singleton_class < SureTweaks::SuMonth
  else
    Rails.logger.warn("[sure_tweaks] Period.current_month_for missing – SU month tweak skipped")
  end
end

Rails.application.config.after_initialize { SureTweaks.install_sankey_override! }
