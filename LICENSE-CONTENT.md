# Licensing of non-code content

The code in this repository is under the MIT License (see `LICENSE`). The
non-code content is split into two licenses, because they have different
origins.

## Teaching materials — CC BY 4.0

Slides, exercises, lesson descriptions, and other materials written for this
course are released under the Creative Commons Attribution 4.0 International
license (CC BY 4.0): https://creativecommons.org/licenses/by/4.0/

You may share and adapt them, including for commercial purposes, as long as you
give appropriate credit.

## Wikipedia-derived data — CC BY-SA 4.0

Files in `data/` that are generated from Wikipedia (the TEI articles) are under
the Creative Commons Attribution-ShareAlike 4.0 International license
(CC BY-SA 4.0): https://creativecommons.org/licenses/by-sa/4.0/

This license is inherited from Wikipedia and cannot be changed. Two obligations
follow:

1. **Attribution.** Credit the source article and the specific revision, and
   name the CC BY-SA 4.0 license. The per-file attribution is recorded in each
   TEI `teiHeader` and summarized in `data/ATTRIBUTION.md`.
2. **ShareAlike.** Any adaptation of this text must also be released under
   CC BY-SA 4.0. For this reason the Wikipedia-derived data is **not** covered
   by the CC BY 4.0 that applies to the course materials, and must be kept
   separate.

Annotations produced in this course (NER labels and the gold standard) are kept
as separate standoff files that reference the text by sentence `xml:id` or
character offset, so the annotation layer remains the author's own work under
CC BY 4.0, while any labels written inline into the TEI file become part of the
CC BY-SA 4.0 text.

## Source texts that are not redistributed here

In-copyright source texts (for example sports or news articles) are not stored
in this repository. The pipeline fetches or reads them at run time, so each user
obtains their own copy for private study, teaching, or text-and-data-mining, and
only derived annotations are shared.
