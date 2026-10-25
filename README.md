# Kompas

[![CI](https://github.com/Brandt03/Kompas/actions/workflows/ci.yml/badge.svg)](https://github.com/Brandt03/Kompas/actions/workflows/ci.yml)

**A personal dashboard that brings my finances, studies, languages, training and screen time together on one local page.**

Kompas runs entirely on my own Mac at `https://kompas.localhost`. Six small projects, written in Python and
JavaScript, each own one part of my life and publish their own pages. Kompas is the frame around them: one menu,
one design system, and a front page that pulls the day together across all of them.

> The interface is in Danish, because I built it for myself. This README and the overview are in English; the
> technical docs for each part are in Danish.

![Kompas, "I dag" (Today), with demo data](docs/skaermbilleder/i-dag.png)

*All screenshots use made-up demo data and are taken from the demo with `node demo/skaermbilleder.mjs`. Run it
yourself with `python3 demo/serve.py` (see below).*

## What it does

| Area | What I see | Built from |
|---|---|---|
| **I dag** (Today) | My day across everything: calendar with free gaps and what I actually did in each block, deadlines, readiness from my watch, sleep, training, self-study and screen time at a glance, habits that have stalled, this week's focus, flashcards and language cards due | `public/` |
| **Økonomi** (Money) | Spending by month or year (with a fix for a wrong category right on the page), "what if" scenarios, and a guard that warns before I earn too much to keep my student grant (SU) | `okonomi/` + [Sure](https://github.com/we-promise/sure) |
| **Studie** (Study) | Week plan, courses, deadlines, spaced-repetition flashcards, exam practice, self-study time against the course workload, exam notes week by week, and an offline phone app | `studie/` |
| **Sprog** (Languages) | A few minutes of spaced-repetition language cards a day, one active language at a time, a short weekly text to answer, and grammar rules picked from my own mistakes | `sprog/` |
| **Form & fokus** (Health) | 14-day training periods, every day and night measure from my watch, a daily recommendation, and a weekly review with planned against actual | `coach/` + `overblik/` |
| **Skærmtid** (Screen time) | Where the time goes on my Mac, desktop, laptop and phone, by category and hour of the day, with a weekly review | `skaermtid/` |
| **Forbindelser** (Connections) | Whether every data source, device, Claude routine and background job works, with how to fix it when one doesn't | `bin/forbindelser.py` |

| | |
|---|---|
| ![Study week overview](docs/skaermbilleder/studie.png) **Studie:** the week from my calendar, the plan for the week, and deadlines | ![Flashcards](docs/skaermbilleder/genkald.png) **Genkald:** today's flashcards, with how often "sure" was actually right |
| ![Self-study](docs/skaermbilleder/selvstudie.png) **Selvstudie:** study time against the course workload, with a daily goal, streak, medals and balance | ![Exam notes](docs/skaermbilleder/usb-noter.png) **USB-noter:** the notes I may bring to the exam, week by week, with my own rating of each week |
| ![14-day training periods](docs/skaermbilleder/perioder.png) **Form & fokus:** the 14-day report, its goals and the trend over periods | ![Body in numbers](docs/skaermbilleder/kroppen.png) **Kroppen i tal:** every day and night measure from the watch, with the night's sleep phases and curves |
| ![Planned against actual](docs/skaermbilleder/ugereview.png) **Ugereview:** planned against actual, calendar blocks against screen time per quarter hour and logged study | ![Screen time](docs/skaermbilleder/skaermtid.png) **Skærmtid:** all devices together, time on two devices at once counted once |
| ![Language overview](docs/skaermbilleder/sprog.png) **Sprog:** today's cards, progress per language and the week's text | ![Spending](docs/skaermbilleder/forbrug.png) **Forbrug:** where the money went over 12 months |
| ![Savings scenarios](docs/skaermbilleder/scenarier.png) **Scenarier:** 1,000 simulated futures for my savings | ![Student grant guard](docs/skaermbilleder/su.png) **SU-vagt:** income against the student grant limit |

<p align="center"><img src="docs/skaermbilleder/mobil.png" width="240" alt="Study flashcards on the phone, offline">
<img src="docs/skaermbilleder/sprog-mobil.png" width="240" alt="Language cards on the phone, offline">
<img src="docs/skaermbilleder/selvstudie-mobil.png" width="240" alt="Self-study on the phone"><br>
<em>On the phone: today's study and language cards work offline and sync later; self-study at a glance.</em></p>

Everything follows the system's light or dark mode ([light version of I dag](docs/skaermbilleder/i-dag-lys.png)).
[Forbindelser](docs/skaermbilleder/forbindelser.png) shows whether everything Kompas depends on works: it tests the
MCP server with a real handshake, reads the Claude routines' own schedules, and never reads secrets, only whether
they are set.

## How it fits together

```mermaid
flowchart LR
  subgraph Sources
    G[Garmin + Hevy]
    C[Calendar feeds]
    S[Sure budget app]
    N[Course notes]
  end
  subgraph Projects["Projects (folders here; separate repos on my Mac)"]
    coach[coach<br/>Python]
    liv[overblik<br/>Python]
    okonomi[okonomi<br/>shell + JS]
    studie[studie<br/>Node.js]
    sprog[sprog<br/>Node.js]
    skaerm[skaermtid<br/>Python]
  end
  AW[ActivityWatch<br/>on every device] --> skaerm --> liv
  G --> coach
  C --> coach
  coach --> liv
  S --> okonomi --> liv
  N --> studie
  liv -.->|week calendar| studie
  studie -.->|exam dates, own texts| sprog
  coach & liv & okonomi & studie & sprog & skaerm -->|pages + kompas.json| caddy[Caddy<br/>kompas.localhost]
  caddy --> shell[Kompas frame<br/>menu, I dag, design kit]
```

- **One contract.** Every project writes its pages plus a small `kompas.json` that describes them. The frame
  builds its menu from those files, so adding a project never touches the frame's code. Pages without data
  simply drop out instead of breaking the page.
- **Projects compute, pages show.** Numbers are calculated once, in the project that owns them, and written as
  JSON. The pages only display them, so the same figure never disagrees between two pages.
- **Local first.** Everything is served by Caddy on `localhost`, kept fresh by macOS LaunchAgents every 30
  minutes, and backed up daily. Nothing is hosted anywhere.
- **Read-only by default.** The pages only write what I type or click, and only through four servers:
  Studie's (flashcard answers and marks, definitions, drill guesses, weeks marked as read, "in my own words"
  notes, practice exams, my rating of the exam notes, deadlines marked done), Sprog's (grades and answers on
  language cards, answers to the week's text), Skærmtid's (my category for one app or site) and Sure's (the
  inputs on Scenarier and SU-vagt and a transaction's category on Forbrug, behind Sure's login). Studie's, Sprog's
  and Skærmtid's servers bind to `127.0.0.1`, answer only to Kompas' own host names (against DNS rebinding), accept
  writes only from Kompas' own origin, and validate every field before anything is saved.
- **Phone without a server.** The study and language pages work offline on my phone as small PWAs. They download
  today's cards while my Mac is reachable over Tailscale, and sync the answers back later without duplicates.
- **Laptop with or without the Mac.** My laptop gets all of Kompas over Tailscale on its own port. When the Mac is
  off, the laptop shows a read-only copy instead: `bin/kopi.py` writes the pages and their data to a folder every
  half hour, Syncthing carries it over, and a small Caddy on the laptop (`baerbar/`) serves it, marked
  "Kopi fra …" in the frame. Nothing can be saved in the copy.
- **AI where judgement is needed.** Scheduled Claude routines do the parts that need judgement: the weekly
  study plan, the 14-day training review, the weekly life review, new language cards with feedback on the
  week's text, and a weekly screen-time review. They only write files that the projects then show; they never send or submit anything.

The full architecture is in [docs/arkitektur.md](docs/arkitektur.md) (Danish). On my Mac each project is its own git
repository; this public repository gathers them as folders, cleaned of personal data, so its history starts at
publication.

## Try the demo

You only need Python 3.9 or newer; no packages, no accounts.

```bash
python3 demo/serve.py
```

Then open http://localhost:8000. The demo generates made-up data around today's date, so the calendar,
deadlines and countdowns look alive whenever you run it. The demo server refuses every write, so nothing is
saved on disk; only Scenarier and SU-vagt keep what you type in your own browser, as they do when Sure is closed.
Sure itself is not part of the demo (its menu items show a short explanation instead).

## The projects

### [coach/](coach/): training, sleep and recovery (Python, SQLite, MCP)

- Pulls my Garmin data, Hevy strength sets and calendar feeds into SQLite. Raw Garmin JSON is kept, so a broken
  unofficial endpoint never costs history, and a workout logged in both apps is counted once.
- `metrics.py` computes everything: acute:chronic workload, monotony, HRV and resting heart rate as deviations
  from a 60-day baseline, Banister TRIMP, strength load calibrated to TRIMP, and estimated 1RM. Gaps stay gaps
  (`null`, not 0), and each figure carries the reason it is or isn't shown.
- A local **MCP server** with 12 tools lets Claude answer questions about my training from finished aggregates
  instead of doing arithmetic on raw series. Its SQL lookup is read-only, enforced by SQLite itself.
- `site byg` writes the pages' JSON atomically, plus the daily recommendation shown on the front page.
- **Kroppen i tal** shows every day and night measure Garmin has (sleep phases, heart rate, HRV, SpO2, breathing,
  stress, body battery, steps) day by day, in the style of garmin-grafana, without Grafana.

### [overblik/](overblik/): the weekly review (Python)

- One row per ISO week across training, money and study, built from Garmin data, the Sure extract and the
  calendar.
- Flags unusual weeks with a robust z-score (median/MAD) against the previous 8 weeks. When most weeks are
  identical (say, nothing spent on cafés), a week only stands out if it falls outside all 8 weeks and differs
  from the median by a fixed amount per column (100 kr., half an hour of training), so 899 kr. after weeks of
  900 kr. is not news.
- Instead of mining every pair of columns for correlations, it tests 11 fixed hypotheses, Bonferroni-corrected.
  Each week is compared with its neighbours (up to 4 weeks, as many on each side) before testing, so a shared
  drift over the semester doesn't count as a link, and p-values come from a block permutation (blocks of 3
  weeks), because neighbouring weeks resemble each other. In simulations this cut false "strong" links from 39 %
  to under 1 % for drifting series, and from 100 % to 0 % for a shared seasonal pattern, while still finding a
  real week-to-week link 90 % of the time.
- Training load comes from coach (TRIMP), the same number everywhere.
- **Planned against actual:** each calendar block of the last 14 days next to what the screen showed per quarter
  hour (from Skærmtid), the self-study I logged and my workouts, so a planned study block that turned into social
  media is visible. A habit that stalls (no study blocks for days) shows up on the front page.

### [studie/](studie/): study planner and flashcards (Node.js)

- **The files are the database.** The server reads and writes my own markdown notes (answers, ✓/~/✗ marks,
  definitions) and JavaScript drills. A guess is written into the drill file, the file is run with Node, and
  JavaScript itself decides whether the guess was right. If the file breaks, it is restored.
- **Spaced repetition without hidden state.** Today's cards are computed from an append-only JSONL log and
  scheduled with FSRS-6: a card comes back when I'm predicted to recall it with 90 % probability, and before an exam
  when it would otherwise be below 95 % on the day. New questions only come from weeks I have marked as read, and the page shows
  how often an answer was actually right when I said I was sure.
- **A new semester is a new `fag.json`.** The code knows no courses: one file lists the semester's courses and
  what each has (recall questions, a glossary, code drills, numbered hand-ins, exam form), and exam dates are read
  from my notes. A test runs the server on a made-up semester and fails if a course id is hardcoded.
- **Offline first on the phone.** *På farten* downloads a package of today's cards over Tailscale, queues
  answers without a connection, and sends them later. Each answer has an id, so sending twice is harmless. A
  service worker serves the pages from cache.
- **No dependencies.** Plain Node.js with its own small markdown renderer and a mini XML reader that turns my
  Word course notes into HTML with images.
- **Careful writes.** Only Kompas may write (Host, Origin and JSON content-type checks), and files are written
  atomically (a unique temp file + rename). A drill guess is parsed as a plain value (numbers, strings, lists,
  objects, `NaN`, `undefined` …) and written back in the server's own form, so a guess can never run as code.
- **In my own words.** Each week on a course page has a field for explaining the material without the book, saved
  in the course folder and also editable offline on the phone, and the lecture slides and exercises for the week
  sit right next to it.
- **Self-study against the workload.** Each course description states its hours; Selvstudie compares the time I log
  with them, with a daily goal, a streak, medals, a running balance and a month calendar. Weeks I'm away and
  teaching I don't use don't count.
- **Exam notes.** For courses that allow notes at the exam, a routine fills the notes document week by week; I
  rate each week (useful, too much, missing something) and the routine tightens it accordingly.
- **Answer first, then the key.** The pages only ask for the answer key after an attempt. That is a habit the
  interface keeps, not a lock: `GET /facit` and `/eksamen/facit` return the key whenever they are asked.

### [sprog/](sprog/): language practice (Node.js + a Claude routine)

- **One language at a time.** The active language gets three new cards a day and a short weekly text; another
  can be kept up with one card a day or paused, and Danish and English are "study languages" with cards made from
  my own mistakes in what I write for my courses. During the 14 days before an exam there are no new cards, only
  review, so studying gets the time. The exam dates are read from Studie's export.
- **The same repetition as Studie.** Today's queue is computed from an append-only log with FSRS-6, at most 15
  due cards a day, one language after another so similar languages don't blur.
- **Judgement in a routine, writes in code.** A Sunday Claude routine follows [RUTINE.md](sprog/RUTINE.md): it sets
  the level from a placement test (never in advance), writes new cards by situation (restaurant, transport …), a
  grammar rule picked from my own mistakes with fill-in cards that practise it, the week's text, and feedback on
  my answer. It can only write through `sprog.js`, which validates everything before it is saved, so the data is
  never half-written or invalid.
- **Offline on the phone** like Studie: a package of today's cards, the texts and the rules, answers queued without
  a connection and synced later with an id each. The phone's own text-to-speech reads the answer aloud.

### [skaermtid/](skaermtid/): screen time across devices (Python)

- [ActivityWatch](https://activitywatch.net) runs on every device; aw-sync and Syncthing bring the other devices'
  data to the Mac, so the project reads one local server only.
- Apps, sites and window titles are sorted into categories and groups by regular expressions in `regler.json`; the
  rest I can categorise on the page with one click, through a small server that only writes my choices.
- **Time on two devices at once counts once.** If the phone's screen is on, the time goes to the phone; otherwise
  it is split between the computers in use. Each device still shows its own full time.
- **Only sums leave ActivityWatch:** hours per day, device, category and app, and a quarter-hour timeline. Window
  titles are only used to match a rule and are never written.
- The demo runs the real calculation on made-up ActivityWatch events for four devices.

### [okonomi/](okonomi/): money, on top of Sure (shell, SQL, JavaScript, a little Ruby)

- [Sure](https://github.com/we-promise/sure) runs untouched in Docker. My additions are mounted as Rails
  initializers that check that what they change exists and switch themselves off otherwise, so updating Sure
  never breaks it.
- `export.sh` builds the whole extract as JSON inside Postgres in one query, every 5 minutes, so the pages keep
  working when Sure and Docker are closed.
- **Forbrug** shows spending by month, year or any period, and a wrong category can be fixed right in the list of
  transactions. The change goes through Sure and does what Sure's own form does (locks the category so rules and
  bank syncs leave it alone); the page shows it at once and the next extract has it. "Uge for uge" shows variable
  spending for the last 12 weeks, from the weekly review.
- **Scenarier** is a Monte Carlo simulation (1,000 runs) that samples my own variable spending from history,
  models returns as log-normal, shows everything in today's money, and uses binary search to find the smallest
  extra monthly saving that reaches a goal with 80 % probability.
- **SU-vagt** knows the 2026 rules for the Danish student grant: the monthly income limits, converting net pay
  to taxable income, what an overshoot costs to pay back, and which months it pays to opt out of the grant.
- One app starts everything (Caddy, LaunchAgents, Docker, Sure, bank sync, export), and one closes it again,
  with a verified `pg_dump` backup and 30-day rotation on the way out.

## Tests

Every push runs [CI](.github/workflows/ci.yml): the demo is generated and served on Python 3.9 and 3.13, coach's
smoke test and its pytest suite run against its real dependencies, overblik has its own pytest suite, and
[tests/](tests/) checks the parts that matter most:

- **Overblik's statistics:** a week that stands out from identical weeks is flagged, a shared seasonal pattern is
  not reported as a link, and a real week-to-week link is still found.
- **Sprog:** the routine's commands reject an invalid card before anything is saved and skip duplicates, today's
  queue keeps one language at a time with the active one first, there are no new cards in the 14 days before an
  exam, and the server refuses foreign host names and writes from other origins and saves a synced answer once.
- **Coach's numbers** against known answers: Banister TRIMP, ACWR (1.0 for even load, 1.6 when the last week
  doubles), HRV as standard deviations from the baseline, and gaps that stay gaps instead of turning into zeros.
- **Studie's drill guesses** are parsed as values: known code-injection attempts are refused.
- **Studie's spaced repetition:** FSRS gives known answers for first reviews, longer intervals for easier grades, and
  pulls a card forward before an exam; new questions alternate between courses, oldest week first; and
  answers synced from the phone are saved once, even when the same answer is sent twice. "In my own words" from
  the phone is refused if the same week was rewritten on the Mac in the meantime.
- **Dates are local:** the study server runs in a foreign time zone in the test, and a week marked as read or a
  deadline marked done still gets the Danish date. Times are read from the plan's date column.
- **Coach's failure modes:** a network outage is not reported as a wrong password, calendar addresses are masked
  before they reach a log, a failed Hevy sync is visible, and a 14-day period must run Saturday to Friday.
- **Overblik:** one broken source no longer stops the others, a calendar's freshness is when it was fetched, and
  the week to plan follows the report's Monday, not the day the routine happens to run.
- **Skærmtid:** time on two devices at once is counted once, a late night belongs to the evening before, and the server refuses
  foreign hosts and origins, unknown categories and oversized or malformed choices.
- **The laptop copy** never writes outside its folder, even if a course or file name in the data contains `..`.
- **I dag** shows everything else when one section's data is broken, and a paused project disappears everywhere.

```bash
python3 -m unittest discover -s tests
for t in tests/test_*.js; do node "$t"; done
pip install -e './coach[dev]' && python3 -m pytest -q coach/tests
PYTHONPATH=overblik python3 -m pytest -q overblik/tests
```

## Running it for real

**Status: a personal project, not a product.** Kompas is built for my own everyday life on my own Mac, so the
demo is the easy way to see all of it. Running it with your own data takes some adapting:

- It is macOS only (LaunchAgents, zsh, Docker via Colima for Sure).
- Each part is set up on its own: Caddy, Sure, Garmin and calendar feeds, Hevy, ActivityWatch, and Tailscale and
  Syncthing for the phone and laptop.
  There is no single installer.
- The LaunchAgents, the small app that starts and stops everything, and most of the scheduled Claude routines
  are not in the repository.
- It assumes Danish student grant (SU) rules and a Danish university's calendar and course files, and the
  interface is in Danish.

Each project has its own README with setup and environment variables. The short version: clone into `~/kompas`,
import the `Caddyfile` into Caddy, set up each project you want, and point the LaunchAgents at `bin/opdater.sh`
and the Studie, Sprog and Skærmtid servers. See [docs/arkitektur.md](docs/arkitektur.md).

## How I built it

I designed and built Kompas with [Claude Code](https://claude.com/claude-code) as my pair programmer. I decided
what each part should do and how the parts fit together. I reviewed and tested the changes, and I use the
system every day. The scheduled AI routines above are part of the design: they run inside clear rules (what
they may read, what they may write, and that they never act on my behalf).

## License

My code is MIT licensed (see [LICENSE](LICENSE)). The Geist font (OFL), Lucide icons (ISC) and Sure's design
tokens (AGPL-3.0) keep their own licences, and the small add-ons in `okonomi/custom/` that run inside Sure are
AGPL-3.0 like Sure. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) lists the files and where their licence
texts are.
