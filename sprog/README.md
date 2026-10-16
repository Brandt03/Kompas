# Sprog

Sprog-delen af Kompas (`/sprog/`): holder fremmedsprog ved lige og bygger ét af dem op ad gangen, på under en time
om ugen og mest på telefonen. Dansk og engelsk er studiesprog: kort af brugerens egne fejl i det, de skriver i
Studie, og akademiske vendinger.

Kun koden er med her. Kortene, svarene og ugens tekster ligger i `data/`, som ikke er i git. Demoen
(`demo/projekter/sprog.py`) laver opdigtede data i samme form.

## Sådan virker det

- **Dagens kort** (5-8 min om dagen, `side/mobil.html`): ét sprog ad gangen, det aktive først. Se forsiden, sig eller
  skriv svaret, vis svaret (og lyt til det med telefonens stemme), marker 1-4. Repetitionen er FSRS som i Studie.
  Virker på telefonen uden net: siden henter en pakke, mens Mac'en er vågen, og sender svarene bagefter.
- **Ugens tekst** (10-15 min om ugen): en kort tekst på det aktive sprog, som brugeren svarer på i et par
  sætninger. Rutinen retter svaret søndag og laver kort af fejlene.
- **Ét aktivt sprog ad gangen** med tre nye kort om dagen. Et fremmedsprog, der ikke er aktivt, holdes ved lige
  (ét nyt kort om dagen) eller står på pause (ingen nye; gentagelsen fortsætter).
- **Eksamensperiode**: fra 14 dage før en eksamen i Studie til og med eksamensdagen kommer der ingen nye sprogkort og
  ingen ny tekst, kun gentagelse. Datoerne læses fra Studies eksport (`~/.kompas/studie/studie.json`, kun læsning).
- **Regler** (`side/regler.html` og fanen Regler på telefonen): én ny sprogregel om ugen på det aktive sprog og én
  på dansk, valgt ud fra brugerens egne fejl. Kort forklaring på dansk, eksempler og typiske fejl. Reglen øves med
  `udfyld`-kort, der peger på den (`"regel": "es-ser-estar"`) og kommer først blandt de nye kort; "Øv reglen" tager
  dem som en ekstra runde.
- **Niveauet** sættes af rutinen ud fra en niveautest (de første kort), aldrig på forhånd.

| Rolle | Nye kort om dagen | Hvad |
|---|---|---|
| aktiv | 3 | situationer fra rejse og hverdag, ugens tekst |
| vedligehold | 1 | samme slags, færre |
| pause | 0 | kortene bliver liggende; `sprog.js rolle <sprog> vedligehold` eller `aktivt <sprog>` tager det op igen |
| studie (dansk, engelsk) | 1 hver, når der er nogle | egne fejl, ugens ord, akademiske vendinger |

Højst 15 forfaldne kort om dagen; nye kort og niveautesten kommer oveni. Standarden (`STANDARD` i `kerne.js`) er
spansk som aktivt sprog og tysk, dansk og engelsk ved siden af.

## Filerne

| Fil | Hvad |
|---|---|
| `kerne.js` | data, FSRS, Dagens kort, pakke og sync (fælles for serveren og kommandoerne) |
| `server.js` | serveren bag `/sprog/` (127.0.0.1:8769, LaunchAgent `local.kompas.sprog`): siderne, `kompas.json` og API'et |
| `sprog.js` | rutinens kommandoer: `rapport`, `tilfoej`, `tekst`, `feedback`, `regel`, `niveau`, `aktivt`, `rolle` (se toppen af filen) |
| `side/` | Oversigt (`index.html`), Dagens kort, Ugens tekst og Regler på telefonen (`mobil.html`), Regler (`regler.html`), visningen af en regel (`regel.js`), service worker og ikoner |
| `RUTINE.md` | instruktionerne til rutinen Sprog (`sprog-ugen`), søndag aften |
| `data/` | **ikke i git**: `sprog.json`, `kort.json`, `log.jsonl` (svarene), `tekster/<uge>.json`, `regler.json` |

Testen ligger i Kompas' `tests/test_sprog.js` (midlertidig datamappe og egen port).

Serveren skriver kun det, brugeren selv taster eller klikker (`log.jsonl`): karakteren og svaret på et kort og
svaret på ugens tekst. Kort, tekster, regler, feedback og niveau skriver rutinen gennem `sprog.js`, som tjekker
alt, før det gemmes. Serveren svarer kun på Kompas' egne værtsnavne (mod DNS rebinding) og tager kun imod skrivninger
fra Kompas' egen origin. JavaScript uden afhængigheder; Node 18 eller nyere.

## Drift

| Hvad | Hvordan | Log |
|---|---|---|
| Sprog-serveren | LaunchAgent `local.kompas.sprog` (startes og lukkes med Kompas-appen) | `~/.kompas/sprog-server.log` |
| Telefonen | `tailscale serve` → Caddy `127.0.0.1:8768` → `/sprog/` (sat op med `bin/tailscale-mobil.sh`) | |
| Backup af `data/` | `bin/backup-data.sh` (dagligt + ved Luk Kompas), `sprog-<dato>.tar.gz` | |
| Rutinen | Sprog (`sprog-ugen`) i Claude-appen, søndag aften | Rutiner i Claude-appen |

Genstart: `launchctl kickstart -k gui/$(id -u)/local.kompas.sprog`. Gendan data:
`tar xzf <backup>.tar.gz -C ~/kompas/sprog` (luk serveren først).

Test skrivninger mod en kopi: `SPROG_DATA=<mappe> SPROG_PORT=18769 node server.js`, og `SPROG_DATA=<mappe> node sprog.js …`.
`SPROG_STUDIE_JSON=<fil>` peger på en anden eksport fra Studie (eksamensdatoerne), og `KOMPAS_SEMESTER` på
semestermappen, som rutinen læser brugerens egne tekster fra.

På telefonen: åbn `https://<mac>.<tailnet>.ts.net/sprog/mobil.html` og vælg Føj til startskærm. Til oplæsning bruger
siden telefonens tekst til tale; hent sprogene under telefonens indstillinger, så virker det også uden net.

## Kendt dublering

FSRS-modellen (`fsrs`, `planlæg`) er kopieret fra Studie-serveren (`studie/Scripts/kompas-server.js`), så Sprog ikke
afhænger af semestrets mappe. Pakke og sync følger samme mønster, men er skrevet enkelt for Sprog. Ændres
FSRS-parametrene ét sted, så ret dem begge steder.
