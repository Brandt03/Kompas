#!/usr/bin/env python3
"""Henter studiejob og praktikopslag fra Jobindex, forfiltrerer dem og lægger nye i køen.

Kun standardbiblioteket bruges. Kør:  python3 hent_jobs.py
Resultat: én JSON-fil pr. nyt relevant opslag i data/koe/, som rutinen (RUTINE.md) behandler.
"""
import html
import json
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

ROD = Path(__file__).resolve().parent
DATA = ROD / "data"
KOE = DATA / "koe"
SET_FIL = DATA / "set.json"
LOG_FIL = DATA / "frasorteret.log"
CV_PDF = ROD.parent / "CV.pdf"
CV_TXT = ROD / "cv.txt"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) jobagent/1.0 (personlig brug)"
PAUSE = 1.0  # sekunder mellem forespørgsler - vær høflig over for Jobindex

# Fritekstsøgningen rammer også opslag, hvor ordet kun står i brødteksten. Vi beholder kun dem,
# hvor titlen selv siger studiejob/praktik. "intern" tæller kun som sidste ord eller før tegnsætning,
# så "Intern sælger" og "Intern revision" ikke kommer med.
STUDIE_TITEL = re.compile(
    r"student(?!ereksamen)|studiejob|studiestilling|praktik|internship|trainee"
    r"|(?<!\w)interns?(?=\s*$|\s*[-–|(,/:])", re.I)
IKKE_STUDIE_TITEL = re.compile(r"ph\.?d|doctoral|studenterrådgiv|student affairs", re.I)
# Står der både studiejob og praktik/trainee i titlen, vinder studiejob.
PRAKTIK_TITEL = re.compile(r"^(?!.*(student|studiejob)).*(praktik|internship|trainee|(?<!\w)interns?(?!\w))", re.I)

# python.org-Python på macOS har ikke selv rodcertifikater; brug systemets bundt hvis det findes.
_MAC_CA = Path("/etc/ssl/cert.pem")
SSL_CTX = ssl.create_default_context(cafile=str(_MAC_CA) if _MAC_CA.exists() else None)


def aabn(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=20, context=SSL_CTX)


def html_til_tekst(s: str) -> str:
    s = re.sub(r"(?is)<(script|style|nav|header|footer|noscript)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def laes_rss(url: str) -> list[dict]:
    with aabn(url) as r:
        root = ET.fromstring(r.read())  # XML-erklæringen angiver selv tegnsættet (ISO-8859-1)
    jobs = []
    for item in root.iter("item"):
        titel_fuld = (item.findtext("title") or "").strip()
        # Jobindex-titler har formen "Jobtitel, Virksomhed"
        titel, _, firma = titel_fuld.rpartition(", ")
        if not titel:
            titel, firma = titel_fuld, ""
        link = (item.findtext("link") or "").strip()
        m = re.search(r"/vis-job/([a-z]?\d+)", link)
        jid = m.group(1) if m else link
        beskrivelse = item.findtext("description") or ""
        omraade = re.search(r'jix_robotjob--area">([^<]*)<', beskrivelse)
        try:
            dato = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
        except (TypeError, ValueError):
            dato = ""
        jobs.append({
            "id": jid,
            "titel": html.unescape(titel),
            "firma": html.unescape(firma),
            "link": link,
            "omraade": html.unescape(omraade.group(1)).strip() if omraade else "",
            "kategorier": [c.text.strip() for c in item.findall("category") if c.text],
            "teaser": html_til_tekst(beskrivelse)[:1200],
            "indrykket": dato,
        })
    return jobs


def hent_soegning(params: dict, navn: str, max_sider: int) -> list[dict]:
    """Bladrer gennem én Jobindex-søgning, indtil en side har færre end 20 opslag."""
    jobs: list[dict] = []
    for side in range(1, max_sider + 1):
        q = urllib.parse.urlencode({**params, "page": side})
        try:
            side_jobs = laes_rss(f"https://www.jobindex.dk/jobsoegning.rss?{q}")
        except Exception as e:  # noqa: BLE001
            print(f"! RSS-fejl ({navn}, side {side}): {e}", file=sys.stderr)
            break
        jobs += side_jobs
        time.sleep(PAUSE)
        if len(side_jobs) < 20:
            break
    return jobs


def matcher(ord_: str, tekst: str) -> bool:
    ord_ = ord_.strip().lower()
    slut = r"(?!\w)" if len(ord_) <= 3 else ""
    return re.search(r"(?<!\w)" + re.escape(ord_) + slut, tekst) is not None


def forfilter(job: dict, cfg: dict) -> tuple[int, list[str]]:
    tekst = " ".join([job["titel"], job["firma"], job["teaser"], " ".join(job["kategorier"])]).lower()
    score, hits = 0, []
    for vaegt, ordliste in cfg["positive_ord"].items():
        for o in ordliste:
            if matcher(o, tekst):
                score += int(vaegt)
                hits.append(o)
    for k in job["kategorier"]:
        if k in cfg["positive_kategorier"]:
            score += 2
            hits.append(f"kategori:{k}")
    titel = job["titel"].lower()
    for o in cfg["negative_ord"]:
        if matcher(o, titel):
            score -= 10  # negativt ord i titlen: næsten altid irrelevant
            hits.append(f"-{o}")
        elif matcher(o, tekst):
            score -= 3
            hits.append(f"-{o}")
    return score, hits


def hent_fuld_annonce(job: dict) -> tuple[str, str]:
    """Jobindex' /jobannonce/-side har den fulde tekst, hvis annoncen ligger hos Jobindex.
    Ellers viderestilles der til virksomhedens side, som vi også forsøger at læse."""
    nr = job["id"]
    for url in (f"https://www.jobindex.dk/jobannonce/{nr}/", job["link"]):
        try:
            with aabn(url) as r:
                slut_url = r.geturl()
                charset = r.headers.get_content_charset() or "utf-8"
                tekst = html_til_tekst(r.read().decode(charset, errors="replace"))
            if len(tekst) > 800:
                return tekst[:15000], slut_url
        except Exception as e:  # noqa: BLE001 - en enkelt fejlet annonce må ikke stoppe kørslen
            print(f"  ! kunne ikke hente {url}: {e}", file=sys.stderr)
        time.sleep(PAUSE)
    return "", job["link"]


def opdater_cv_tekst() -> None:
    if not CV_PDF.exists():
        return
    if CV_TXT.exists() and CV_TXT.stat().st_mtime >= CV_PDF.stat().st_mtime:
        return
    pdftotext = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
    try:
        subprocess.run([pdftotext, "-layout", str(CV_PDF), str(CV_TXT)], check=True)
        print("cv.txt opdateret fra CV.pdf")
    except Exception as e:  # noqa: BLE001
        print(f"! kunne ikke konvertere CV.pdf ({e}) - Claude læser så PDF'en direkte", file=sys.stderr)


def main() -> None:
    cfg = json.loads((ROD / "config.json").read_text(encoding="utf-8"))
    KOE.mkdir(parents=True, exist_ok=True)
    set_ids: dict = json.loads(SET_FIL.read_text()) if SET_FIL.exists() else {}
    i_koe = {p.stem for p in KOE.glob("*.json")}
    opdater_cv_tekst()

    alle: dict[str, dict] = {}
    for geo in cfg["geoareaid"]:
        for et, et_navn in cfg["employment_types"].items():
            for j in hent_soegning({"geoareaid": geo, "employment_type": et}, et_navn,
                                   cfg["max_sider_pr_soegning"]):
                j["type"] = et_navn
                alle.setdefault(j["id"], j)
    taggede = len(alle)

    # Ikke alle virksomheder sætter mærket Studiejob/Praktik, så søg også på ordene i fritekst.
    for geo in cfg["geoareaid"]:
        for ord_ in cfg.get("fritekst_soegninger", []):
            for j in hent_soegning({"geoareaid": geo, "q": ord_}, f"'{ord_}'",
                                   cfg.get("max_sider_pr_fritekst", 20)):
                if j["id"] in alle or not STUDIE_TITEL.search(j["titel"]) or IKKE_STUDIE_TITEL.search(j["titel"]):
                    continue
                j["type"] = "Praktik" if PRAKTIK_TITEL.search(j["titel"]) else "Studiejob"
                j["uden_jobindex_maerke"] = True
                alle[j["id"]] = j
    print(f"{len(alle)} aktive opslag fundet på Jobindex "
          f"({taggede} med mærket studiejob/praktik, {len(alle) - taggede} uden mærke via fritekst)")

    nye = [j for jid, j in alle.items() if jid not in set_ids and jid not in i_koe]
    kandidater, frasorteret = [], []
    for j in nye:
        j["forfilter_score"], j["forfilter_hits"] = forfilter(j, cfg)
        (kandidater if j["forfilter_score"] >= cfg["min_forfilter_score"] else frasorteret).append(j)

    nu = datetime.now().isoformat(timespec="seconds")
    with LOG_FIL.open("a", encoding="utf-8") as log:
        for j in frasorteret:
            set_ids[j["id"]] = {"dato": nu, "status": "frasorteret", "titel": j["titel"], "firma": j["firma"]}
            log.write(f"{nu}\t{j['forfilter_score']}\t{j['id']}\t{j['titel']} - {j['firma']}\n")

    # De bedste først; resten bliver liggende til næste kørsel (markeres ikke som set).
    kandidater.sort(key=lambda j: (j["forfilter_score"], j["indrykket"]), reverse=True)
    udvalgt = kandidater[: cfg["max_nye_pr_koersel"]]
    for j in udvalgt:
        print(f"  + [{j['forfilter_score']:>3}] {j['titel']} - {j['firma']}")
        j["fuld_tekst"], j["kilde_url"] = hent_fuld_annonce(j)
        j["hentet"] = nu
        (KOE / f"{j['id']}.json").write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
        set_ids[j["id"]] = {"dato": nu, "status": "i_koe", "titel": j["titel"], "firma": j["firma"]}

    SET_FIL.write_text(json.dumps(set_ids, ensure_ascii=False, indent=1), encoding="utf-8")
    rest = len(kandidater) - len(udvalgt)
    print(f"\n{len(nye)} nye opslag: {len(udvalgt)} lagt i kø, {len(frasorteret)} frasorteret af forfilteret"
          + (f", {rest} relevante venter til næste kørsel" if rest else ""))
    print(f"Køen indeholder nu {len(list(KOE.glob('*.json')))} opslag i {KOE}")


if __name__ == "__main__":
    main()
