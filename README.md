# Kompas

**A personal dashboard that brings my finances, studies, training and job search together on one local page.**

Kompas runs entirely on my own Mac at `https://kompas.localhost`. Five small projects, written in Python and
JavaScript, each own one part of my life and publish their own pages. Kompas is the frame around them: one menu,
one design system, and a front page that pulls the day together across all of them.

> The interface is in Danish, because I built it for myself. This README and the overview are in English; the
> technical docs for each part are in Danish.

![Kompas, "I dag" (Today), with demo data](docs/skaermbilleder/i-dag.png)

*All screenshots use made-up demo data. Run it yourself with `python3 demo/serve.py` (see below).*

## What it does

| Area | What I see | Built from |
|---|---|---|
| **I dag** (Today) | My day across everything: calendar with free gaps, deadlines, readiness from my watch, this week's focus, flashcards due, new job matches | `public/` |
| **Økonomi** (Money) | Spending by month, "what if" scenarios, and a guard that warns before I earn too much to keep my student grant (SU) | `okonomi/` + [Sure](https://github.com/we-promise/sure) |
| **Studie** (Study) | Week plan, courses, deadlines, spaced-repetition flashcards, exam practice, and an offline phone app | `studie/` |
| **Form & fokus** (Health) | 14-day training periods, sleep and recovery, a daily recommendation, and a weekly review | `coach/` + `overblik/` |
| **Karriere** (Career) | A job agent that finds student jobs every morning and scores them against my profile, with the reasons and gaps for each | `karriere/` |

| | |
|---|---|
| ![Study week overview](docs/skaermbilleder/studie.png) **Studie:** the week from my calendar, the plan for the week, and deadlines | ![Flashcards](docs/skaermbilleder/genkald.png) **Genkald:** today's flashcards, with how often "sure" was actually right |
| ![14-day training periods](docs/skaermbilleder/perioder.png) **Form & fokus:** the 14-day report, its goals and the trend over periods | ![Sleep and recovery](docs/skaermbilleder/soevn.png) **Søvn & restitution:** 60 nights against my own baseline |
| ![Job matches](docs/skaermbilleder/karriere.png) **Karriere:** scored job matches with reasons and gaps | ![Spending](docs/skaermbilleder/forbrug.png) **Forbrug:** where the money went over 12 months |
| ![Savings scenarios](docs/skaermbilleder/scenarier.png) **Scenarier:** 1,000 simulated futures for my savings | ![Student grant guard](docs/skaermbilleder/su.png) **SU-vagt:** income against the student grant limit |

<p align="center"><img src="docs/skaermbilleder/mobil.png" width="260" alt="Flashcards on the phone, offline"><br>
<em>On the phone: today's cards work offline and sync later.</em></p>

Everything follows the system's light or dark mode ([light version of I dag](docs/skaermbilleder/i-dag-lys.png)).

## How it fits together

```mermaid
flowchart LR
  subgraph Sources
    G[Garmin + Hevy]
    C[Calendar feeds]
    S[Sure budget app]
    J[Job listings]
    N[Course notes]
  end
  subgraph Projects["Projects (each its own repo)"]
    coach[coach<br/>Python]
    liv[overblik<br/>Python]
    okonomi[okonomi<br/>shell + JS]
    karriere[karriere<br/>Python]
    studie[studie<br/>Node.js]
  end
  G --> coach
  C --> coach
  coach --> liv
  S --> okonomi --> liv
  J --> karriere
  N --> studie
  liv -.->|week calendar| studie
  coach & liv & okonomi & karriere & studie -->|pages + kompas.json| caddy[Caddy<br/>kompas.localhost]
  caddy --> shell[Kompas frame<br/>menu, I dag, design kit]
```

- **One contract.** Every project writes its pages plus a small `kompas.json` that describes them. The frame
  builds its menu from those files, so adding a project never touches the frame's code. Pages without data
  simply drop out instead of breaking the page.
- **Projects compute, pages show.** Numbers are calculated once, in the project that owns them, and written as
  JSON. The pages only display them, so the same figure never disagrees between two pages.
- **Local first.** Everything is served by Caddy on `localhost`, kept fresh by macOS LaunchAgents every 30
  minutes, and backed up daily. Nothing is hosted anywhere.
- **Read-only by default.** Only three things can write through the pages, and only what I type or click:
  job decisions, flashcard answers, and marking a deadline done. Each server binds to `127.0.0.1`, answers only
  to Kompas' own host names (against DNS rebinding), and accepts writes only from Kompas' own origin.
- **Phone without a server.** The study pages work offline on my phone as a small PWA. It downloads today's
  cards while my Mac is reachable over Tailscale, and syncs the answers back later without duplicates.
- **AI where judgement is needed.** Scheduled Claude routines do the parts that need judgement: the weekly
  study plan, the 14-day training review, the weekly life review and scoring job listings. They only write
  files that the projects then show; they never send or submit anything.

The full architecture is in [docs/arkitektur.md](docs/arkitektur.md) (Danish).

## Try the demo

You only need Python 3.9 or newer; no packages, no accounts.

```bash
python3 demo/serve.py
```

Then open http://localhost:8000. The demo generates made-up data around today's date, so the calendar,
deadlines and countdowns look alive whenever you run it. It never saves anything. Sure itself is not part of
the demo (its menu items show a short explanation instead).

## The projects

### [coach/](coach/): training, sleep and recovery (Python, SQLite, MCP)

- Pulls my Garmin data, Hevy strength sets and calendar feeds into SQLite. Raw Garmin JSON is kept, so a broken
  unofficial endpoint never costs history, and a workout logged in both apps is counted once.
- `metrics.py` computes everything: acute:chronic workload, monotony, HRV and resting heart rate as deviations
  from a 60-day baseline, Banister TRIMP, strength load calibrated to TRIMP, and estimated 1RM. Gaps stay gaps
  (`null`, not 0), and each figure carries the reason it is or isn't shown.
- A local **MCP server** with 11 tools lets Claude answer questions about my training from finished aggregates
  instead of doing arithmetic on raw series. Its SQL lookup is read-only, enforced by SQLite itself.
- `site byg` writes the pages' JSON atomically, plus the daily recommendation shown on the front page.

### [overblik/](overblik/): the weekly review (Python)

- One row per ISO week across training, money and study, built from Garmin data, the Sure extract and the
  calendar.
- Flags unusual weeks with a robust z-score (median/MAD) against the previous 8 weeks, with a fallback when
  most weeks are identical (say, nothing spent on cafés), so one unusual week still stands out.
- Instead of mining every pair of columns for correlations, it tests 11 fixed hypotheses, Bonferroni-corrected.
  Each week is compared with its neighbours (4 weeks on each side) before testing, so a shared drift over the
  semester doesn't count as a link, and p-values come from a block permutation (blocks of 3 weeks), because
  neighbouring weeks resemble each other. In simulations this cut false "strong" links from 39 % to under 1 %
  for drifting series, and from 100 % to 0 % for a shared seasonal pattern, while still finding a real
  week-to-week link 90 % of the time.
- Training load comes from coach (TRIMP), the same number everywhere.

### [studie/](studie/): study planner and flashcards (Node.js)

- **The files are the database.** The server reads and writes my own markdown notes (answers, ✓/~/✗ marks,
  definitions) and JavaScript drills. A guess is written into the drill file, the file is run with Node, and
  JavaScript itself decides whether the guess was right. If the file breaks, it is restored.
- **Spaced repetition without hidden state.** Today's cards are computed from an append-only JSONL log, with
  intervals of 3/7/21/60/120 days. New questions only come from weeks I have marked as read, and the page shows
  how often an answer was actually right when I said I was sure.
- **Offline first on the phone.** *På farten* downloads a package of today's cards over Tailscale, queues
  answers without a connection, and sends them later. Each answer has an id, so sending twice is harmless. A
  service worker serves the pages from cache.
- **No dependencies.** Plain Node.js with its own small markdown renderer and a mini XML reader that turns my
  Word course notes into HTML with images.
- **Careful writes.** Only Kompas may write (Host, Origin and JSON content-type checks), files are written
  atomically (temp file + rename), and the answer key is only shown after an attempt. A drill guess is parsed as
  a plain value (numbers, strings, lists, objects, `NaN`, `undefined` …) and written back in the server's own
  form, so a guess can never run as code.

### [karriere/](karriere/): job agent (Python + a Claude routine)

- A deterministic fetcher (standard library only) reads new student-job listings, pre-filters them with weighted
  word lists and queues the relevant ones.
- A scheduled Claude routine follows [AGENT.md](karriere/AGENT.md): it scores each listing 0–100 on a fixed
  five-part rubric with caps, and writes down why it fits and what is missing. Listings are treated as data, not
  instructions (prompt-injection defence), and the routine only writes its assessments; it never applies for
  anything or contacts anyone.
- I decide in Kompas (want to apply, or not interested and why). The decisions are logged and read by the next
  run, which uses them as a signal and suggests changes to the profile or filters without making them itself.
- A small standard-library HTTP server with exactly three narrow writes (status, profile, threshold), taken one
  at a time under a lock with atomic file writes, Host checks against DNS rebinding, Origin/Content-Type checks
  against CSRF, and path-traversal guards.

### [okonomi/](okonomi/): money, on top of Sure (shell, SQL, JavaScript, a little Ruby)

- [Sure](https://github.com/we-promise/sure) runs untouched in Docker. My additions are mounted as Rails
  initializers that check that what they change exists and switch themselves off otherwise, so updating Sure
  never breaks it.
- `export.sh` builds the whole extract as JSON inside Postgres in one query, every 5 minutes, so the pages keep
  working when Sure and Docker are closed.
- **Scenarier** is a Monte Carlo simulation (1,000 runs) that samples my own variable spending from history,
  models returns as log-normal, shows everything in today's money, and uses binary search to find the smallest
  extra monthly saving that reaches a goal with 80 % probability.
- **SU-vagt** knows the 2026 rules for the Danish student grant: the monthly income limits, converting net pay
  to taxable income, what an overshoot costs to pay back, and which months it pays to opt out of the grant.
- One app starts everything (Caddy, LaunchAgents, Docker, Sure, bank sync, export), and one closes it again,
  with a verified `pg_dump` backup and 30-day rotation on the way out.

## Running it for real

**Status: a personal project, not a product.** Kompas is built for my own everyday life on my own Mac, so the
demo is the easy way to see all of it. Running it with your own data takes some adapting:

- It is macOS only (LaunchAgents, zsh, Docker via Colima for Sure).
- Each part is set up on its own: Caddy, Sure, Garmin and calendar feeds, Hevy, and Tailscale for the phone.
  There is no single installer.
- The LaunchAgents, the small app that starts and stops everything, and most of the scheduled Claude routines
  are not in the repository.
- It assumes three courses, Danish student grant (SU) rules and Danish job listings, and the interface is in
  Danish.

Each project has its own README with setup and environment variables. The short version: clone into `~/kompas`,
import the `Caddyfile` into Caddy, set up each project you want, and point the LaunchAgents at `bin/opdater.sh`
and the two small servers. See [docs/arkitektur.md](docs/arkitektur.md).

## How I built it

I designed and built Kompas with [Claude Code](https://claude.com/claude-code) as my pair programmer. I decided
what each part should do and how the parts fit together. I reviewed and tested the changes, and I use the
system every day. The scheduled AI routines above are part of the design: they run inside clear rules (what
they may read, what they may write, and that they never act on my behalf).

## License

My code is MIT licensed (see [LICENSE](LICENSE)). The Geist font (OFL), Lucide icons (ISC) and Sure's design
tokens (AGPL-3.0) keep their own licences, and the small add-ons in `okonomi/custom/` that run inside Sure are
AGPL-3.0 like Sure.
