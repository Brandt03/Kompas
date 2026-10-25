"""Indsætter noter i et Fagnoter-dokument uden at røre det, brugeren selv har skrevet.

Pr. uge: tilføjer kilder, kernebegreber, en ny 'Modeller'-sektion med billeder,
forbindelser og uafklaret/[EKS]. Tomme pladsholder-punkter fjernes kun, hvis de er tomme.
'I egne ord' røres aldrig. reset_week tømmer en udfyldt uge (fx efter din vurdering på Kompas → USB-noter),
så den kan udfyldes igen; det, der står under 'I egne ord', flyttes med uændret.
"""
import copy
import json
import os
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn

# Label-afsnittene i skabelonen. Listen står i labels.json, som eksporten (Scripts/kompas-eksport.js) også læser
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "labels.json"), encoding="utf-8") as _f:
    LABELS = json.load(_f)["labels"]


def label_of(p):
    """Returnerer label-navnet, hvis afsnittet er en label (fed første run), ellers None."""
    runs = p.runs
    if not runs:
        return None
    first = runs[0]
    txt = p.text.strip()
    for lab in LABELS:
        if txt.startswith(lab) and first.bold:
            return lab
    # label-runs bruger <w:b/> direkte i rPr
    rpr = first._r.rPr
    if rpr is not None and rpr.find(qn("w:b")) is not None:
        for lab in LABELS:
            if txt.startswith(lab):
                return lab
    return None


def is_heading(p, level=None):
    s = p.style.name if p.style is not None else ""
    if level is None:
        return s.startswith("Heading")
    return s == f"Heading {level}"


def is_list(p):
    ppr = p._p.pPr
    return ppr is not None and ppr.find(qn("w:numPr")) is not None


def new_par_after(anchor_el, template_p=None):
    """Nyt tomt afsnit efter anchor_el; kopierer pPr fra template_p."""
    new_p = copy.deepcopy(template_p._p) if template_p is not None else None
    if new_p is None:
        from docx.oxml import OxmlElement
        new_p = OxmlElement("w:p")
    else:
        for child in list(new_p):
            if child.tag != qn("w:pPr"):
                new_p.remove(child)
    anchor_el.addnext(new_p)
    return new_p


def add_text_runs(par, text, gray_small=False, italic=False, bold_head=False):
    """Skriver tekst; '**x**' i starten af en linje bliver fed (begrebsnavn før ' — ')."""
    if bold_head and " — " in text and not gray_small:
        head, tail = text.split(" — ", 1)
        r = par.add_run(head)
        r.bold = True
        par.add_run(" — " + tail)
        return
    r = par.add_run(text)
    if gray_small:
        r.italic = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0x59, 0x59, 0x59)
    elif italic:
        r.italic = True


class Filler:
    def __init__(self, path):
        self.path = path
        self.doc = Document(path)
        self.body = self.doc.element.body
        # skabeloner
        self.list_tpl = next(p for p in self.doc.paragraphs if is_list(p))
        self.label_tpl = next(p for p in self.doc.paragraphs if label_of(p) == "Kernebegreber")
        self.normal_tpl = next(p for p in self.doc.paragraphs
                               if not is_list(p) and not is_heading(p) and p.text == ""
                               and p._p.pPr is not None)

    def P(self, el):
        return Paragraph(el, self.doc._body)

    def paragraphs(self):
        return [self.P(el) for el in self.body.iterchildren(qn("w:p"))]

    def block(self, heading_prefix):
        """Afsnittene fra overskriften 'Uge N' til næste overskrift."""
        ps = self.paragraphs()
        start = next(i for i, p in enumerate(ps)
                     if is_heading(p, 2) and p.text.strip().startswith(heading_prefix))
        end = next((i for i in range(start + 1, len(ps)) if is_heading(ps[i])), len(ps))
        return ps[start:end]

    def section(self, blk, label):
        """(label-afsnit, [afsnit indtil næste label])."""
        idx = next((i for i, p in enumerate(blk) if label_of(p) == label), None)
        if idx is None:
            return None, []
        out = []
        for p in blk[idx + 1:]:
            if label_of(p) is not None:
                break
            if p.text.strip().startswith("Kopiér blokken"):
                break
            out.append(p)
        return blk[idx], out

    # --- operationer ---------------------------------------------------------
    def add_list(self, label_p, items, sec, texts, bold_head=False):
        # fjern tomme pladsholder-punkter (kun helt tomme listeafsnit uden billeder)
        tpl = next((p for p in sec if is_list(p)), None)
        for p in sec:
            if is_list(p) and p.text.strip() == "" and "<w:drawing" not in p._p.xml:
                p._p.getparent().remove(p._p)
        sec = [p for p in sec if p._p.getparent() is not None]
        # indsæt efter sidste ikke-tomme listeafsnit, ellers efter label
        anchor = label_p._p
        for p in sec:
            if p.text.strip() or "<w:drawing" in p._p.xml:
                anchor = p._p
        # hvis sektionen kun har tomme normal-afsnit, brug dem ikke som anker
        tpl = tpl or self.list_tpl
        for t in texts:
            el = new_par_after(anchor, tpl)
            add_text_runs(self.P(el), t, bold_head=bold_head)
            anchor = el
        return anchor

    def add_label(self, after_el, name, hint):
        el = copy.deepcopy(self.label_tpl._p)
        after_el.addnext(el)
        runs = el.findall(qn("w:r"))
        runs[0].find(qn("w:t")).text = name
        if len(runs) > 1:
            t = runs[1].find(qn("w:t"))
            t.text = "   " + hint
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            for r in runs[2:]:
                el.remove(r)
        return el

    def add_image(self, after_el, img_path, caption, width_cm=14.5):
        el = new_par_after(after_el, self.normal_tpl)
        par = self.P(el)
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.add_run().add_picture(img_path, width=Cm(width_cm))
        cap_el = new_par_after(el, self.normal_tpl)
        cap = self.P(cap_el)
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_text_runs(cap, caption, gray_small=True)
        return cap_el

    def fill_text_section(self, label_p, sec, text):
        empty = next((p for p in sec if not is_list(p) and p.text.strip() == ""
                      and "<w:drawing" not in p._p.xml), None)
        if empty is not None and all(p.text.strip() == "" for p in sec):
            add_text_runs(empty, text)
            return empty._p
        anchor = sec[-1]._p if sec else label_p._p
        el = new_par_after(anchor, self.normal_tpl)
        add_text_runs(self.P(el), text)
        return el

    def fill_week(self, heading_prefix, d, img_dir):
        blk = self.block(heading_prefix)
        lab, sec = self.section(blk, "Kilder")
        if lab is not None and d.get("kilder"):
            self.add_list(lab, None, sec, d["kilder"])

        blk = self.block(heading_prefix)
        lab, sec = self.section(blk, "Kernebegreber")
        self.add_list(lab, None, sec, d.get("begreber", []), bold_head=True)

        # Modeller efter kernebegreberne (før 'I egne ord')
        if d.get("modeller"):
            blk = self.block(heading_prefix)
            lab, sec = self.section(blk, "Kernebegreber")
            anchor = sec[-1]._p if sec else lab._p
            anchor = self.add_label(anchor, "Modeller", "slides og figurer — tegn dem selv fra hukommelsen")
            for img, cap, width in d["modeller_files"]:
                anchor = self.add_image(anchor, img, cap, width)

        self.add_extra_sections(heading_prefix, d)

        if d.get("forbindelser"):
            blk = self.block(heading_prefix)
            lab, sec = self.section(blk, "Forbindelser")
            if lab is not None:
                self.fill_text_section(lab, sec, d["forbindelser"])

        if d.get("uafklaret"):
            blk = self.block(heading_prefix)
            lab, sec = self.section(blk, "Uafklaret")
            if lab is not None:
                self.add_list(lab, None, sec, d["uafklaret"])

    def fill_h1_section(self, h1_text, label, texts):
        ps = self.paragraphs()
        start = next(i for i, p in enumerate(ps) if is_heading(p, 1) and p.text.strip().startswith(h1_text))
        end = next((i for i in range(start + 1, len(ps)) if is_heading(ps[i], 1)), len(ps))
        blk = ps[start:end]
        lab, sec = self.section(blk, label)
        if lab is not None:
            self.add_list(lab, None, sec, texts)


    # --- nye ugeblokke ------------------------------------------------------
    def ensure_week(self, prefix, title):
        ps = self.paragraphs()
        if any(is_heading(p, 2) and p.text.strip().startswith(prefix) for p in ps):
            return
        start = next(i for i, p in enumerate(ps) if is_heading(p, 2) and p.text.strip().startswith("Uge [x]"))
        end = next((i for i in range(start + 1, len(ps)) if is_heading(ps[i])), len(ps))
        tpl_els = [p._p for p in ps[start:end]]
        anchor = tpl_els[0]
        for el in tpl_els:
            new = copy.deepcopy(el)
            anchor.addprevious(new)
            if el is tpl_els[0]:
                runs = new.findall(qn("w:r"))
                runs[0].find(qn("w:t")).text = title
                for r in runs[1:]:
                    new.remove(r)
                for pe in new.findall(qn("w:proofErr")):
                    new.remove(pe)

    def _heading_el(self, el, level=None):
        return el.tag == qn("w:p") and is_heading(self.P(el), level)

    def _block_els(self, prefix):
        """(overskrift, [elementer til næste overskrift]) for ugeblokken, der starter med prefix."""
        kids = list(self.body.iterchildren())
        start = next(i for i, el in enumerate(kids)
                     if self._heading_el(el, 2) and self.P(el).text.strip().startswith(prefix))
        end = next((i for i in range(start + 1, len(kids))
                    if self._heading_el(kids[i]) or kids[i].tag == qn("w:sectPr")), len(kids))
        return kids[start], kids[start + 1:end]

    def reset_week(self, prefix):
        """Tømmer en udfyldt uge og lægger skabelonens tomme blok ind i stedet. Overskriften bliver stående,
        og afsnittene under 'I egne ord' (brugerens egne) flyttes uændret over i den nye blok."""
        heading, els = self._block_els(prefix)
        egne, inde = [], False
        for el in els:
            if el.tag != qn("w:p"):
                inde = False
                continue
            p = self.P(el)
            lab = label_of(p)
            if lab is not None:
                inde = lab == "I egne ord"
                continue
            if p.text.strip().startswith("Kopiér blokken"):
                inde = False
            elif inde and (p.text.strip() or "<w:drawing" in el.xml):
                egne.append(copy.deepcopy(el))
        for el in els:
            el.getparent().remove(el)
        _, tpl = self._block_els("Uge [x]")
        anchor = heading
        for el in tpl:
            new = copy.deepcopy(el)
            anchor.addnext(new)
            anchor = new
        if egne:
            _, ny = self._block_els(prefix)
            lab = next(el for el in ny if el.tag == qn("w:p") and label_of(self.P(el)) == "I egne ord")
            pladsholder = lab.getnext()
            anchor = lab
            for el in egne:
                anchor.addnext(el)
                anchor = el
            if pladsholder is not None and pladsholder.tag == qn("w:p") and not self.P(pladsholder).text.strip() \
                    and label_of(self.P(pladsholder)) is None and "<w:drawing" not in pladsholder.xml:
                pladsholder.getparent().remove(pladsholder)
        return len(egne)

    # --- kode og ekstra lister ----------------------------------------------
    def add_code(self, after_el, title, code):
        el = new_par_after(after_el, self.normal_tpl)
        t = self.P(el)
        r = t.add_run(title)
        r.bold = True
        r.font.size = Pt(10)
        t.paragraph_format.space_before = Pt(6)
        t.paragraph_format.space_after = Pt(2)
        t.paragraph_format.keep_with_next = True
        anchor = el
        lines = code.strip("\n").split("\n")
        for k, line in enumerate(lines):
            el = new_par_after(anchor, self.normal_tpl)
            par = self.P(el)
            pf = par.paragraph_format
            pf.space_before = Pt(0)
            pf.space_after = Pt(0) if k < len(lines) - 1 else Pt(6)
            pf.left_indent = Cm(0.4)
            if k < len(lines) - 1:
                pf.keep_with_next = True
            ppr = el.get_or_add_pPr()
            from docx.oxml import OxmlElement
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "F2F2F2")
            after_shd = {qn("w:" + t) for t in ("tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
                         "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi",
                         "adjustRightInd", "snapToGrid", "spacing", "ind", "contextualSpacing",
                         "mirrorIndents", "suppressOverlap", "jc", "textDirection", "textAlignment",
                         "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange")}
            nxt = next((c for c in ppr if c.tag in after_shd), None)
            if nxt is not None:
                nxt.addprevious(shd)
            else:
                ppr.append(shd)
            run = par.add_run(line if line else " ")
            run.font.name = "Menlo"
            rpr = run._r.get_or_add_rPr()
            rfonts = rpr.find(qn("w:rFonts"))
            for a in ("w:ascii", "w:hAnsi", "w:cs"):
                rfonts.set(qn(a), "Menlo")
            run.font.size = Pt(8.5)
            anchor = el
        return anchor

    def add_extra_sections(self, heading_prefix, d):
        if not (d.get("kode") or d.get("fejl")):
            return
        blk = self.block(heading_prefix)
        idx = next(i for i, p in enumerate(blk) if label_of(p) == "I egne ord")
        anchor = blk[idx - 1]._p
        if d.get("kode"):
            anchor = self.add_label(anchor, "Syntaks og eksempler", "opslag til stedprøven — egne eksempler, ikke løsninger")
            for title, code in d["kode"]:
                anchor = self.add_code(anchor, title, code)
        if d.get("fejl"):
            anchor = self.add_label(anchor, "Typiske fejl", "sådan ser de ud i en fejlmeddelelse")
            for t in d["fejl"]:
                el = new_par_after(anchor, self.list_tpl)
                add_text_runs(self.P(el), t, bold_head=True)
                anchor = el

    def save(self, path=None):
        self.doc.save(path or self.path)
