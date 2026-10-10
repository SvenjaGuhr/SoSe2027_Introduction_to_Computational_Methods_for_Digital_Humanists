"""Fetch a Wikipedia article and store it as TEI P5 with sentence segmentation.

The article HTML gives the structure: the lead and every <h2>/<h3> section
become TEI <div> elements with a <head>, every <p> becomes a TEI <p>.
Sentences within each paragraph are segmented with spaCy and encoded as TEI
<s> elements with a running xml:id, so each sentence is individually
addressable for annotation.

Compared with a plain text dump, the script
  * keeps the section structure (<div type="lead"> / <div type="section">),
  * removes footnote markers, maintenance tags ("citation needed"), tables,
    infoboxes and other non-prose material, and documents this in the header,
  * keeps the original spacing around links (no "Graz ," artefacts),
  * repairs typical sentencizer errors (abbreviations such as "lit.",
    ordinals such as "2. Bundesliga", sentences starting in lower case),
  * encodes IPA transcriptions as <foreign xml:lang="…-fonipa">,
  * writes a complete teiHeader (responsibility, publicationStmt with an
    agency, source with revision id and retrieval date, encodingDesc,
    profileDesc, revisionDesc).

Text source: Wikipedia, licensed CC BY-SA 4.0. The generated TEI inherits that
license and records the source, the exact revision, and the retrieval date in
its teiHeader. See LICENSE-CONTENT.md for attribution and share-alike terms.

Every run must name the person responsible for the encoding with --editor
and an xml:id for that person with --editor-id; both go into the teiHeader
(<respStmt>, <authority>, <change who="#…">).

Examples:
    # fetch the current revision of the English article
    python fetch_wikipedia_tei.py --editor "Your Name" --editor-id "YN" \
        --title "SK Sturm Graz" --out ../data/sturm_graz.tei.xml

    # pin a specific revision for reproducibility
    python fetch_wikipedia_tei.py --editor "Your Name" --editor-id "YN" \
        --oldid 1375555621 --out ../data/sturm_graz.tei.xml

    # parse a locally saved HTML file instead of fetching (offline / testing)
    python fetch_wikipedia_tei.py --editor "Your Name" --editor-id "YN" \
        --html-file page.html --title "SK Sturm Graz" --oldid 1375555621 \
        --out ../data/sample.tei.xml

    # validate the result against tei_all (download the schema once from
    # https://tei-c.org/release/xml/tei/custom/schema/relaxng/tei_all.rng)
    python fetch_wikipedia_tei.py --editor "Your Name" --editor-id "YN" \
        --title "SK Sturm Graz" --rng tei_all.rng
"""
import argparse
import datetime as dt
import re

import requests
import spacy
from bs4 import BeautifulSoup
from lxml import etree

API_TEMPLATE = "https://{lang}.wikipedia.org/w/api.php"
ARTICLE_URL = "https://{lang}.wikipedia.org/wiki/{title}"
REVISION_URL = "https://{lang}.wikipedia.org/w/index.php?oldid={revid}"
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
XML_ID = f"{{{XML_NS}}}id"
XML_LANG = f"{{{XML_NS}}}lang"
TEI_ALL = "http://www.tei-c.org/release/xml/tei/custom/schema/relaxng/tei_all.rng"
# Wikimedia's User-Agent policy asks for a contact; the repository URL serves
# as that contact, so no e-mail address is needed in the code.
REPO_URL = "https://github.com/<account>/<repository>"   # <- your public repository
USER_AGENT = f"wiki-tei-fetcher/1.1 (teaching material; {REPO_URL})"

# Material that is not running prose and is removed before text extraction.
JUNK_SELECTORS = [
    "sup.reference",          # footnote markers [1]
    "sup.noprint",            # maintenance tags: [citation needed], [when?] ...
    ".Inline-Template",
    ".mw-editsection",        # [edit] links next to headings
    "style", "script",
    "table",                  # infobox, squad tables, navboxes
    "figure", ".thumb", ".gallery",
    ".hatnote", ".shortdescription", ".navbox", ".metadata",
    ".reflist", ".mw-references-wrap", "ol.references",
    "#toc", ".toc", "#vector-toc", ".vector-toc",   # table of contents
]
# Sections whose content is lists, tables or apparatus rather than prose.
DEFAULT_SKIP_SECTIONS = [
    "Contents", "Players", "Current squad", "Out on loan", "Personnel", "Staff",
    "Honours", "Records", "Coaching staff", "Managerial history", "Statistics", "Former players", "Notable players",
    "Coaching history", "Managers", "European record", "Seasons",
    "See also", "References", "Notes", "Footnotes", "Sources",
    "Further reading", "External links",
]
LANG_NAMES = {"en": "English", "de": "German", "fr": "French", "it": "Italian",
              "es": "Spanish", "pl": "Polish", "hr": "Croatian", "sl": "Slovenian",
              "hu": "Hungarian", "la": "Latin"}
# Paragraphs that are template boilerplate, e.g. the note under squad tables.
BOILERPLATE = [
    re.compile(r"^Note: Flags indicate national team"),
    re.compile(r"^Players may hold more than one non-FIFA nationality"),
]
# Abbreviations after which the sentencizer must not split (also when an
# opening quote follows, as in "lit. 'Graz Storm'").
ABBREVIATION_END = re.compile(
    r"(?:^|[\s(])(?:lit|e\.g|i\.e|ca|approx|St|Dr|Mr|Mrs|Prof|No|vs|cf|Jr|Sr)\.\s*['‘\"]?$")


def tei(tag):
    return f"{{{TEI_NS}}}{tag}"


def sub(parent, tag, text=None, **attrs):
    el = etree.SubElement(parent, tei(tag))
    for key, value in attrs.items():
        el.set(XML_ID if key == "xml_id" else key, str(value))
    if text is not None:
        el.text = text
    return el


# --------------------------------------------------------------------------
# Fetching and HTML parsing
# --------------------------------------------------------------------------
def fetch_html(title=None, oldid=None, lang="en"):
    """Return (html, revid, title) from the Wikipedia parse API."""
    params = {"action": "parse", "prop": "text|revid|displaytitle",
              "format": "json", "formatversion": "2", "redirects": "1"}
    if oldid:
        params["oldid"] = oldid
    else:
        params["page"] = title
    resp = requests.get(API_TEMPLATE.format(lang=lang), params=params,
                        headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    parse = resp.json()["parse"]
    return parse["text"], parse["revid"], parse["title"]


def clean_text(node):
    """Text of a node without separators, so link text keeps its spacing."""
    return " ".join(node.get_text().split())


def html_to_sections(html, skip_sections, removed_log, doc_lang="en"):
    """Return the article as a list of sections.

    Each section is a dict {"head": str|None, "level": 1|2|3,
    "paragraphs": [{"text": str, "foreign": [(text, lang), ...]}]}.
    The lead has head None and level 1.
    """
    soup = BeautifulSoup(html, "html.parser")
    # A page saved from the browser also contains menus, the table of contents
    # and the footer; the article itself is inside .mw-parser-output.
    content = soup.select_one(".mw-parser-output")
    if content is not None:
        soup = content
    for junk in soup.select(", ".join(JUNK_SELECTORS)):
        junk.decompose()

    skip = {s.lower() for s in skip_sections}
    sections = [{"head": None, "level": 1, "paragraphs": []}]
    skipping_level = None          # level of the skipped section we are in

    for el in soup.find_all(["h2", "h3", "p"]):
        if el.name in ("h2", "h3"):
            level = int(el.name[1])
            head = clean_text(el)
            if skipping_level is not None and level > skipping_level:
                continue            # subsection of a skipped section
            skipping_level = None
            if head.lower() in skip:
                skipping_level = level
                removed_log["sections"].append(head)
                continue
            sections.append({"head": head, "level": level, "paragraphs": []})
            continue

        # a <p>
        if skipping_level is not None:
            continue
        if el.find_parent(["li", "td", "th", "blockquote"]):
            continue
        # IPA transcriptions and other language-tagged spans -> <foreign>
        foreign, seen = [], []
        for span in el.select("span.IPA, span[lang], i[lang]"):
            if any(span in s.descendants for s in seen):
                continue                      # nested inside a span already taken
            seen.append(span)
            classes = span.get("class") or []
            lang = span.get("lang") or ("und-fonipa" if "IPA" in classes else None)
            txt = clean_text(span)
            if lang and txt and lang.split("-")[0] != doc_lang:
                foreign.append((txt, lang))
        text = clean_text(el)
        if len(text) <= 1:
            continue
        if any(p.search(text) for p in BOILERPLATE):
            removed_log["boilerplate"] += 1
            continue
        sections[-1]["paragraphs"].append({"text": text, "foreign": foreign})

    # Keep a section if it has prose of its own, or if it is an <h2> whose
    # prose sits in <h3> subsections (e.g. "History" > "Foundation").
    kept = []
    for i, sec in enumerate(sections):
        has_sub = (sec["level"] == 2 and i + 1 < len(sections)
                   and sections[i + 1]["level"] == 3)
        if sec["paragraphs"] or has_sub:
            kept.append(sec)
    # drop <h2> containers whose subsections all turned out empty
    return [sec for i, sec in enumerate(kept)
            if sec["paragraphs"] or (i + 1 < len(kept) and kept[i + 1]["level"] == 3)]


# --------------------------------------------------------------------------
# Sentence segmentation with repair rules
# --------------------------------------------------------------------------
def segment(text, nlp, repair_log):
    """Split a paragraph into sentences and repair typical sentencizer errors.

    Merging works on character offsets, so the original spacing is kept
    (e.g. "lit. 'Graz Storm')" stays intact).
    """
    spans = [[s.start_char, s.end_char] for s in nlp(text).sents if s.text.strip()]
    merged = []
    for start, end in spans:
        if merged:
            prev = text[merged[-1][0]:merged[-1][1]].rstrip()
            nxt = text[start:end].lstrip()
            reason = None
            if ABBREVIATION_END.search(prev):
                reason = "abbreviation"
            elif re.search(r"(?:^|\s)\d{1,2}\.$", prev):   # not "2009–10."
                reason = "ordinal"            # "German 2." + "Bundesliga club …"
            elif nxt[:1].islower() or nxt[:1] in ",;:)]":
                reason = "lowercase/punctuation start"
            if reason:
                merged[-1][1] = end
                repair_log[reason] = repair_log.get(reason, 0) + 1
                continue
        merged.append([start, end])
    return [text[a:b].strip() for a, b in merged]


def fill_sentence(s_el, text, foreign):
    """Write text into <s>, wrapping known IPA strings in <foreign>."""
    targets = [(t, l) for t, l in foreign if t and t in text]
    if not targets:
        s_el.text = text
        return
    pattern = "|".join(re.escape(t) for t, _ in targets)
    langs = dict(targets)
    pos, last = 0, None
    for m in re.finditer(pattern, text):
        chunk = text[pos:m.start()]
        if last is None:
            s_el.text = chunk
        else:
            last.tail = chunk
        last = sub(s_el, "foreign", m.group(0))
        last.set(XML_LANG, langs[m.group(0)])
        pos = m.end()
    last.tail = text[pos:]


# --------------------------------------------------------------------------
# TEI
# --------------------------------------------------------------------------
def build_header(root, *, title, revid, lang, editor, editor_id, pub_place,
                 purpose, removed_log, repair_log, foreign_langs):
    today = dt.date.today().isoformat()
    header = sub(root, "teiHeader")
    file_desc = sub(header, "fileDesc")

    title_stmt = sub(file_desc, "titleStmt")
    sub(title_stmt, "title", title, type="main")
    sub(title_stmt, "title", "Sentence-segmented TEI version of the Wikipedia article",
        type="sub")
    resp_stmt = sub(title_stmt, "respStmt", xml_id=editor_id)
    sub(resp_stmt, "resp", "TEI encoding and sentence segmentation")
    sub(resp_stmt, "persName", editor)

    # publicationStmt needs an agency (publisher/distributor/authority) first
    pub = sub(file_desc, "publicationStmt")
    sub(pub, "authority", editor)
    if pub_place:
        sub(pub, "pubPlace", pub_place)
    sub(pub, "date", today, when=today)
    avail = sub(pub, "availability", status="free")
    sub(avail, "licence",
        "Text from Wikipedia, licensed under CC BY-SA 4.0. "
        "Derivatives must keep this licence and attribute the source.",
        target="https://creativecommons.org/licenses/by-sa/4.0/")

    src = sub(file_desc, "sourceDesc")
    bibl = sub(src, "bibl")
    sub(bibl, "title", title, level="m")
    sub(bibl, "author", "Wikipedia contributors")
    sub(bibl, "publisher", "Wikipedia, The Free Encyclopedia")
    if revid:
        sub(bibl, "idno", REVISION_URL.format(lang=lang, revid=revid), type="URI")
    else:
        sub(bibl, "idno", ARTICLE_URL.format(lang=lang, title=title.replace(" ", "_")),
            type="URI")
    note = sub(bibl, "note", f"Revision {revid}, retrieved " if revid else "Retrieved ")
    sub(note, "date", today, when=today).tail = "."

    enc = sub(header, "encodingDesc")
    app_info = sub(enc, "appInfo")
    app = sub(app_info, "application", ident="spaCy", version=spacy.__version__)
    sub(app, "label", "spaCy rule-based sentencizer")
    if purpose:
        sub(sub(enc, "projectDesc"), "p", purpose)
    skipped = ", ".join(removed_log["sections"]) or "none"
    sub(sub(enc, "samplingDecl"), "p",
        "Only running prose is included. Removed: infobox and all tables, figures, "
        "footnote markers, maintenance tags such as [citation needed], "
        + (f"{removed_log['boilerplate']} boilerplate paragraph(s) from templates, "
           if removed_log["boilerplate"] else "")
        + f"and the sections: {skipped}.")
    edit = sub(enc, "editorialDecl")
    repairs = ", ".join(f"{k}: {v}" for k, v in sorted(repair_log.items())) or "none"
    seg_p = sub(sub(edit, "segmentation"), "p", "Each ")
    sub(seg_p, "gi", "s").tail = (
        " element holds one sentence, split automatically with the spaCy "
        "sentencizer and repaired by rule where it split after abbreviations, "
        f"after ordinals or before lower-case continuations (repairs: {repairs}). "
        "Sentence boundaries have not been checked by hand.")
    sub(sub(edit, "normalization"), "p",
        "Whitespace was normalised; the wording of the source, including its "
        "errors, is unchanged.")

    prof = sub(header, "profileDesc")
    lang_usage = sub(prof, "langUsage")
    sub(lang_usage, "language", LANG_NAMES.get(lang, lang), ident=lang)
    for fl in sorted(foreign_langs - {lang}):
        name = LANG_NAMES.get(fl.split("-")[0], fl)
        label = f"{name}, IPA transcription" if "fonipa" in fl else name
        sub(lang_usage, "language", label, ident=fl)

    rev = sub(header, "revisionDesc")
    sub(rev, "change", "Generated with fetch_wikipedia_tei.py.",
        when=today, who=f"#{editor_id}")


def build_tei(sections, nlp, title, revid, lang, editor, editor_id,
              pub_place=None, purpose=None, removed_log=None):
    root = etree.Element(tei("TEI"), nsmap={None: TEI_NS})
    root.set(XML_LANG, lang)

    repair_log, foreign_langs = {}, set()
    text_el = etree.Element(tei("text"))
    body = sub(text_el, "body")

    s_counter = 0
    current_h2 = None
    for sec in sections:
        if sec["level"] == 3 and current_h2 is not None and current_h2.get("type") != "lead":
            div = sub(current_h2, "div", type="subsection")
        else:
            div = sub(body, "div", type="lead" if sec["head"] is None else "section")
            current_h2 = div
        if sec["head"]:
            sub(div, "head", sec["head"])
        for para in sec["paragraphs"]:
            p_el = sub(div, "p")
            foreign_langs.update(l for _, l in para["foreign"])
            for sent in segment(para["text"], nlp, repair_log):
                s_counter += 1
                s_el = sub(p_el, "s", xml_id=f"s{s_counter}")
                fill_sentence(s_el, sent, para["foreign"])

    build_header(root, title=title, revid=revid, lang=lang, editor=editor,
                 editor_id=editor_id, pub_place=pub_place, purpose=purpose,
                 removed_log=removed_log, repair_log=repair_log,
                 foreign_langs=foreign_langs)
    root.append(text_el)
    return root


def write_tei(root, path):
    doc = etree.ElementTree(root)
    pi = etree.ProcessingInstruction(
        "xml-model", f'href="{TEI_ALL}" type="application/xml" '
        'schematypens="http://relaxng.org/ns/structure/1.0"')
    root.addprevious(pi)
    doc.write(path, encoding="UTF-8", xml_declaration=True, pretty_print=True)


def validate(path, rng_path):
    schema = etree.RelaxNG(etree.parse(rng_path))
    doc = etree.parse(path)
    if schema.validate(doc):
        print("valid against", rng_path)
    else:
        for err in schema.error_log:
            print(f"line {err.line}: {err.message}")


def xml_id(value):
    """argparse type: the editor id must be a valid xml:id (an XML NCName)."""
    if not re.fullmatch(r"[A-Za-z_][\w.\-]*", value):
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a valid xml:id: start with a letter or '_', "
            "then use only letters, digits, '.', '-' or '_' (no spaces)")
    return value


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--title", default="SK Sturm Graz", help="article title")
    ap.add_argument("--oldid", help="pin a specific revision id (recommended)")
    ap.add_argument("--lang", default="en", help="Wikipedia language edition")
    ap.add_argument("--html-file", help="parse local HTML instead of fetching")
    ap.add_argument("--out", default="article.tei.xml", help="output TEI path")
    ap.add_argument("--editor", required=True,
                    help='person responsible for the encoding, e.g. "Your Name" (required)')
    ap.add_argument("--editor-id", required=True, type=xml_id,
                    help='xml:id for that person, e.g. "YN" (required)')
    ap.add_argument("--pub-place", default="Graz")
    ap.add_argument("--purpose", default=(
        "Teaching material for named entity recognition (PER and ORG) in the course "
        "'Introduction to Computational Methods for Digital Humanities', "
        "MA Digitale Geisteswissenschaften, University of Graz."))
    ap.add_argument("--skip-section", action="append", default=None,
                    help="section heading to drop (repeatable; replaces the default list)")
    ap.add_argument("--rng", help="path to tei_all.rng for validation")
    args = ap.parse_args()

    if args.html_file:
        with open(args.html_file, encoding="utf-8") as fh:
            html = fh.read()
        revid, title = args.oldid, args.title
    else:
        html, revid, title = fetch_html(args.title, args.oldid, args.lang)

    nlp = spacy.blank(args.lang)
    nlp.add_pipe("sentencizer")

    removed_log = {"sections": [], "boilerplate": 0}
    sections = html_to_sections(html, args.skip_section or DEFAULT_SKIP_SECTIONS,
                                removed_log, args.lang)
    root = build_tei(sections, nlp, title, revid, args.lang, args.editor, args.editor_id,
                     args.pub_place, args.purpose, removed_log)
    write_tei(root, args.out)

    n_par = sum(len(s["paragraphs"]) for s in sections)
    n_sents = sum(1 for _ in root.iter(tei("s")))
    print(f"{title}: rev {revid}, {len(sections)} divs, {n_par} paragraphs, "
          f"{n_sents} sentences -> {args.out}")
    if removed_log["sections"]:
        print("skipped sections:", ", ".join(removed_log["sections"]))
    if args.rng:
        validate(args.out, args.rng)


if __name__ == "__main__":
    main()
