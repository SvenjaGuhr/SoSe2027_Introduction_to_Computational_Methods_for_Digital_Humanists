# SoSe 2027 – Introduction to Computational Methods for Digital Humanists

Teaching materials for the master's course *Introduction to Computational Methods for Digital
Humanists* (University of Graz, summer semester 2027). 

<img width="1018" height="568" alt="Screenshot 2026-10-11 at 09 52 40" src="https://github.com/user-attachments/assets/e62e1b01-216f-4a94-84e8-8e3a698d288a" />



## What `fetch_wikipedia_tei.py` does

`src/fetch_wikipedia_tei.py` turns a Wikipedia article into a structured
**TEI P5** document that is ready for sentence-level annotation. It fetches the
article through the Wikipedia API (or reads a saved HTML copy) and then:

- **Keeps the section structure.** The lead and every `<h2>`/`<h3>` section
  become TEI `<div>` elements (`type="lead"`, `type="section"`,
  `type="subsection"`) with a `<head>`; every paragraph becomes a `<p>`.
- **Segments sentences.** Each sentence is an `<s>` element with a running
  `xml:id` (`s1`, `s2`, ...), so it can be referenced in annotation. Sentences
  are split with the spaCy `sentencizer` and repaired by rule where it wrongly
  split after abbreviations (such as "lit."), after ordinals (such as
  "2. Bundesliga"), or before a lower-case continuation.
- **Removes non-prose material.** Footnote markers, maintenance tags such as
  "[citation needed]", tables and infoboxes, figures and galleries, the table
  of contents, navboxes, and the reference apparatus are stripped, and
  list/table sections (squad, honours, records, references, external links, and
  similar) are skipped. Every removal is documented in the header's
  `samplingDecl`.
- **Marks foreign strings.** IPA transcriptions and other language-tagged spans
  are wrapped in `<foreign xml:lang="...">`.
- **Writes a complete `teiHeader`.** It records the person responsible for the
  encoding (`respStmt`), the publication details (`authority`, `pubPlace`,
  `date`, CC BY-SA 4.0 `availability`), the source (Wikipedia, publisher, the
  exact revision as an `idno`, and the retrieval date), the spaCy version and
  the sampling and segmentation decisions (`encodingDesc`), the languages used
  (`profileDesc`), and a `revisionDesc` entry.
- **Can validate itself.** With `--rng` the output is checked against the TEI
  `tei_all` schema, and the file carries an `<?xml-model?>` association to it.

Every run must name the encoder with `--editor` and give an `xml:id` for that
person with `--editor-id`; both are required and go into the header.

## Setup

```bash
pip install -r requirements.txt
```

The script needs only spaCy's blank pipeline plus the `sentencizer`, so no model
download is required. For `--rng` validation, download the TEI schema once:

```bash
curl -O https://tei-c.org/release/xml/tei/custom/schema/relaxng/tei_all.rng
```

The separate NER step (not part of this script) uses a trained model, installed
with `python -m spacy download en_core_web_sm`.

## Configuration

Open `src/fetch_wikipedia_tei.py` and set `REPO_URL` to this repository:

```python
REPO_URL = "https://github.com/SvenjaGuhr/SoSe2027_Computational_Methods_for_Digital_Humanities"
```

Wikimedia's API etiquette asks for a contact in the User-Agent, and the
repository URL serves as that contact, so no e-mail address is needed.

## Usage

```bash
# current revision of the English article
python src/fetch_wikipedia_tei.py --editor "Svenja Guhr" --editor-id "SG" \
    --title "SK Sturm Graz" --out data/sturm_graz.tei.xml

# pin a specific revision for reproducibility (recommended)
python src/fetch_wikipedia_tei.py --editor "Svenja Guhr" --editor-id "SG" \
    --oldid 1375555621 --out data/sturm_graz.tei.xml

# parse a locally saved HTML file instead of fetching (offline / class use)
python src/fetch_wikipedia_tei.py --editor "Svenja Guhr" --editor-id "SG" \
    --html-file page.html --oldid 1375555621 --out data/sturm_graz.tei.xml

# validate the result against the TEI schema
python src/fetch_wikipedia_tei.py --editor "Svenja Guhr" --editor-id "SG" \
    --title "SK Sturm Graz" --rng tei_all.rng
```

To find a revision id, open the article, go to *View history*, and copy the
`oldid` from a permalink. Pinning the revision keeps the text, and therefore any
annotation offsets built on it, stable across the semester.

### Options

| Option | Default | Purpose |
| --- | --- | --- |
| `--editor` | *(required)* | person responsible for the encoding |
| `--editor-id` | *(required)* | `xml:id` for that person (an XML NCName, no spaces) |
| `--title` | `SK Sturm Graz` | article title |
| `--oldid` | *(current)* | pin a specific revision id |
| `--lang` | `en` | Wikipedia language edition |
| `--html-file` | *(none)* | parse a local HTML copy instead of fetching |
| `--out` | `article.tei.xml` | output TEI path |
| `--pub-place` | `Graz` | place of publication for the header |
| `--purpose` | *(course text)* | project description for the header |
| `--skip-section` | *(default list)* | section heading to drop (repeatable; replaces the default list) |
| `--rng` | *(none)* | path to `tei_all.rng` for validation |

## Repository layout

```
.
├── README.md
├── LICENSE              # MIT, for the code
├── LICENSE-CONTENT.md   # CC BY 4.0 for teaching materials; CC BY-SA 4.0 for Wikipedia-derived data
├── .gitignore
├── requirements.txt
├── src/
│   └── fetch_wikipedia_tei.py
└── data/
    ├── ATTRIBUTION.md
    └── sample_placeholder.tei.xml   # illustrative output only; run the script for the real article
```

## Data and licensing

This repository is deliberately split:

- **Code** (`src/`) is under the **MIT License** (see `LICENSE`).
- **Teaching materials** written for the course (slides, exercises, prose) are
  under **CC BY 4.0**.
- **Wikipedia-derived data** (`data/*.tei.xml`) is under **CC BY-SA 4.0**,
  inherited from Wikipedia. It must keep that license and carry attribution; it
  cannot be relicensed under CC BY. The per-file attribution is written into
  each `teiHeader`; see `data/ATTRIBUTION.md` and `LICENSE-CONTENT.md`.

In-copyright source texts (for example news articles) are **not** stored here.
The pipeline fetches or reads them at run time, so each user obtains their own
copy, and only derived annotations are shared. The included TEI sample is a
labeled placeholder, not the Wikipedia article; run the script to generate the
real file.

## Author

Svenja Guhr. Course: *Computational Methods for Digital Humanities*, MA Digitale
Geisteswissenschaften, University of Graz, SoSe 2027.
Repository: `SvenjaGuhr/SoSe2027_Introduction_to_Computational_Methods_for_Digital_Humanists`.

## Statement of use of generative language models

The code has been supported by generative AI through translation of the English-language algorithm into python code. 
