# Jobagent

Overvåger studiejob og praktikopslag i Region Hovedstaden på Jobindex, vurderer dem mod dit CV og dine fag med en fast rubrik og viser de bedste match i Kompas. Den søger aldrig selv: du beslutter, hvad du vil søge, og holder selv styr på dine ansøgninger.

**Kører automatisk** mandag og torsdag kl. 12:00 som en planlagt opgave i Claude-appen ("Karriere" under *Planlagte opgaver*). Opgavens prompt står i `rutine.md` og peger blot på `AGENT.md`. Er appen lukket på det tidspunkt, kører opgaven, næste gang appen åbnes.

## Hvor ligger hvad
| Fil/mappe | Hvad |
|---|---|
| `rapporter/ÅÅÅÅ-MM-DD.md` | Dagens rangerede liste med score, frist og begrundelse |
| `oversigt.csv` | Tracker over alt vurderet. `status` sættes på Kompas (vil søge, fravalgt, søgt, samtale, …) |
| `profil.md` | Dine fag, erfaring og ønsker. **Det er her, du tuner matchet** |
| `config.json` | Område, jobtyper, søgeord og tærskel for gode match (`match_taerskel`, standard 70) |
| `AGENT.md` | Instruktionerne, Claude følger ved hver kørsel |
| `rutine.md` | Prompten til den planlagte opgave i Claude-appen |
| `hent_jobs.py` | Henter opslag fra Jobindex (kun standardbibliotek) |
| `data/` | Intern tilstand: kø, behandlede opslag, vurderinger, `set.json`, `beslutninger.jsonl`, `frasorteret.log` |

## Dine egne filer
Dit CV, din profil og alt, agenten finder og skriver, er personligt og holdes ude af git (`.gitignore`). Kun eksemplerne er med:

| Rigtig fil | Eksempel | Hvem laver den |
|---|---|---|
| `profil.md` | `profil.example.md` (en opdigtet studerende, Alex) | Dig: `cp profil.example.md profil.md`, og skriv din egen |
| `cv.txt` | `cv.example.txt` | `hent_jobs.py` laver den fra `../CV.pdf` med `pdftotext` (Poppler). Uden PDF kan du skrive den selv |
| `../CV.pdf`, `../*karakterudskrift*.pdf` | – | Dig. De ligger i mappen *over* jobagenten (fx `Jobs/CV.pdf` med jobagenten i `Jobs/jobagent/`). Kompas viser kun filnavnene |
| `oversigt.csv` | `oversigt.example.csv` (viser formatet) | Agenten opretter den med header ved første kørsel |
| `rapporter/`, `data/` | – | Agenten og `hent_jobs.py` |

Alle stier er relative til mappen, filerne ligger i, så jobagenten kan ligge hvor som helst. I Kompas ligger den som `~/kompas/karriere`; er det et symlink (fx til en mappe med backup), følger stierne symlinket, så `../CV.pdf` er mappen over den rigtige jobagent-mappe.

## I Kompas
Fundene ligger også på **https://kompas.localhost/karriere/** (Nye match, Ansøgninger, Profil). Dér kan du sige "vil søge" eller "ikke interesseret", flytte dine ansøgninger fra "vil søge" til sendt, samtale og svar, og rette `profil.md` og tærsklen. Siden skriver kun `status` i `oversigt.csv`, `data/beslutninger.jsonl`, `profil.md` (gammel version i `data/profil-historik/`) og tærsklen i `config.json`. Den sender aldrig noget.

Under "Uafklarede" viser siden højst 50 opslag (`max_uafklarede_i_kompas` i `config.json`). Er der flere, skjules dem med lavest score. De bliver ikke slettet og ligger stadig under "Alle".

Holder virksomheden samtaler løbende, får opslaget mærket **Løbende samtaler** ved fristen. Stillingen kan så blive besat før fristen, så søg inden for få dage.

Siden leveres af `kompas_server.py` (kun standardbiblioteket), som kører i baggrunden (LaunchAgent `local.kompas.karriere`), til Luk Kompas slukker den. Siderne selv ligger i `kompas/`. Serveren lytter på `127.0.0.1:8766`; sæt `KARRIERE_PORT` for at bruge en anden port (fx til en testserver mod en kopi af mappen).

| Metode | Sti (under `/karriere`) | Hvad |
|---|---|---|
| GET | `/kompas.json` | Sidernes manifest til Kompas' menu (med en "nyt"-nøgle, når der er kommet opslag) |
| GET | `/api/data` | Alle opslag med status, score, frist, begrundelser og beslutninger, seneste rapport, profil, CV og søgeord |
| GET | `/api/opslag?id=<id>` | Opslagets tekst, som `hent_jobs.py` hentede den |
| POST | `/api/status` | `{"id", "status", "note"}` → `oversigt.csv` og `data/beslutninger.jsonl` |
| POST | `/api/profil` | `{"tekst"}` → `profil.md` |
| POST | `/api/taerskel` | `{"vaerdi"}` → `match_taerskel` i `config.json` |

Skrivninger tages kun imod fra `https://kompas.localhost` med `Content-Type: application/json`.

## Kør manuelt
```bash
python3 hent_jobs.py
```
Den henter kun nye opslag. Vil du også have dem vurderet med det samme, så tryk *Run now* på opgaven i Claude-appen.

Opdaterer du `../CV.pdf`, genereres `cv.txt` automatisk igen ved næste kørsel.
