# SPDX-License-Identifier: AGPL-3.0-only (runs inside Sure, so it is licensed like Sure)
#
# Adds our own tabs to Sure's left menu (right after Budgets/Plan) and shows the Caddy-served dashboard pages
# inside Sure's own layout:
#   Forbrug    /forbrug-side    -> https://localhost/forbrug/
#   Scenarier  /scenarier-side  -> https://localhost/forbrug/scenarier/
#   SU-vagt    /su-side         -> https://localhost/forbrug/su/
#
# The pages keep their settings (payslip figures, scenario inputs) as JSON in dashboard/public/state/, which
# Caddy serves read-only at /forbrug/state/<name>.json. Writes go through PUT /dashboard-state/<name> below,
# so they need a signed-in Sure session.
#
# Mounted read-only into the web container by compose.override.yml – Sure's image is untouched, so
# `docker compose pull` keeps working. Remove the override (or this file) to get stock Sure back.
#
# How the menu entries are added without copying Sure's templates: at boot we copy Sure's own
# layouts/shared/_nav_item partial to a temp view dir under a new name, and put a thin
# _nav_item wrapper in front of it that renders the original and, after Budgets, our extra items.
require "fileutils"

module DashboardTabs
  VIEW_DIR = Rails.root.join("tmp", "dashboard_tab_views")
  STATE_DIR = Pathname.new("/rails/custom_state")
  STATE_NAMES = %w[su scenarier].freeze
  STATE_MAX_BYTES = 256.kilobytes

  # name, Sure path, iframe src, lucide icon
  TABS = [
    [ "Forbrug", "/forbrug-side", "/forbrug/", "wallet" ],
    [ "Scenarier", "/scenarier-side", "/forbrug/scenarier/", "chart-spline" ],
    [ "SU-vagt", "/su-side", "/forbrug/su/", "graduation-cap" ]
  ].freeze

  def self.install!
    upstream = Rails.root.join("app", "views", "layouts", "shared", "_nav_item.html.erb")
    return Rails.logger.warn("[dashboard] #{upstream} not found – menu items skipped") unless upstream.exist?

    dir = VIEW_DIR.join("layouts", "shared")
    FileUtils.mkdir_p(dir)
    FileUtils.cp(upstream, dir.join("_nav_item_upstream.html.erb"))
    items = TABS.map do |name, path, _src, icon|
      %(<%= render "layouts/shared/nav_item_upstream", name: "#{name}", path: "#{path}", icon: "#{icon}",
              icon_custom: false, active: request.path.start_with?("#{path}") %>)
    end
    File.write(dir.join("_nav_item.html.erb"), <<~ERB)
      <%= render "layouts/shared/nav_item_upstream", **local_assigns %>
      <% if [budgets_path, (plan_path rescue nil)].compact.include?(local_assigns[:path]) %>
        #{items.join("\n  ")}
      <% end %>
    ERB
    ActionController::Base.prepend_view_path(VIEW_DIR.to_s)
  end
end

Rails.application.config.to_prepare do
  DashboardTabs.install!

  unless defined?(::DashboardTabsController)
    klass = Class.new(ApplicationController) do
      # Plain JSON PUTs from our own same-origin pages. Cross-site requests can't send a JSON body without a
      # CORS preflight (which Rails never approves) and don't carry the Lax session cookie, so no CSRF token.
      skip_forgery_protection only: :save_state

      def show
        name, _path, src, = DashboardTabs::TABS.find { |_, path, _| path == request.path }
        render inline: <<~ERB, layout: "application", locals: { name: name, src: src }
          <% content_for :title, name %>
          <iframe src="<%= src %>" title="<%= name %>"
                  style="display:block;width:100%;height:calc(100dvh - 2rem);border:0;border-radius:12px;background:transparent"></iframe>
        ERB
      end

      def save_state
        name = params[:name].to_s
        return head(:not_found) unless DashboardTabs::STATE_NAMES.include?(name)
        return head(:unsupported_media_type) unless request.media_type == "application/json"

        body = request.body.read(DashboardTabs::STATE_MAX_BYTES + 1).to_s
        return head(:content_too_large) if body.bytesize > DashboardTabs::STATE_MAX_BYTES

        data = JSON.parse(body)
        return head(:unprocessable_entity) unless data.is_a?(Hash)

        data["saved_at"] = Time.current.iso8601
        file = DashboardTabs::STATE_DIR.join("#{name}.json")
        tmp = DashboardTabs::STATE_DIR.join(".#{name}.json.tmp")
        File.write(tmp, JSON.pretty_generate(data))
        File.rename(tmp, file)
        render json: { saved_at: data["saved_at"] }
      rescue JSON::ParserError
        head :unprocessable_entity
      end
    end
    Object.const_set(:DashboardTabsController, klass)
  end
end

Rails.application.routes.append do
  DashboardTabs::TABS.each { |_, path, _| get path, to: "dashboard_tabs#show" }
  put "/dashboard-state/:name", to: "dashboard_tabs#save_state", constraints: { name: /[a-z]+/ }
end
