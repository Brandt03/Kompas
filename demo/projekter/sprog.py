"""Demodata for Sprog (/sprog/): Dagens kort, ugens tekst og reglerne for en opdigtet studerende.

Skriver det, sprog/server.js ville svare, med datoerne regnet ud fra idag:

  ud/sprog/kompas.json          menuen (som manifest() i server.js)
  ud/sprog/api/pakke.json       GET /sprog/api/pakke: sprogene, dagens kø, teksterne, tallene, reglerne
  ud/sprog/api/tekster.json     GET /sprog/api/tekster
  ud/sprog/api/regler.json      GET /sprog/api/regler

Spansk er det aktive sprog (A2 efter niveautesten), tysk er på pause, og dansk og engelsk er studiesprog, som i
standardopsætningen i sprog/kerne.js. Kortene, teksterne og reglerne er opdigtede eksempler i samme form som dem,
rutinen skriver; tallene hænger sammen med køen (forfaldne og nye i dag står også i statistikken). Demoens eksamener
ligger mindst syv uger frem (se studie.py), så der er ingen eksamensperiode. Kun standardbiblioteket.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

SPROG = {
    "es": {"navn": "Spansk", "stemme": "es-ES", "rolle": "aktiv", "nye_pr_dag": 3, "fokus": "rejse og hverdag"},
    "de": {"navn": "Tysk", "stemme": "de-DE", "rolle": "pause", "nye_pr_dag": 0, "fokus": "rejse og hverdag"},
    "da": {"navn": "Dansk", "stemme": "da-DK", "rolle": "studie", "nye_pr_dag": 1, "fokus": "skriftlig præcision i studiet"},
    "en": {"navn": "Engelsk", "stemme": "en-GB", "rolle": "studie", "nye_pr_dag": 1, "fokus": "akademisk og fagligt engelsk"},
}
OPGAVE = {"frase": "Sig det på {}", "ret": "Ret sætningen", "ord": "Brug ordet i en sætning", "udfyld": "Sæt det manglende ind"}

# Dagens kø i serverens rækkefølge: det aktive sprog først (forfaldne, så nye med reglens kort først), så
# studiesprogene og til sidst sproget på pause, hvor gentagelsen fortsætter uden nye kort.
# (id, type, situation, niveau, forside, bagside, note, regel, ny, dage siden sidst, stabilitet)
KOE = [
    ("es-0007", "frase", "restaurant", "A2", "Kan vi få regningen, tak?", "¿Nos trae la cuenta, por favor?",
     "la cuenta = regningen", None, False, 6, 6.2),
    ("es-0012", "frase", "transport", "A2", "Hvornår kører det næste tog til Sevilla?",
     "¿A qué hora sale el próximo tren a Sevilla?", "salir = køre/afgå (om tog og fly)", None, False, 4, 4.1),
    ("es-0019", "frase", "indkøb", "A2", "Hvor meget koster de her?", "¿Cuánto cuestan estos?",
     "cuesta om én ting, cuestan om flere", None, False, 9, 8.7),
    ("es-0023", "frase", "vej og retning", "A1", "Er det langt herfra?", "¿Está lejos de aquí?",
     "hvor noget er: estar", "es-ser-estar", False, 3, 2.9),
    ("es-0031", "frase", "læge og apotek", "A2", "Jeg har ondt i halsen.", "Me duele la garganta.",
     "doler bøjes som gustar: det er halsen, der gør ondt", "es-gustar", False, 2, 1.6),
    ("es-0058", "udfyld", "overnatning", "A1", "El hotel ___ cerca de la estación. (estar)",
     "El hotel está cerca de la estación.", "hvor noget ligger: estar", "es-ser-estar", True, None, None),
    ("es-0059", "udfyld", "small talk", "A1", "Mi hermana ___ enfermera. (ser)", "Mi hermana es enfermera.",
     "hvad nogen er (et erhverv): ser", "es-ser-estar", True, None, None),
    ("es-0060", "frase", "restaurant", "A2", "Jeg tager det samme som hende.", "Para mí, lo mismo que ella.",
     "para mí = til mig, når man bestiller", None, True, None, None),
    ("da-0011", "ret", None, None, "Det afhænger af, hvordan virksomheden fungere i praksis.",
     "Det afhænger af, hvordan virksomheden fungerer i praksis.",
     "Nutid får -r (fungerer); navnemåde efter 'at' gør ikke (at fungere).", "da-nutids-r", False, 5, 3.4),
    ("da-0015", "ord", None, None, "at nuancere: at gøre et billede mere præcist ved at vise forskelle og forbehold",
     "Undersøgelsen nuancerer billedet af, hvordan små virksomheder bruger data.",
     "Bruges om at tilføje forbehold; det er ikke det samme som at modsige.", None, True, None, None),
    ("en-0009", "frase", None, None, "Resultaterne tyder på, at …", "The findings suggest that …",
     "suggest er forsigtigere end show", None, False, 7, 5.5),
    ("de-0004", "frase", "vej og retning", "A1", "Hvor er toilettet?", "Wo ist die Toilette?",
     None, None, False, 11, 9.8),
]

# Kort, der øver en regel, men ikke er i dagens kø (de kommer med i pakken, så "Øv reglen" virker uden net)
REGELKORT = [
    ("es-0041", "udfyld", "transport", "A1", "¿Dónde ___ la parada del autobús? (estar)",
     "¿Dónde está la parada del autobús?", "hvor noget er: estar", "es-ser-estar"),
    ("es-0042", "udfyld", "small talk", "A1", "Nosotros ___ de Dinamarca. (ser)", "Nosotros somos de Dinamarca.",
     "hvor man kommer fra: ser", "es-ser-estar"),
    ("es-0047", "udfyld", "restaurant", "A2", "No me ___ el café sin azúcar. (gustar)",
     "No me gusta el café sin azúcar.", "gusta, fordi det er kaffen, der behager", "es-gustar"),
    ("es-0048", "udfyld", "small talk", "A2", "¿Te ___ los museos? (gustar)", "¿Te gustan los museos?",
     "gustan, fordi museerne er flere", "es-gustar"),
    ("da-0012", "ret", None, None, "Systemet giver et overblik, som ledelsen kan bruge, når den planlægge.",
     "Systemet giver et overblik, som ledelsen kan bruge, når den planlægger.",
     "Nutid får -r: den planlægger.", "da-nutids-r"),
]

REGLER = [
    {"id": "es-ser-estar", "sprog": "es", "niveau": "A1", "titel": "ser og estar",
     "forklaring": "Begge betyder *at være*. **ser** bruges om, hvad og hvem noget er: navn, erhverv, nationalitet, "
                   "hvor man kommer fra, og hvad noget er lavet af. **estar** bruges om, hvor noget er, og hvordan "
                   "noget har det lige nu.\n\nSpørg dig selv: er det, hvad det *er*, eller hvor og hvordan det *er lige nu*?",
     "eksempler": [{"tekst": "Soy estudiante.", "oversaettelse": "Jeg er studerende."},
                   {"tekst": "La estación está cerca.", "oversaettelse": "Stationen ligger tæt på."},
                   {"tekst": "Estoy cansado hoy.", "oversaettelse": "Jeg er træt i dag."}],
     "fejl": [{"fejl": "¿Dónde es el baño?", "rettet": "¿Dónde está el baño?", "hvorfor": "hvor noget er: estar"},
              {"fejl": "Estoy de Dinamarca.", "rettet": "Soy de Dinamarca.", "hvorfor": "hvor man kommer fra: ser"}],
     "kilde": "niveautesten", "uger_siden": 2},
    {"id": "es-gustar", "sprog": "es", "niveau": "A2", "titel": "gustar og doler",
     "forklaring": "*Me gusta* betyder ordret *det behager mig*. Det, man kan lide, er grundleddet, så verbet bøjes "
                   "efter det: **gusta** om én ting, **gustan** om flere. Personen står foran som *me, te, le, nos, "
                   "os, les*. **doler** (gøre ondt) virker på samme måde: *me duele la cabeza*.",
     "eksempler": [{"tekst": "Me gusta el pan.", "oversaettelse": "Jeg kan lide brødet."},
                   {"tekst": "Nos gustan las playas.", "oversaettelse": "Vi kan lide strandene."},
                   {"tekst": "Me duelen los pies.", "oversaettelse": "Mine fødder gør ondt."}],
     "fejl": [{"fejl": "Yo gusto el café.", "rettet": "Me gusta el café.", "hvorfor": "det er kaffen, der behager"},
              {"fejl": "Me gusta los museos.", "rettet": "Me gustan los museos.", "hvorfor": "flere museer: gustan"}],
     "kilde": "fejl i ugens tekst", "uger_siden": 1},
    {"id": "da-nutids-r", "sprog": "da", "niveau": None, "titel": "Nutids-r",
     "forklaring": "Et udsagnsord i nutid ender på **-r**: *han arbejder, systemet fungerer*. Navnemåden har intet r: "
                   "*at arbejde, at fungere*. Er du i tvivl, så sæt et udsagnsord ind, hvor man hører forskellen: "
                   "*virksomheden **lever*** (nutid) eller *at **leve*** (navnemåde).",
     "eksempler": [{"tekst": "Virksomheden fungerer godt.", "oversaettelse": "nutid: -r"},
                   {"tekst": "Den skal fungere bedre.", "oversaettelse": "efter skal: navnemåde"}],
     "fejl": [{"fejl": "Når ledelsen planlægge …", "rettet": "Når ledelsen planlægger …", "hvorfor": "nutid efter grundleddet"}],
     "kilde": "egne-ord.md (Beta)", "uger_siden": 0},
]

TEKSTER = [
    {"titel": "En la estación",
     "tekst": "Lucía vive en Madrid, pero este fin de semana viaja a Sevilla para visitar a su abuela. Llega a la "
              "estación de Atocha a las nueve y media. Hay mucha gente y el tren sale a las diez, así que primero "
              "compra un café y un bocadillo.\n\nEn el andén, una mujer le pregunta si este tren va a Sevilla. Lucía "
              "mira su billete y dice que sí: es el AVE de las diez, vagón cuatro. El viaje dura dos horas y media. "
              "Lucía prefiere el tren al avión, porque puede leer, mirar por la ventana y no tiene que llegar al "
              "aeropuerto dos horas antes.",
     "ord": [["el andén", "perronen"], ["el billete", "billetten"], ["el vagón", "vognen"],
             ["el bocadillo", "sandwich (med brød)"], ["durar", "vare"], ["preferir", "foretrække"]],
     "spoergsmaal": ["¿Adónde viaja Lucía y por qué?", "¿Por qué prefiere el tren?", "¿Cómo viajas tú normalmente cuando vas de vacaciones?"]},
    {"titel": "El mercado del sábado",
     "tekst": "Todos los sábados, Pablo va al mercado con su hija. Les gusta llegar temprano, cuando la fruta está "
              "fresca y no hay mucha gente. Pablo compra tomates, naranjas y pan, y su hija siempre quiere fresas.\n\n"
              "En el mercado hay un pequeño bar. Allí toman un café y un zumo y hablan con los vecinos. Para Pablo, el "
              "sábado es el mejor día de la semana.",
     "ord": [["el mercado", "markedet"], ["temprano", "tidligt"], ["la fresa", "jordbæret"], ["el zumo", "juicen"],
             ["el vecino", "naboen"]],
     "spoergsmaal": ["¿Qué compra Pablo?", "¿Por qué llegan temprano?", "¿Qué haces tú los sábados?"],
     "svar": "Pablo compra tomates, naranjas y pan. Llegan temprano porque la fruta es fresca y no es mucha gente. "
             "Los sábados yo gusto dormir mucho y después voy a correr. Por la tarde estoy con mis amigos en un bar.",
     "feedback": "**Det, der virker:** Du svarer på alle tre spørgsmål med hele sætninger, og *por la tarde* sidder.\n\n"
                 "**Ret**\n\n"
                 "- *la fruta es fresca* → **la fruta está fresca**: frisk lige nu er en tilstand, så estar (se reglen *ser og estar*).\n"
                 "- *no es mucha gente* → **no hay mucha gente**: *der er* hedder *hay*.\n"
                 "- *yo gusto dormir* → **me gusta dormir**: det er det at sove, der behager dig.\n\n"
                 "**Næste skridt:** Øv *me gusta* og *hay* i de nye kort i denne uge."},
]


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _uge(d: date) -> str:
    aar, u, _ = d.isocalendar()
    return f"{aar}-W{u:02d}"


def _kort(t: tuple, idag: date, ny: bool = False, dage=None, stabilitet=None) -> dict:
    id_, type_, situation, niveau, forside, bagside, note, regel = t[:8]
    sp = t[0].split("-")[0]
    navn = SPROG[sp]["navn"]
    sidst = datetime.combine(idag - timedelta(days=dage), time(8, 40)).astimezone() if dage is not None else None
    return {"id": id_, "sprog": sp, "sprognavn": navn, "stemme": SPROG[sp]["stemme"], "type": type_, "situation": situation,
            "niveau": niveau, "opgave": OPGAVE[type_].format(navn.lower()), "forside": forside, "bagside": bagside,
            "note": note, "regel": regel, "ny": ny, "stabilitet": stabilitet,
            "forfald": _iso(datetime.combine(idag, time(0, 0)).astimezone()) if sidst else None,
            "sidst": _iso(sidst) if sidst else None}


def lav(ud: Path, idag: date) -> None:
    nu = datetime.now().astimezone() if idag == date.today() else datetime.combine(idag, time(9, 25)).astimezone()
    mandag = idag - timedelta(days=idag.weekday())
    soendag_aften = lambda uger: datetime.combine(mandag - timedelta(days=1 + 7 * uger), time(20, 10)).astimezone()  # noqa: E731

    sprog = {k: {**v, "niveau": None, "niveau_note": None, "niveau_sat": None} for k, v in SPROG.items()}
    sprog["es"].update(niveau="A2", niveau_sat=(mandag - timedelta(days=36)).isoformat(),
                       niveau_note="Niveautesten: A1 4/4 og A2 3/4 forståelige, B1 1/4 (datid og ser/estar)")
    sprog["de"].update(niveau="A1", niveau_sat=(mandag - timedelta(days=36)).isoformat(),
                       niveau_note="Niveautesten: A1 3/4, A2 1/4")

    koe = [_kort(t[:8], idag, ny=t[8], dage=t[9], stabilitet=t[10]) for t in KOE]
    # Som pakke() i kerne.js: alle kort med en regel, uden repetitionens felter; ny = aldrig besvaret
    regelkort = [_kort(t[:8], idag, ny=t[8]) for t in KOE if t[7]] + [_kort(t, idag) for t in REGELKORT]

    # Tallene pr. sprog: forfaldne og nye i dag er dem i køen; resten er demoens egne
    stat = {"es": {"i_alt": 64, "laert": 31, "nye_venter": 12, "test_i_alt": 16},
            "da": {"i_alt": 14, "laert": 6, "nye_venter": 2, "test_i_alt": 0},
            "en": {"i_alt": 11, "laert": 5, "nye_venter": 0, "test_i_alt": 0},
            "de": {"i_alt": 12, "laert": 7, "nye_venter": 0, "test_i_alt": 12}}
    for sp, s in stat.items():
        s.update(forfaldne=sum(1 for k in koe if k["sprog"] == sp and not k["ny"]), test_tilbage=0,
                 nye_i_dag=sum(1 for k in koe if k["sprog"] == sp and k["ny"]))

    tekster = []
    for i, t in enumerate(TEKSTER):
        skrevet = soendag_aften(i)
        tekster.append({"uge": _uge(skrevet.date() + timedelta(days=1)), "sprog": "es", "niveau": "A2", "titel": t["titel"],
                        "tekst": t["tekst"], "ord": [{"ord": o, "betydning": b} for o, b in t["ord"]],
                        "spoergsmaal": t["spoergsmaal"],
                        "opgave": "Svar på spørgsmålene i tre til fem sætninger på spansk.", "skrevet": _iso(skrevet),
                        "feedback": None, "svar": None})
        if t.get("svar"):
            svaret = skrevet + timedelta(days=3, hours=-12)
            tekster[-1]["svar"] = {"tekst": t["svar"], "tid": _iso(svaret)}
            tekster[-1]["feedback"] = {"tekst": t["feedback"], "skrevet": _iso(soendag_aften(i - 1) + timedelta(minutes=4)),
                                       "til_svar": _iso(svaret)}

    # Rutinen skriver reglerne søndag aften
    regler = [{**{k: v for k, v in r.items() if k != "uger_siden"},
               "oprettet": _iso(soendag_aften(r["uger_siden"]) + timedelta(minutes=6))} for r in REGLER]

    pakke = {
        "genereret": _iso(nu), "aktivt": "es", "sprog": sprog, "kort": koe, "tekster": tekster,
        "statistik": {"klaret_i_dag": 3, "minutter": max(1, round(len(koe) * 0.5)),
                      "naeste": _iso(datetime.combine(idag + timedelta(days=1), time(0, 0)).astimezone()),
                      "sprog": stat, "eksamensperiode": None},
        "regler": regler, "regelkort": regelkort,
        # Dit seneste svar (til "Står stille" på I dag): det sidste af dagens kort
        "sidst_svar": _iso(nu - timedelta(minutes=35)),
        # Som nyFeedback() i kerne.js: den nye tekst er ikke besvaret, og feedbacken på ugen før står forrest
        "ny_feedback": ({"uge": tekster[1]["uge"], "titel": tekster[1]["titel"], "skrevet": tekster[1]["feedback"]["skrevet"]}
                        if not tekster[0]["svar"] and tekster[1]["feedback"] else None),
    }

    # Som manifest() i server.js: den nyeste tekst og den nyeste feedback
    f = next((x for x in tekster if x["feedback"]), None)
    nyt_tekst = f"{tekster[0]['uge']}{'' if not f else '-feedback' if f is tekster[0] else '+' + f['uge'] + '-feedback'}"
    manifest = {"omraade": "Sprog", "ikon": "languages", "raekkefoelge": 25, "kilde": "sprog/server.js (live, port 8769) · demodata",
                "opdateret": _iso(nu), "sider": [
                    {"titel": "Oversigt", "ikon": "languages", "sti": "/sprog/", "praecis": True, "nyt": nyt_tekst},
                    {"titel": "Dagens kort", "ikon": "check", "sti": "/sprog/mobil.html"},
                    {"titel": "Regler", "ikon": "book-open", "sti": "/sprog/regler.html", "nyt": max(r["oprettet"] for r in regler)},
                ]}

    mappe = ud / "sprog"
    (mappe / "api").mkdir(parents=True, exist_ok=True)
    for navn, data in (("kompas.json", manifest), ("api/pakke.json", pakke), ("api/tekster.json", tekster),
                       ("api/regler.json", regler)):
        (mappe / navn).write_text(json.dumps(data, ensure_ascii=False, indent=1))
