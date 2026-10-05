# webloc

Standalone Python tool for Next.js + next-intl messages in
`locales/{en,tr,es,fr,pt}.json`. English is the source and fallback.
Namespaces are retained: `InsightsHub.title` and `credits_wallet_title`
remain full Sheet keys. There is no feature routing or pt-BR remapping.

## Install and configure

Requires Python 3.10+.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
```

Copy `webloc.config.json` to the actual web repository. It is configured for the
[web Sheet](https://docs.google.com/spreadsheets/d/1vRttkL1XaZffrTb3jnD29viTvAf_SAzlhdZVVBKaLXw/edit).
Set `locales_dir` to the
directory relative to the config file. The config explicitly fixes en as
source and the five supported locales.

Tabs are `web_en`, `web_tr`, `web_es`, `web_fr`, `web_pt`; schema is
exactly `key | value`. The enforced `web_` prefix isolates the Android
language tabs even when sharing a spreadsheet. Prefer a separate web Sheet.
The old Android Sheet ID is deliberately not the configured default.

Share the Sheet with the service account email. Provide the **rotated**
credential using `GOOGLE_SA_JSON` (JSON contents or local filename).
Revoke the previously exposed private key first. Never commit credentials.
GitHub Actions expects the JSON contents in the `GOOGLE_SA_JSON` secret.

## Commands and ownership

```sh
webloc push --config webloc.config.json
webloc seed --config webloc.config.json
webloc seed --skip-fallback --config webloc.config.json
webloc pull --config webloc.config.json
webloc validate --config webloc.config.json
webloc validate --local-only --strict --config webloc.config.json
webloc validate --base-source /tmp/base-en.json --config webloc.config.json
```

- **push:** en.json defines the keys and source texts. Updates every en Sheet
  cell, adds missing rows, removes obsolete rows; preserves existing target
  Sheet translations. New target cells start blank.
- **seed:** uploads local JSON translations; overwrites existing Sheet values.
  Missing target files/keys become blank; local orphan keys are rejected.
  Run intentionally during migration, before editors start using the Sheet.
- **seed --skip-fallback:** target text exactly equal to en is uploaded blank.
  This is an optional equality heuristic, **not proof of an untranslated
  message**: brand names, numbers and valid identical translations can match.
  Without this flag identical messages are retained.
- **pull:** writes target files using source hierarchy, replacing blank or
  whitespace-only cells with local English. Never modifies en.json.
  Messages with nonblank content retain all spaces, newlines and Unicode.
- **validate:** checks both local files and Sheet; `--local-only` needs no
  credentials. Hard failures: malformed/duplicate JSON, unsupported JSON
  structure, duplicate Sheet keys, path collisions, orphan keys, missing Sheet
  rows, stale en Sheet text, ICU syntax and argument/type/tag mismatch.
  Missing or blank target translations are warnings; `--strict` makes them
  failures. A missing local file is a hard error.
  Equality with en is not a translation-status check.

For PR validation, export the **trusted base commit's** en.json and pass
`--base-source`. Only Sheet rows added/deleted by that PR, and source cells
changed relative to base, are tolerated until post-merge push. Unrelated
Sheet missing/orphan/stale rows still fail. Local orphan keys still fail.
Strict mode still requires local translations for additions. Pull never
uses the Sheet's English cells as fallback.

## JSON and ICU policies

UTF-8 output is valid JSON, sorted deterministically with two-space indentation
and a trailing newline. Object/string trees round-trip without altering message
strings. Formatting and original object order are not retained.

Arrays use zero-based bracket paths: `paywall.reviews[0].text`. Nested arrays
are supported. These are synchronization paths, not new next-intl API keys;
components using raw arrays can continue using their existing JSON structure.
Only string leaves are sent to Sheets. Numbers (including IDs), booleans, null,
empty objects and empty arrays are retained from the en.json source template
on pull. Source owns array order, length and metadata. Do not reorder array
items in en.json without migrating their Sheet translations: indices are
positions, not stable item identities.

Literal dots/brackets and empty object member names are rejected to prevent
ambiguous paths. Prefix collisions (`a` with `a.b` or `a[0]`), object/array
collisions, negative and noncanonical indices are rejected. Partial array
paths in Sheets are allowed; pull reconstructs using the complete source
template and English fallback rather than creating sparse arrays. Duplicate
JSON member names are detected before dictionary conversion.

The Python ICU profile supports named arguments, number/date/time with standard
styles, plural/selectordinal/select (required `other`, unique selectors,
offset), nested branches, apostrophe escaping and paired rich-text tags.
Argument names, types and tag names must match; locale-specific plural
categories may differ. Unsupported custom format styles, skeletons and
self-closing rich tags fail conservatively. This is a supported subset, not
a replacement for the full FormatJS parser or next-intl runtime tests.
See [FormatJS syntax](https://formatjs.github.io/docs/core-concepts/icu-syntax/).
No Vue interpolation or Android percent-placeholder rules are applied.

All locale data is checked before pull writes or Sheet mutations. Local files
use atomic per-file replacement (not a multi-file filesystem transaction).
Sheets uses one atomic `spreadsheets.batchUpdate` across all tabs: `updateCells`
with stringValue writes the header/messages and clears trailing A:B cells in
the same request. Formulas cannot be injected through message strings.
Other columns are untouched. There is no clear-then-update data-loss window.

Sheet read-modify-write has no compare-and-swap lock against human editors.
Avoid editing during push/seed; CI concurrency serializes workflow executions
within the web repo, but cannot lock editors or a second repository.
A failed batch leaves the original Sheet data intact; do not split batches
without a transactional design.

## JSON merge driver

```sh
pip install -e .
sh scripts/setup-merge.sh
```

Copy `.gitattributes` to the web repo and run the setup there with webloc
installed in the Python environment used by Git. The driver merges independent
nested edits and additions/deletions. Conflicting edits, delete-versus-edit
and object/string changes return nonzero, preserving ours for manual resolution;
it prints the conflicting path and never inserts invalid JSON conflict markers.
Git records the file as unmerged. Driver config is local and must be installed
for each clone.

## CI integration

This repository has executable PR/main tests in `test.yml`, and a reusable
`webloc.yml`. Copy `.github/workflows/web-caller.yml.example` into the actual
web repo as `.github/workflows/localization.yml`:

- PR → local and Sheet validation, using PR base en.json.
- main source merge → push.
- daily cron (04:17 UTC / 07:17 Istanbul) → validate/pull/validate → real
  translation PR via create-pull-request.
- manual dispatch → validate, push or pull.

All runs share a concurrency group with cancellation disabled.
Fork PRs have no Sheet secret: local checks run and Sheet validation explicitly
reports unavailable. No pull_request_target execution of untrusted code.
Enable GitHub Actions to create PRs in repository settings. GITHUB_TOKEN-created
PRs generally do not trigger new workflow runs; use a suitably scoped GitHub App
token if automated PR checks are required. Pin workflow/action/tool refs to
reviewed commit SHAs for production rollout.

The tool repo does not contain the real web locale files. Read-only checks of
the sibling astopia-webapp checkout verified array-aware flatten/template
reconstruction against all five complete JSON documents: en has 1746 string
leaves; tr/es/fr/pt have 1689 each. Numeric metadata and array order round-trip.
These current counts supersede the LOCALE.md counts for this checkout.

Local validation still reports two source paths incompatible with the ICU
profile: dashboard.biorhythmInfoDesc contains HTML attributes, and
celestia.ui.creditsLeft contains an unclosed credit tag. Their raw-message
usage needs a deliberate validation policy before live sync. Target locales
also have missing/blank translations (59 for tr, 57 for es/fr/pt).
Sheet permissions, remote synchronization and GitHub workflow execution
remain unverified. No credentials, remote Sheet writes, commit or push were
used for these checks; the WebApp checkout was not modified.

### Explicit raw message policy

An optional `webloc.raw-messages.json` beside the config maps full string paths to
`html-color` or `credit-token`. These contracts apply to source, local and Sheet
messages in validate, push and pull. All other messages retain ICU validation.
Unknown policies and policy keys absent from source fail validation.

`html-color` allows balanced p/strong/span/br markup and only `color: rgb(...)`
style attributes, with no interpolation. `credit-token` requires exactly one
literal `<credit>` and disallows other markup or placeholders. This is for raw
JSON consumers, not t()/t.rich(). Review any policy expansion with the consumer.
Read-only validate and pull clients use the Sheets readonly OAuth scope.
Validation reports base-source added/deleted/changed string paths explicitly.
