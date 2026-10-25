"""Brug: run_notes.py <notes.py> <kilde.docx> <mål.docx>
notes.py definerer WEEKS = {nr: dict(kilder, begreber, modeller_files=[(jpg, billedtekst, bredde_cm)],
kode=[(titel, kode)], fejl=[...], forbindelser, uafklaret)}, valgfrit NEW_WEEKS = {nr: overskrift}
og EKSAMEN = {label: [punkter]}. RESET_WEEKS = [nr, …] tømmer de uger først (Filler.reset_week), så de
udfyldes forfra; det, der står under 'I egne ord', flyttes med."""
import os, sys, importlib.util
sys.dont_write_bytecode = True   # ingen __pycache__ i semestermappen (den kan ligge i en synkroniseret mappe)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # fill_fagnoter.py ligger ved siden af
from fill_fagnoter import Filler
spec = importlib.util.spec_from_file_location("notes", sys.argv[1]); N = importlib.util.module_from_spec(spec); spec.loader.exec_module(N)
F = Filler(sys.argv[2])
for w in getattr(N, "RESET_WEEKS", []):
    print(f"uge {w} tømt; {F.reset_week(f'Uge {w}')} afsnit under 'I egne ord' flyttet med")
for w, title in getattr(N, "NEW_WEEKS", {}).items():
    F.ensure_week(f"Uge {w}", title)
for w, d in N.WEEKS.items():
    d = dict(d); d.setdefault("modeller", bool(d.get("modeller_files")))
    F.fill_week(f"Uge {w}", d, None)
for lab, texts in getattr(N, "EKSAMEN", {}).items():
    F.fill_h1_section("Eksamen", lab, texts)
F.save(sys.argv[3]); print("saved", sys.argv[3])
