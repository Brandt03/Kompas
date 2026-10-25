# Få Telefon, Stationær og Bærbar med i Skærmtid

Trin for trin. Værtsnavne og stier herunder er eksempler: Mac'en hedder `macbook.local` (se `hostname` på Mac'en), og
`<bruger>` er dit brugernavn på enheden.

Sådan hænger det sammen: ActivityWatch logger på hver enhed. Syncthing holder én mappe, **ActivityWatchSync**,
ens på alle tre. aw-sync lægger hver enheds tal i mappen, og Mac'en henter de andres ind i sin ActivityWatch,
som Skærmtid læser.

```
Telefon    ActivityWatch-appen (Sync Settings) ─────────────┐
Stationær  ActivityWatch → aw-sync (Opgavestyring, 30 min) ─┼→ ActivityWatchSync (Syncthing)
Mac        ActivityWatch ⇄ aw-sync (opdater.sh, 30 min) ────┘        ↓
                                                    Mac'ens ActivityWatch → skaermtid.py byg → siden
```

Det skal du bruge undervejs:

| Hvad | Værdi |
|---|---|
| Mac'ens Syncthing-id (offentligt, ikke hemmeligt) | `<MAC-ID>`: Mac'ens Syncthing-side → Handlinger → Vis id |
| Mappens navn | `ActivityWatchSync` |
| Mappe-ID (skal være præcis dette, ellers kobles mapperne ikke) | `aw-sync` |
| Mac'ens Syncthing-side | http://127.0.0.1:8384 (på Mac'en) |

Først Mac'en: ActivityWatch kører (med tilladelsen Tilgængelighed), Syncthing (fx Syncthing.app fra Homebrew) kører og
starter ved login, mappen `~/ActivityWatchSync` deles som `aw-sync` med `(?d)*.tmp` i sin `.stignore`, og
`~/kompas/bin/opdater.sh` kører aw-sync hvert 30. minut.

## Telefon (Android)

### T1. ActivityWatch-appen

1. Installer **ActivityWatch** fra F-Droid (pakken `net.activitywatch.android`, version 0.14.0 eller nyere),
   Google Play eller https://github.com/ActivityWatch/aw-android/releases/latest (`aw-android-arm64-v8a.apk`).
2. Åbn den, og tillad notifikationer, når den spørger.
3. Giv den **Adgang til brugsdata**: søg på `brugsdata` i Indstillinger → **Adgang til brugsdata** →
   **ActivityWatch** → slå **Tillad adgang til brugsdata** til.
4. Spørger den om **Web browsing tracking** (hjælpefunktioner), så vælg **No thanks**. Skærmtid tæller kun
   apps på telefonen, ikke hjemmesider.

Tjek: efter et par minutters brug viser appens forside dagens apps.

### T2. Batteri: lad begge apps køre i baggrunden

Mange Android-telefoner lukker apps i baggrunden, og så stopper både logningen og synkroniseringen. Menuerne
hedder lidt forskelligt fra mærke til mærke.

1. Indstillinger → **Apps** → **ActivityWatch** → **Batteriforbrug** → slå **Tillad baggrundsaktivitet** til.
   Står der i stedet **Batterioptimering**, så vælg **Optimer ikke** eller **Ubegrænset**.
2. Gør det samme for **Syncthing-Fork**.

### T3. Mappen i Syncthing-Fork

1. Åbn Syncthing-Fork. Tjek under **Enheder**, at Mac'en står som **Forbundet**.
2. Gå til **Mapper**, og tryk **+**.
3. **Mappenavn:** `ActivityWatchSync`.
4. **Mappe-ID:** slet det foreslåede, og skriv `aw-sync`.
5. **Mappe:** vælg **Intern lagerplads**, opret en ny mappe `ActivityWatchSync`, og vælg den. Beder appen om
   **Adgang til alle filer**, så tillad det.
6. Under enhederne: slå **Mac'en** til (den hedder fx `macbook.local`, hvis du ikke gav den et andet navn).
7. **Mappetype:** lad den stå på **Send og modtag**. Gem med fluebenet øverst.

Tjek: mappen står som **Opdateret** inden for et minut, og den indeholder `macbook.local`. På Mac'ens
Syncthing-side forsvinder fodnoten "Fjernenheden har ikke accepteret deling af denne mappe".

### T4. Sync i ActivityWatch-appen

1. Sync Settings ligger i appens egen sidemenu, ikke i menuen bag ☰. Åbn sidemenuen: sæt fingeren helt ude ved
   **venstre kant** midt på skærmen, hold den stille et øjeblik, og træk så mod højre (et hurtigt stryg bliver til
   "tilbage"). Nederst under **Misc** står **Sync Settings**. Vil den ikke komme frem, så skift midlertidigt til
   knapper: Indstillinger → **System** → **Systemnavigation** → **Knapper**, stryg ind fra venstre kant, og skift
   tilbage bagefter.
2. Slå sync til.
3. Vælg mappe: **Intern lagerplads** → **ActivityWatchSync** → **Brug denne mappe** → **Tillad**.

Tjek: Sync Settings viser næste planlagte sync, og efter første sync ligger der en ny undermappe med telefonens
navn i ActivityWatchSync ved siden af `macbook.local`.

## Stationær (Windows)

### S1. ActivityWatch

1. Hent `activitywatch-v0.14.1-windows-x86_64-setup.exe` fra
   https://github.com/ActivityWatch/activitywatch/releases/latest. Tag den uden "tauri" i navnet.
2. Kør den. Siger Windows **Windows beskyttede din pc**, så klik **Flere oplysninger** → **Kør alligevel**.
3. Vælg **Install for me only**, og lad **Start ActivityWatch when Windows starts** være slået til.
4. Afslut installationen. ActivityWatch starter med et ikon i proceslinjen (måske under pilen ^).

Tjek: http://localhost:5600 → **Raw Data** viser `aw-watcher-window_<pc-navn>` og `aw-watcher-afk_<pc-navn>`.

### S2. Browserudvidelsen til Edge

1. Åbn i Edge: https://chromewebstore.google.com/detail/activitywatch-web-watcher/nglaklhklhcoonedhgnpgddginnjdadi
2. Klik **Tillad udvidelser fra andre butikker** → **Tillad**.
3. Klik **Hent** (Get) → **Tilføj udvidelse**.
4. Åbner udvidelsen en side, der beder om samtykke til dataindsamling, så accepter den.

Tjek: efter et minuts browsing viser **Raw Data** også `aw-watcher-web-edge…`.

### S3. Syncthing

1. Hent `syncthing-windows-setup-v2.1.1.exe` (eller nyeste) fra
   https://github.com/Bill-Stewart/SyncthingWindowsSetup/releases/latest.
2. Kør den som almindelig bruger, ikke som administrator. Så installeres den kun for dig. Lad valget om at
   starte Syncthing ved logon være slået til.
3. Spørger Windows Firewall, så tillad **Private netværk**.
4. Åbn http://127.0.0.1:8384 (eller **Syncthing Configuration Page** i Start-menuen). Svar på spørgsmålet om
   anonym statistik, som du vil.

### S4. Forbind PC'en og Mac'en

1. På PC'en: **Tilføj fjernenhed** (Add Remote Device) → indsæt Mac'ens id → navn `Mac` → **Gem**.
2. På Mac'en: åbn http://127.0.0.1:8384. Et banner siger, at en ny enhed vil forbinde: **Tilføj enhed**.
   Gå til fanen **Deling**, sæt flueben ved **ActivityWatchSync**, og **Gem**.
3. På PC'en: **Tilføj mappe** (Add Folder):
   - **Mappenavn:** `ActivityWatchSync`
   - **Mappe-ID:** `aw-sync`
   - **Mappesti:** `C:\Users\<dit brugernavn>\ActivityWatchSync`
   - Fanen **Deling:** flueben ved **Mac**. **Gem**.
   Dukker der i stedet et banner op om, at Mac vil dele ActivityWatchSync, så tryk **Tilføj** og brug samme
   navn og sti.

Tjek: mappen står som **Ajour** (Up to Date) på begge enheder, og `C:\Users\<bruger>\ActivityWatchSync\macbook.local`
findes.

### S5. aw-sync hvert 30. minut

Åbn **PowerShell** (ikke som administrator), og indsæt:

```powershell
$aw = (Get-ChildItem "$env:LOCALAPPDATA\Programs\ActivityWatch","$env:ProgramFiles\ActivityWatch" -Recurse -Filter aw-sync.exe -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
$dir = "$env:USERPROFILE\ActivityWatchSync"
"aw-sync: $aw"; "pc-navn: $env:COMPUTERNAME"
& $aw --sync-dir $dir sync
```

Den første linje skal vise en sti til `aw-sync.exe`. Er den tom, så find `aw-sync.exe` i ActivityWatch' mappe
i Stifinder, og sæt `$aw = "<stien>"` selv. Den sidste linje skal ende med `pushed … events`.

Lav den så til en opgave, der kører hvert 30. minut:

```powershell
$a = New-ScheduledTaskAction -Execute $aw -Argument "--sync-dir `"$dir`" sync"
$t = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "aw-sync" -Action $a -Trigger $t -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable)
```

Et sort vindue blinker kort hvert 30. minut. Generer det, så åbn **Opgavestyring** → **aw-sync** →
**Egenskaber** → **Kør, uanset om brugeren er logget på eller ej** (kræver din Windows-adgangskode).

Tjek:

```powershell
& $aw --sync-dir $dir status
```

viser PC'ens egen fil (`own-staging`) og Mac'en som peer.

## Bærbar (Linux med Hyprland)

ActivityWatch' egen vinduesmåler kan ikke se vinduer under Wayland. Bærbaren bruger derfor **awatcher**
(https://github.com/2e3s/awatcher), som er ActivityWatch-serveren og målere for aktivt vindue og inaktivitet
i ét program, og som kan Hyprland. aw-sync hentes fra ActivityWatch' Linux-zip. Afsnittet kan gives direkte
til Claude Code på bærbaren.

### L1. awatcher (server og målere)

```bash
mkdir -p ~/.local/opt/awatcher && cd ~/.local/opt/awatcher
curl -LO https://github.com/2e3s/awatcher/releases/latest/download/awatcher-bundle.zip
unzip -o awatcher-bundle.zip && ls -l
```

Programmet i zip'en (`awatcher` eller lignende) skal starte ved login. Med Hyprland er det nemmest i
`~/.config/hypr/autostart.conf` (eller `hyprland.conf`):

```
exec-once = ~/.local/opt/awatcher/awatcher
```

Start det med det samme én gang (eller log ud og ind). Kør ikke ActivityWatch' egen `aw-qt` ved siden af; de
deler port 5600.

Tjek: `curl -s localhost:5600/api/0/buckets/` viser `aw-watcher-window_<værtsnavn>` og `aw-watcher-afk_<værtsnavn>`
efter et par minutter, og `hostnamectl hostname` viser værtsnavnet.

### L2. Browserudvidelsen

Installer **ActivityWatch Web Watcher** i Chromium fra
https://chromewebstore.google.com/detail/activitywatch-web-watcher/nglaklhklhcoonedhgnpgddginnjdadi og accepter
samtykket. Bruger du Firefox: https://addons.mozilla.org/firefox/addon/aw-watcher-web/

### L3. aw-sync

```bash
cd /tmp && curl -LO https://github.com/ActivityWatch/activitywatch/releases/download/v0.14.1/activitywatch-v0.14.1-linux-x86_64.zip
unzip -o activitywatch-v0.14.1-linux-x86_64.zip -d ~/.local/opt/
find ~/.local/opt/activitywatch -name aw-sync -type f
```

Kun `aw-sync` bruges herfra. Den fundne sti kaldes `AWSYNC` nedenfor.

### L4. Syncthing

```bash
sudo pacman -S --needed syncthing
systemctl --user enable --now syncthing.service
mkdir -p ~/ActivityWatchSync && printf '(?d)*.tmp\n' > ~/ActivityWatchSync/.stignore
MAC=<MAC-ID>   # Mac'ens Syncthing-id fra tabellen øverst
syncthing cli config devices add --device-id $MAC --name Mac
syncthing cli config folders add --id aw-sync --label ActivityWatchSync --path ~/ActivityWatchSync
syncthing cli config folders aw-sync devices add --device-id $MAC
syncthing cli show system | grep myID
```

Det sidste id er bærbarens. Tilføj bærbaren på Mac'ens Syncthing-side: banneret om en ny enhed → **Tilføj enhed**
→ fanen **Deling** → flueben ved **ActivityWatchSync** → **Gem**.

Tjek: `~/ActivityWatchSync/macbook.local` dukker op på bærbaren.

### L5. aw-sync hvert 30. minut

`~/.config/systemd/user/aw-sync.service` (ret stien til AWSYNC fra L3):

```ini
[Unit]
Description=aw-sync: ActivityWatch-data til Syncthing-mappen

[Service]
Type=oneshot
ExecStart=/home/<bruger>/.local/opt/activitywatch/aw-sync --sync-dir %h/ActivityWatchSync sync
```

`~/.config/systemd/user/aw-sync.timer`:

```ini
[Unit]
Description=aw-sync hvert 30. minut

[Timer]
OnBootSec=5min
OnUnitActiveSec=30min

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now aw-sync.timer
systemctl --user start aw-sync.service
$AWSYNC --sync-dir ~/ActivityWatchSync status
```

Tjek: status viser bærbarens egen fil (`own-staging`) under `~/ActivityWatchSync/<værtsnavn>/`.

## Til sidst, på Mac'en

Når telefonen, PC'en og bærbaren har synkroniseret, dukker de op som ukendte enheder på
https://kompas.localhost/#/skaermtid/ inden for 30 minutter. Sæt så deres værtsnavne i `regler.json`
(kopieret fra `regler.example.json`): en computer har typisk to navne, pc-navnet
med små bogstaver og et langt enheds-id; telefonen kun et enheds-id.

```json
{"navn": "Stationær", "vaert": ["desktop-xxxx", "1a2b3c4d-…"], "slags": "computer"},
{"navn": "Telefon",   "vaert": ["5e6f7a8b-…"], "slags": "telefon"}
```

```bash
/usr/bin/python3 ~/kompas/skaermtid/skaermtid.py byg
```

skal melde 4 enheder med data (3 uden bærbaren).

## Hvis noget ikke virker

- **Mac'ens side siger "Fjernenheden har ikke accepteret deling af denne mappe":** mappen mangler på den anden
  enhed, eller dens Mappe-ID er ikke præcis `aw-sync`. Se T3 eller S4.
- **Mac'en henter intet:** kør på Mac'en
  `/Applications/ActivityWatch.app/Contents/Resources/aw-sync --sync-dir ~/ActivityWatchSync status`. Den siger pr.
  fil, hvorfor den ikke blev hentet.
- **Telefonen holder op med at sende:** batteriindstillingen i T2 er sat tilbage, eller Syncthing-Fork kører kun på
  wifi eller under opladning (dens indstillinger → **Kørselsbetingelser**).
- **PC'en bliver ved at være gammel:** er ActivityWatch startet (ikon i proceslinjen), og har opgaven aw-sync kørt
  (Opgavestyring → **Seneste kørselstidspunkt**)?
