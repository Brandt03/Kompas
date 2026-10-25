# Kompas på bærbaren

Bærbaren (en Linux-maskine; opsætningen er skrevet til Arch) åbner Kompas på **http://kompas.localhost:8780**. Svarer Mac'en, er det det levende
Kompas, og alt kan gemmes. Svarer den ikke, viser bærbaren den seneste kopi, og intet kan gemmes. Nederst i menuen
står så, hvornår kopien er fra. Skiftet sker af sig selv: til kopien med det samme, når Mac'en forsvinder, og
tilbage inden for cirka 15 sekunder, når den er der igen.

```
Mac   opdater.sh hver halve time → bin/kopi.py → ~/KompasKopi ──Syncthing (kompas-kopi)──┐
Mac   Caddy 127.0.0.1:8771 ← tailscale serve :8443 ←───────────────────────────────┐       │
                                                                                   │       ↓
Bærbar  Chromium → Caddy kompas.localhost:8780 ── Mac'en svarer? ── ja ──────────────┘   ~/KompasKopi/site
                                                                └── nej ─────────────────────┘
```

Filerne her er skabeloner. `bin/kopi.py` sætter Mac'ens Tailscale-navn ind og lægger dem i `~/KompasKopi/baerbar`,
så bærbaren altid har den nyeste udgave. Caddy på bærbaren læser sin fil igen, når den ændrer sig.

| Fil | Hvad |
|---|---|
| `Caddyfile` | Sender til Mac'en, når den svarer, ellers kopien. Kun navnet kompas.localhost og kun denne maskine. |
| `kompas-kopi.service` | systemd-tjeneste for brugeren, starter Caddy ved login |
| `opsaet.sh` | Installerer Caddy og starter tjenesten |

**Med i kopien:** Kompas' forside, menu og Forbindelser, Studie med Genkald, fagsider og pensum, Form og fokus,
ugereviewet, Skærmtid, Forbrug, Scenarier og SU-vagt og Sprog. **Ikke med:** Sures egne sider, fx
Oversigt og Transaktioner, og kald med parametre som facit og eksamenssæt. De viser fejl eller "Kun på Mac'en".
Kopien ligger på bærbarens disk, også økonomital, studienoter og helbredstal.

## Opsætning på bærbaren

Afsnittet kan gives direkte til Claude Code på bærbaren. Mac'en deler allerede mappen.

### B1. Tag imod mappen i Syncthing

1. Åbn Syncthing på bærbaren (http://127.0.0.1:8384). Et banner siger, at Mac'en (`<mac>.local`) vil dele
   **KompasKopi**. Tryk **Tilføj**.
2. **Mappesti:** `~/KompasKopi`. Mappe-ID'et skal være `kompas-kopi`; det står der allerede.
3. Fanen **Avanceret**, **Mappetype:** **Modtag kun**. Mac'en er den eneste, der skriver. **Gem**.

Tjek: mappen står som **Ajour** efter et par minutter (den fylder omkring 80 MB), og
`ls ~/KompasKopi` viser `baerbar` og `site`.

### B2. Start Kompas

```bash
bash ~/KompasKopi/baerbar/opsaet.sh
```

Den beder om din adgangskode, hvis Caddy skal installeres. Den sidste linje skal være
`Kompas kører: http://kompas.localhost:8780`.

### B3. Åbn den

Åbn http://kompas.localhost:8780 i Chromium. Første gang du åbner Økonomi, logger du ind på Sure, fordi login gælder
pr. adresse. Den gamle adresse `https://<mac>.<tailnet>.ts.net:8443` virker stadig, men har ingen kopi.

Tjek: med Mac'en vågen står "Sure kører" nederst i menuen. Uden Mac'en står "Kopi fra …".

## Fejlfinding

```bash
systemctl --user status kompas-kopi
```

```bash
journalctl --user -u kompas-kopi -n 50
```

Står kopien som gammel, så se siden Forbindelser på Mac'en (punktet Kopi til bærbaren) og Syncthing på begge
maskiner.
