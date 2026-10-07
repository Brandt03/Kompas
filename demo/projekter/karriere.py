"""Demodata for Karriere (jobagenten): /karriere/kompas.json og /karriere/api/*.

Bygger en opdigtet jobagent-mappe for den fiktive studerende Alex (oversigt.csv, vurderinger, opslag,
beslutninger, dagens rapport, profil og cv) i en midlertidig mappe og lader den rigtige
karriere/kompas_server.py læse den. Så har demo-svarene præcis samme form som serverens. Serveren
startes ikke, og intet skrives uden for `ud`.

Alle virksomheder, opslag og personer er opdigtede. Links peger på example.com.
"""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import re
import tempfile
from datetime import date, timedelta
from pathlib import Path

KARRIERE = Path(__file__).resolve().parents[2] / "karriere"
MAANEDER = ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september",
            "oktober", "november", "december"]

# Opslagene. "dato" er dagen, agenten vurderede opslaget (dage fra i dag), "frist" er dage fra i dag eller
# en tekst, og "besl" er brugerens beslutninger på siden: (dage fra i dag, klokkeslæt, fra, til, note).
JOBS = [
    dict(id="d1001", firma="Nordlys Analytics ApS", stilling="Studentermedhjælper til data og rapportering",
         type="Studiejob", score=86, frist=9, status="vurderet", omraade="København K", timer="15 t/uge",
         loebende=True, dato=0, indrykket=-1, kategorier=["IT", "Økonomi og regnskab"],
         om="Nordlys Analytics hjælper danske detailkæder med at forstå deres salgsdata. Vi er 40 medarbejdere "
            "med kontor tæt på Nørreport.",
         opgaver=["Vedligeholde ugentlige salgsrapporter i Excel og Power BI",
                  "Rydde op i data fra kundernes kassesystemer, før de indgår i analyser",
                  "Hjælpe konsulenterne med tal og grafer til kundemøder"],
         krav=["Læser en relevant bachelor, gerne på 1. eller 2. år",
               "Er tryg ved Excel og nysgerrig på Power BI", "Kan lide at finde fejl i tal, før andre gør"],
         opstart="1. {m1} eller efter aftale",
         hvorfor=["Opgaverne er fast Excel-rapportering og et Power BI-dashboard, tæt på dit ugentlige "
                  "returneringsark hos Rytterstalden Cykler.",
                  "Opslaget nævner selv studerende på 1. eller 2. år, så niveauet er realistisk.",
                  "15 timer om ugen og ca. 15 minutter fra Nørrebro."],
         huller=["Power BI er en fordel, og du har kun prøvet det på studiet."],
         kort="Stærkt match på rapportering og data. De holder samtaler løbende, så søg i denne uge."),
    dict(id="d1002", firma="Havnefront Pension", stilling="Studentermedhjælper til Business Intelligence",
         type="Studiejob", score=81, frist=2, status="vurderet", omraade="Hellerup", timer="12–16 t/uge",
         loebende=False, dato=0, indrykket=-2, kategorier=["Finans og forsikring", "IT"],
         om="Havnefront Pension forvalter pensioner for 90.000 medlemmer. BI-teamet leverer tal til ledelse, "
            "investering og medlemsservice.",
         opgaver=["Opdatere månedlige nøgletalsrapporter til ledelsen",
                  "Skrive enkle SQL-forespørgsler mod vores datavarehus med hjælp fra teamet",
                  "Teste nye rapporter, før de går i drift"],
         krav=["Er i gang med en økonomisk eller IT-faglig bacheloruddannelse",
               "Har styr på Excel; SQL lærer vi dig", "Arbejder struktureret og spørger, når noget ikke giver mening"],
         opstart="snarest muligt",
         hvorfor=["Teamet bygger rapporter i Excel og SQL og lærer studerende SQL op fra bunden.",
                  "Rapportering og BI står under \"Helst\" i din profil."],
         huller=["SQL er ønsket, og du har ikke arbejdet med det endnu.",
                 "Hellerup er ca. 35 minutter fra Nørrebro, inden for grænsen, men tæt på."],
         kort="God retning og realistisk niveau. Fristen er om to dage."),
    dict(id="d1003", firma="Kobberstien Forsikring A/S", stilling="Student assistant, Finance Operations",
         type="Studiejob", score=77, frist="Snarest muligt", status="vurderet", omraade="Valby", timer="15–20 t/uge",
         loebende=True, dato=-1, indrykket=-2, kategorier=["Økonomi og regnskab", "Finans og forsikring"],
         om="Kobberstien Forsikring er et nordisk forsikringsselskab. Finance Operations i Valby står for "
            "bogføring, afstemninger og månedsafslutning, og arbejdssproget er engelsk.",
         opgaver=["Afstemme konti og følge op på differencer", "Forberede bilag til månedsafslutningen",
                  "Hjælpe med at automatisere faste opgaver i Excel"],
         krav=["Læser en økonomisk bachelor", "Taler og skriver engelsk flydende", "Har sans for detaljer og deadlines"],
         opstart="snarest muligt",
         hvorfor=["Afstemninger og månedsafslutning i Excel ligner det, du laver som kasserer i idrætsforeningen.",
                  "Ønsket om at automatisere faste opgaver passer med retningen i din profil."],
         huller=["Op til 20 timer om ugen i eksamensperioder kan blive tungt. Spørg, om timerne kan flekse."],
         kort="Solidt finance-match. Stillingen besættes, så snart de finder den rette."),
    dict(id="d1004", firma="Strandvejens Energi A/S", stilling="Studentermedhjælper i controlling",
         type="Studiejob", score=64, frist=12, status="vurderet", omraade="Kgs. Lyngby", timer="15 t/uge",
         loebende=False, dato=0, indrykket=-3, kategorier=["Økonomi og regnskab"],
         om="Strandvejens Energi leverer fjernvarme og el til erhvervskunder i Nordsjælland.",
         opgaver=["Følge op på budget og forbrug i afdelingerne", "Lave månedlige afvigelsesanalyser",
                  "Vedligeholde vores controllingmodeller i Excel"],
         krav=["Læser en økonomisk uddannelse, helst fra 3. semester", "Har gode Excel-kompetencer",
               "Kender et ERP-system, gerne Dynamics"],
         opstart="1. {m2}",
         kort="God retning, men de foretrækker studerende fra 3. semester med kendskab til Dynamics, og Lyngby "
              "ligger tæt på din grænse for transporttid."),
    dict(id="d1005", firma="Fyrlys IT ApS", stilling="Praktikant i IT-support og drift",
         type="Praktik", score=49, frist="Løbende", status="vurderet", omraade="Ballerup", timer="30 t/uge",
         loebende=False, dato=-3, indrykket=-6, kategorier=["IT"],
         om="Fyrlys IT driver servere og arbejdspladser for 60 små virksomheder.",
         opgaver=["Besvare supporthenvendelser fra kunderne", "Sætte bærbare og telefoner op til nye medarbejdere",
                  "Dokumentere løsninger i vores vidensbase"],
         krav=["Er i gang med en IT-uddannelse", "Kan arbejde 30 timer om ugen i et semester", "Har kørekort"],
         opstart="{m3}",
         kort="Praktik på 30 timer om ugen kan ikke passes ved siden af studiet, og Ballerup ligger over din "
              "grænse for transporttid."),
    dict(id="d1006", firma="Kanalbyen Bank", stilling="Studentermedhjælper i kreditadministration",
         type="Studiejob", score=68, frist=-3, status="vurderet", omraade="København V", timer="15 t/uge",
         loebende=False, dato=-10, indrykket=-13, kategorier=["Finans og forsikring"],
         om="Kanalbyen Bank er en lokal bank med 25.000 kunder i hovedstadsområdet.",
         opgaver=["Klargøre lånesager til kreditudvalget", "Registrere sikkerheder og pantebreve",
                  "Svare rådgiverne på spørgsmål om sagernes status"],
         krav=["Læser økonomi, jura eller lignende", "Er omhyggelig og systematisk", "Har lyst til at lære bankens systemer"],
         opstart="efter aftale",
         kort="Sagsbehandling med krav om præcision passer godt, men opgaverne er mere administration end data."),
    dict(id="d1007", firma="Mølleå Data ApS", stilling="Studentermedhjælper til dataanalyse i kundeservice",
         type="Studiejob", score=79, frist=6, status="vil søge", omraade="København Ø", timer="10–15 t/uge",
         loebende=False, dato=-5, indrykket=-7, kategorier=["IT", "Handel og service"],
         besl=[(-4, "19:42:10", "vurderet", "vil søge", None)],
         om="Mølleå Data laver software til kundeservice i mellemstore webshops.",
         opgaver=["Analysere vores egne supporthenvendelser og finde mønstre",
                  "Bygge en ugentlig oversigt til produktteamet", "Foreslå forbedringer af hjælpeteksterne i produktet"],
         krav=["Læser en relevant bachelor, gerne med IT", "Har erfaring fra kundeservice",
               "Python er en fordel, men ikke et krav"],
         opstart="{m1}",
         hvorfor=["Du skal finde mønstre i henvendelser, præcis det, du gjorde med returneringerne hos Rytterstalden Cykler.",
                  "To års kundeservice i en webshop er netop den baggrund, de beder om."],
         huller=["Python er en fordel, og det har du ikke brugt endnu."],
         kort="Din kundeserviceerfaring og dit Excel-ark gør dig til et oplagt bud."),
    dict(id="d1008", firma="Lysbro Finans", stilling="Studentermedhjælper til økonomiafdelingen",
         type="Studiejob", score=66, frist=15, status="vil søge", omraade="Frederiksberg", timer="15 t/uge",
         loebende=False, dato=-2, indrykket=-4, kategorier=["Økonomi og regnskab"],
         besl=[(-1, "21:05:33", "vurderet", "vil søge", None)],
         om="Lysbro Finans formidler leasing og finansiering til små og mellemstore virksomheder.",
         opgaver=["Bogføre købs- og salgsfakturaer", "Afstemme bank og kreditorer", "Hjælpe med kvartalsrapporteringen"],
         krav=["Læser en økonomisk uddannelse", "Har gerne erfaring med et økonomisystem", "Er stabil og grundig"],
         opstart="1. {m1}",
         kort="Bogføring og afstemninger i et lille team. Lidt under tærsklen, fordi de ønsker erfaring med et "
              "økonomisystem."),
    dict(id="d1009", firma="Saltholm Rådgivning A/S", stilling="Studentermedhjælper til økonomistyring",
         type="Studiejob", score=75, frist=-2, status="søgt", omraade="København K", timer="15 t/uge",
         loebende=False, dato=-12, indrykket=-15, kategorier=["Økonomi og regnskab", "Ledelse og personale"],
         besl=[(-11, "08:12:40", "vurderet", "vil søge", None), (-8, "16:30:02", "vil søge", "søgt", None)],
         om="Saltholm Rådgivning er et rådgivningshus med 120 konsulenter inden for økonomistyring i den "
            "offentlige sektor.",
         opgaver=["Opdatere budgetopfølgninger for vores kunder", "Klargøre data til analyser",
                  "Hjælpe med præsentationer til styregrupper"],
         krav=["Læser en økonomisk eller IT-faglig bachelor", "Er god til Excel", "Kan lide at have mange opgaver i gang"],
         opstart="{m1}",
         hvorfor=["Budgetopfølgning i Excel bygger direkte på dit arbejde som kasserer.",
                  "De søger netop studerende på 1. eller 2. år."],
         huller=["Ingen erfaring med offentlig økonomi. Nævn, at du er nysgerrig på det."],
         kort="Godt match på Excel og budget."),
    dict(id="d1010", firma="Bølgebryder Forsikring", stilling="Studentermedhjælper i prisanalyse",
         type="Studiejob", score=83, frist=-6, status="samtale", omraade="København S", timer="12–15 t/uge",
         loebende=False, dato=-18, indrykket=-21, kategorier=["Finans og forsikring"],
         besl=[(-17, "07:58:21", "vurderet", "vil søge", None), (-15, "20:14:09", "vil søge", "søgt", None),
               (-3, "12:02:47", "søgt", "samtale", None)],
         om="Bølgebryder Forsikring forsikrer private boliger og biler. Prisafdelingen sætter præmierne ud fra "
            "skadesdata.",
         opgaver=["Opdatere analyser af skadesudvikling", "Teste nye prismodeller i Excel",
                  "Formidle resultater til salg og kundeservice"],
         krav=["Læser en økonomisk eller kvantitativ bachelor", "Har god talforståelse",
               "Kan forklare tal til ikke-specialister"],
         opstart="efter aftale",
         hvorfor=["Analyse i Excel og formidling af tal er dine to stærkeste beviser.",
                  "Analyse står under \"Helst\" i din profil."],
         huller=["Prismodeller er nyt for dig."],
         kort="Stærkt match på data og formidling."),
    dict(id="d1011", firma="Tågelys Kapital A/S", stilling="Student assistant, Portfolio Reporting",
         type="Studiejob", score=71, frist=-9, status="afslag", omraade="København K", timer="15 t/uge",
         loebende=False, dato=-20, indrykket=-23, kategorier=["Finans og forsikring"],
         besl=[(-19, "18:40:55", "vurderet", "vil søge", None), (-16, "09:21:13", "vil søge", "søgt", None),
               (-2, "10:47:30", "søgt", "afslag", None)],
         om="Tågelys Kapital forvalter aktie- og obligationsporteføljer for fonde og pensionskasser.",
         opgaver=["Opdatere månedlige porteføljerapporter til kunderne", "Kontrollere data fra depotbanken",
                  "Hjælpe med rapportskabeloner i Excel"],
         krav=["Studerer finansiering eller økonomi", "Er stærk i Excel", "Er præcis og kan holde deadlines"],
         opstart="efter aftale",
         hvorfor=["Fast rapportering i Excel med kontrol af data.", "Rapportering står under \"Helst\" i din profil."],
         huller=["Kapitalforvaltning er nyt for dig."],
         kort="Over tærsklen, men konkurrencen er hård."),
    dict(id="d1012", firma="Spirekassen ApS", stilling="Studentermedhjælper til salg og kundeservice",
         type="Studiejob", score=28, frist=10, status="fravalgt", omraade="Glostrup", timer="16 t/uge",
         loebende=False, dato=-4, indrykket=-5, kategorier=["Handel og service"],
         besl=[(-3, "22:18:04", "vurderet", "fravalgt", "Mest telefonsalg. Det er ikke den retning, jeg vil.")],
         om="Spirekassen sælger abonnementer på grøntsagskasser til private.",
         opgaver=["Ringe til tidligere kunder med nye tilbud", "Besvare henvendelser i chat og telefon",
                  "Registrere salg i vores CRM"],
         krav=["Har salgserfaring", "Er udadvendt", "Kan arbejde om aftenen"],
         opstart="snarest muligt",
         kort="Reelt telefonsalg, som din profil fravælger, så scoren er højst 30."),
]


def _maaned(idag: date, n: int) -> str:
    return MAANEDER[(idag.month - 1 + n) % 12]


def _opstart(tekst: str, idag: date) -> str:
    """Opstart som "1. {m1}" bliver til den første i næste måned osv., så teksten følger idag."""
    return tekst.format(m1=_maaned(idag, 1), m2=_maaned(idag, 2), m3=_maaned(idag, 3))


def _dag(idag: date, n: int) -> date:
    return idag + timedelta(days=n)


def _frist(j: dict, idag: date) -> str:
    return _dag(idag, j["frist"]).isoformat() if isinstance(j["frist"], int) else j["frist"]


def _lang_dato(s: str) -> str:
    if not re.match(r"\d{4}-\d{2}-\d{2}$", s):
        return s.lower()
    d = date.fromisoformat(s)
    return f"{d.day}. {MAANEDER[d.month - 1]} {d.year}"


def _link(j: dict) -> str:
    return f"https://example.com/job/{j['id']}"


def _opslag(j: dict, idag: date) -> str:
    linjer = [j["stilling"], f"{j['firma']} · {j['omraade']}", "", j["om"], "", "Dine opgaver"]
    linjer += [f"• {x}" for x in j["opgaver"]] + ["", "Vi forventer, at du"] + [f"• {x}" for x in j["krav"]]
    timer = j["timer"].replace("t/uge", "timer om ugen")
    linjer += ["", "Vi tilbyder",
               f"Et studiejob på {timer} med fleksible arbejdstider, der tager hensyn til din eksamensplan, og en "
               f"fast kollega, der lærer dig op. Opstart {_opstart(j['opstart'], idag)}.", "",
               f"Ansøgningsfrist: {_lang_dato(_frist(j, idag))}."]
    if j["loebende"]:
        linjer.append("Vi holder samtaler løbende, så send gerne din ansøgning hurtigt.")
    linjer.append("Søg via linket. Vi ser frem til at høre fra dig.")
    return "\n".join(linjer)


def _rapport(idag: date) -> str:
    nye = [j for j in JOBS if j["dato"] == 0]
    over = sorted((j for j in nye if j.get("hvorfor")), key=lambda j: -j["score"])
    under = [j for j in nye if not j.get("hvorfor")]
    dm = lambda j: f"{_dag(idag, j['frist']).day}/{_dag(idag, j['frist']).month}"
    frist_celle = lambda j: _frist(j, idag) + (" · **løbende samtaler**" if j["loebende"] else "")
    bedste = " og ".join("%s %d" % (j["firma"].replace(" ApS", ""), j["score"]) for j in over)
    ud = [f"# Jobagent – {idag.isoformat()}",
          f"Tre nye opslag er vurderet, og to ligger over tærsklen ({bedste}). "
          f"**Havnefront Pension har frist {dm(JOBS[1])}**, og Nordlys Analytics holder samtaler løbende.", "",
          "## Bedste match", "| Score | Stilling | Virksomhed | Frist | Link |", "|---|---|---|---|---|"]
    ud += [f"| {j['score']} | {j['stilling']} | {j['firma']} | {frist_celle(j)} | [opslag]({_link(j)}) |" for j in over]
    for j in over:
        ud += ["", f"### {j['firma']} – {j['stilling']} ({j['score']})"]
        ud += [f"- **Hvorfor match:** {x}" for x in j["hvorfor"]] + [f"- **Huller/risici:** {x}" for x in j["huller"]]
    ud += ["", "## Vurderet, men under tærsklen", "| Score | Stilling | Virksomhed | Kort begrundelse |", "|---|---|---|---|"]
    ud += [f"| {j['score']} | {j['stilling']} | {j['firma']} | {j['kort']} |" for j in under]
    ud += ["", "## Bemærkninger",
           "- Du har fravalgt Spirekassen, fordi det mest var telefonsalg. Kommer der flere opslag, hvor salg er "
           "hovedopgaven, så overvej at tilføje \"salgsassistent\" til `negative_ord` i `config.json`.",
           "- Strandvejens Energi foretrækker studerende fra 3. semester og ligger derfor under tærsklen, men "
           "retningen passer godt.",
           "- Ingen opslag indeholdt instruktioner rettet mod en AI.", ""]
    return "\n".join(ud)


def _skriv_mappe(mappe: Path, idag: date) -> None:
    """Den opdigtede jobagent-mappe, som kompas_server.py læser."""
    for d in ("rapporter", "data/behandlet", "data/vurderinger"):
        (mappe / d).mkdir(parents=True, exist_ok=True)
    for navn in ("CV.pdf", "Karakterudskrift_gymnasium.pdf"):  # kun navnene vises i Kompas
        (mappe.parent / navn).write_bytes(b"")
    (mappe / "config.json").write_text((KARRIERE / "config.json").read_text(encoding="utf-8"), encoding="utf-8")
    (mappe / "profil.md").write_text((KARRIERE / "profil.example.md").read_text(encoding="utf-8"), encoding="utf-8")
    (mappe / "cv.txt").write_text((KARRIERE / "cv.example.txt").read_text(encoding="utf-8"), encoding="utf-8")
    (mappe / "rapporter" / f"{idag.isoformat()}.md").write_text(_rapport(idag), encoding="utf-8")

    rækker = [["dato", "id", "virksomhed", "stilling", "type", "score", "frist", "status", "link"]]
    beslutninger = []
    for j in sorted(JOBS, key=lambda j: j["dato"]):
        dato = _dag(idag, j["dato"]).isoformat()
        rækker.append([dato, j["id"], j["firma"], j["stilling"], j["type"], str(j["score"]), _frist(j, idag),
                       j["status"], _link(j)])
        tekst = _opslag(j, idag)
        (mappe / "data" / "behandlet" / f"{j['id']}.json").write_text(json.dumps({
            "id": j["id"], "titel": j["stilling"], "firma": j["firma"], "link": _link(j), "omraade": j["omraade"],
            "kategorier": j["kategorier"], "teaser": tekst[:300], "indrykket": _dag(idag, j["indrykket"]).isoformat(),
            "type": j["type"], "forfilter_score": 4 + j["score"] // 10, "forfilter_hits": [],
            "fuld_tekst": tekst, "kilde_url": _link(j), "hentet": f"{dato}T07:31:0{int(j['id'][-1]) % 10}",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        vurdering = {"id": j["id"], "score": j["score"], "frist": _frist(j, idag), "loebende": j["loebende"],
                     "sted": j["omraade"], "timer": j["timer"], "kort_begrundelse": j["kort"]}
        if j.get("hvorfor"):
            vurdering.update(hvorfor=j["hvorfor"], huller=j["huller"])
        (mappe / "data" / "vurderinger" / f"{j['id']}.json").write_text(
            json.dumps(vurdering, ensure_ascii=False), encoding="utf-8")
        for n, kl, fra, til, note in j.get("besl", []):
            b = {"tid": f"{_dag(idag, n).isoformat()}T{kl}", "id": j["id"], "fra": fra, "til": til}
            if note:
                b["note"] = note
            beslutninger.append(b)

    ud = io.StringIO()
    csv.writer(ud, delimiter=";", lineterminator="\n").writerows(rækker)
    (mappe / "oversigt.csv").write_text(ud.getvalue(), encoding="utf-8")
    beslutninger.sort(key=lambda b: b["tid"])
    (mappe / "data" / "beslutninger.jsonl").write_text(
        "".join(json.dumps(b, ensure_ascii=False) + "\n" for b in beslutninger), encoding="utf-8")


def _server(mappe: Path):
    """Indlæser karriere/kompas_server.py og peger den på den opdigtede mappe (uden at starte serveren)."""
    spec = importlib.util.spec_from_file_location("karriere_kompas_server_demo", KARRIERE / "kompas_server.py")
    ks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ks)
    ks.MAPPE, ks.SIDER = mappe, mappe / "kompas"
    ks.OVERSIGT, ks.BESLUTNINGER = mappe / "oversigt.csv", mappe / "data" / "beslutninger.jsonl"
    return ks


def lav(ud: Path, idag: date) -> None:
    """Skriver Karrieres demodata under ud/karriere."""
    api = ud / "karriere" / "api"
    (api / "opslag").mkdir(parents=True, exist_ok=True)
    tid = f"{idag.isoformat()}T07:34:12"  # jobagenten kører kl. 7.30

    with tempfile.TemporaryDirectory() as tmp:
        mappe = Path(tmp) / "Jobs" / "jobagent"
        _skriv_mappe(mappe, idag)
        ks = _server(mappe)
        manifest = {**ks.manifest(), "opdateret": tid}
        data = {**ks.data(), "genereret": tid}
        opslag = {j["id"]: json.loads((mappe / "data" / "behandlet" / f"{j['id']}.json").read_text(encoding="utf-8"))["fuld_tekst"]
                  for j in JOBS}

    skriv = lambda sti, tekst: sti.write_text(tekst, encoding="utf-8")
    skriv(ud / "karriere" / "kompas.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    skriv(api / "data.json", json.dumps(data, ensure_ascii=False, indent=1))
    # GET /karriere/api/opslag?id=<id> svarer med tekst, ikke JSON. Demo-serveren slår det op som
    # opslag/<id>; opslag.json (Nordlys) er reserven, hvis en server ignorerer query-strengen.
    for jid, tekst in opslag.items():
        skriv(api / "opslag" / jid, tekst)
    skriv(api / "opslag.json", opslag[JOBS[0]["id"]])

