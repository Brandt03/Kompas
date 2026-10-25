# Fagnoter

Studie-rutinens værktøj til fagnoterne: hvert fag har et Word-dokument (`<fag>/Fagnoter - <kort>.docx`), og efter
ugen sætter rutinen ugens noter ind i fagets ugeblok uden at røre det, brugeren selv har skrevet. Eksporten
(`Scripts/kompas-eksport.js`) viser ugeblokkene på Fag-siden.

| Fil | Hvad den gør |
|---|---|
| `run_notes.py <notes.py> <kilde.docx> <mål.docx>` | Læser en notes-fil og skriver noterne ind i en kopi af dokumentet |
| `fill_fagnoter.py` | Selve indsættelsen (bruges af `run_notes.py`) |
| `verify_prog.py <notes.py>` | For fag med kode: tjekker formatet og kører hvert `// →`-resultat i kodeblokkene gennem node |
| `labels.json` | Skabelonens labels (Kilder, Kernebegreber, Modeller …); eksporten læser den samme liste |
| `requirements.txt` | `pip install -r requirements.txt` (python-docx, lxml, Pillow) |

Semestrets egne filer ligger ved siden af og er ikke med i repoet: `eksempler/notes_<id>.py` (de godkendte
noter pr. fag, som rutinen efterligner) og `backup/` (en kopi af dokumentet før hver ændring).

## Dokumentet

Word-dokumentet skal have en ugeblok pr. uge som Overskrift 2 (`Uge 12 — emne`), og i blokken label-afsnit, der
starter med et navn fra `labels.json` i fed. `Kernebegreber` og `I egne ord` skal findes; `Kilder`, `Forbindelser` og
`Uafklaret` fyldes, hvis de findes. Der skal være en tom skabelonblok `Uge [x]` (bruges, når en uge mangler) og, hvis noterne har
`EKSAMEN`, en Overskrift 1 `Eksamen` med labels som `Mønstre i gamle sæt`. `I egne ord` røres aldrig.

## En notes-fil

En notes-fil er Python med en ordbog `WEEKS` (ugenummer → felter) og evt. `NEW_WEEKS` og `EKSAMEN`:

| Felt | Indhold |
|---|---|
| `kilder` | liste: kapitler, sider og slides, ugens noter bygger på |
| `begreber` | liste: `"Begreb — forklaring (s. 12)"`, præcis én ` — `; delen før bliver fed |
| `modeller_files` | liste af `(billede.jpg, billedtekst, bredde_cm)`; giver en `Modeller`-label med billederne |
| `kode` | kun fag med kode: liste af `(titel, kode)`; højst 12 linjer á 64 tegn, `// →` efter hver udskrift |
| `fejl` | kun fag med kode: liste: `"Fejlmeddelelse — hvad den betyder"` |
| `forbindelser` | én tekst: hvordan ugen hænger sammen med andre uger og fag |
| `uafklaret` | liste: `[EKS] …` for det, gamle sæt spørger om, `[?] …` for åbne spørgsmål |
| `NEW_WEEKS` | `{12: "Uge 12 — emne"}` laver ugeblokken ud fra skabelonen, hvis den mangler |
| `EKSAMEN` | `{label: [punkter]}` under Overskrift 1 `Eksamen`; kun i fagets eksempel, ikke i ugens fil |
| `RESET_WEEKS` | `[12]` tømmer ugen og lægger skabelonens tomme blok ind, før den udfyldes forfra (efter en vurdering i USB-noter); det, der står under `I egne ord`, flyttes med uændret |

`verify_prog.py` kræver `begreber`, `kode`, `fejl` og `uafklaret` i hver uge (tomme lister er nok).

Et lille, opdigtet eksempel for demoens kodefag:

```python
# Noter til Gamma, uge 12. Sidetal = lærebogens trykte sider.
WEEKS = {}

WEEKS[12] = dict(
    kilder=[
        "Lærebogen kap. 3 \"Funktioner\", s. 41-52",
        "Slides FL5: parametre s. 4-9, returværdier s. 10-14",
    ],
    begreber=[
        "Parameter — navnet i funktionens definition, som får argumentets værdi ved kaldet (s. 43)",
        "Returværdi — det, return giver tilbage; uden return giver kaldet undefined (s. 45)",
    ],
    kode=[
        ("return giver en værdi tilbage", """\
function dobbelt(x) {
  return x * 2;
}
console.log(dobbelt(4));   // → 8
console.log(typeof dobbelt(4));   // → number"""),
    ],
    fejl=[
        "TypeError: dobbelt is not a function — navnet peger på noget andet end en funktion (s. 47)",
    ],
    modeller_files=[],
    forbindelser="Funktioner samler uge 10-11's udtryk og løkker; uge 13 sender dem videre som værdier.",
    uafklaret=[
        "[EKS] \"Skriv en funktion, der …\" med eksempelkald og forventet output",
        "[?] Hvornår er en pilefunktion bedre end en almindelig funktion?",
    ],
)
```

Kør mod en kopi, før det rigtige dokument røres:

```sh
python verify_prog.py notes_gamma_uge12.py
python run_notes.py notes_gamma_uge12.py "Gamma/Fagnoter - Gamma.docx" /tmp/kopi.docx
```
