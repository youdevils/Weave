# Publishing

Publishing turns one **canonical revision** of a model into a single, self-contained, read-only HTML file
(a "portable Explorer") that works offline, and records that it happened.

```
canonical DB ──load_effective_dataset(model, None)──► apply_scope ──► build_bundle ─┬─► preview JSON (Publishing page)
                                                       (Python,          (Python)    └─► render_document ─► one .html (download)
                                                    authoritative)
Portable Explorer runtime = shared Explorer kit (pure JS) + LocalSource(bundle)   ← same code in the preview and in the file
```

## Rules that must keep holding

- **Canonical only.** Data is read with `load_effective_dataset(model, None)`. No code path takes a proposal.
- **A Publication is immutable.** `save()` on an existing row and queryset `update()`/`bulk_update()` raise. There
  is no update endpoint and the admin is read-only.
- **The HTML is never stored.** It is generated in memory, returned once (`Cache-Control: no-store`) and dropped.
- **No row without a file.** `services/publishing.publish` is one transaction: lock model → build → compare with the
  preview → create row → render → validate → commit. Any failure rolls everything back (sequence numbers included).
- **What you preview is what you publish.** The preview returns a content digest; publishing must present the same
  revision and digest under the model lock, otherwise it is refused with a 409.
- **Exclusions win.** Nothing excluded by type or filter can be pulled back in by a starting object or a
  connection, and excluded content is absent from every part of the file (data, facets, history).
- **The file cannot call home.** It ships with a Content-Security-Policy (`connect-src 'none'`, scripts pinned by
  hash) and `services/portable/validator.py` inspects every generated document before it is committed.

## Layout

| Path | Purpose |
|---|---|
| `models.py` | `Publication` (snapshot definition; no HTML) |
| `services/config.py` | Scope, presentation and opening-view documents, sanitised against the data they refer to |
| `services/scoping.py` | `apply_scope`: pure, decides what is in the file |
| `services/bundle.py` | The JSON bundle and its digest; styles are resolved here |
| `services/defaults.py` | Defaults for a new publication, copied from the last successful one |
| `services/publishing.py` | `preview` and `publish` |
| `services/portable/` | ES-module inliner, asset loader, document renderer, validator |
| `views/`, `access.py` | Publishing page and endpoints; Owner/Editor only (Viewer 403, non-member 404) |
| `static/publication/js/portable/` | Entry point of the published file (bundled, never loaded live) |
| `static/publication/js/publish/` | The Publishing page |
| `tests/parity_cases.py`, `jstests/fixtures/parity.json` | Golden cases that keep the JS engine equal to the Python Explorer |

The browser-side Explorer logic (`model/static/model/js/explore/engine/`) is a port of
`model/services/model_graph/`. If you change that Python on purpose, regenerate the golden file and update the JS:

    WEAVE_UPDATE_PARITY=1 python manage.py test publication.tests.test_parity
    npm test

## Known limitations

- **No regeneration.** Canonical state has no history, so a Publication records its definition (revision, scope,
  presentation, appearance snapshot, content digest) but the exact file cannot be rebuilt later. If the response is
  lost after the transaction commits, the record exists and the file does not.
- **Appearance is not versioned with `Model.revision`**, which is why each publication stores an appearance snapshot
  and the digest covers resolved styles.
- **History is included.** Every published record carries its history and evidence, including the email of whoever
  proposed each change. The Publishing page says so; there is no switch for it yet.
- **No attribute-level redaction.** Scope works on types, records and attribute filters, not on hiding one attribute.
- **Python/JS parity edge cases.** Case folding uses a table of the characters where `toLowerCase` and Python's
  `casefold` differ; exotic scripts beyond it could sort or match differently offline than they do in the live Explorer.
- **Size.** The published object count and bytes are capped (`PUBLICATION_MAX_OBJECTS`, default 25,000, and
  `PUBLICATION_MAX_BYTES`, default 50 MB); the whole file is built in one request.
- **Browser support.** Verified in Chromium (Edge). The script hashes in the CSP are standard CSP3, but Firefox and
  Safari have not been exercised.
