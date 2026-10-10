# kemptd

> Tidy, provider-backed media library organizer — **scan → match → plan → apply**, safely.

`kemptd` turns a pile of inconsistently-named TV and movie files into a clean,
server-ready library (Jellyfin / Plex / Kodi layout) without you hand-renaming
anything. It parses messy release names, matches them against metadata providers
with a **confidence score**, shows you a **plan**, and only then moves files —
atomically, never destructively, and with a journaled **undo**.

```console
$ kemptd parse "/media/Shows"
Parsed 42 file(s)
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Kind    ┃ Title                 ┃ Year ┃ S/E    ┃ File                       ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ episode │ Fallout               │ 2024 │ S02E01 │ www.UIndex.org - Fallo…mkv │
│ episode │ Black Clover          │      │ abs 91 │ Black Clover 091 (108…mkv  │
└─────────┴───────────────────────┴──────┴────────┴────────────────────────────┘
```

## Why

Downloaders (Sonarr/Radarr) are great at *acquiring* new media, but they choke on
*reorganizing an existing mess* — weird separators, scene prefixes, absolute-numbered
anime, split season packs. `kemptd` is purpose-built for that cleanup pass.

## Design

The core is pure and IO-free, so parsing/matching/planning are deterministic and
fully testable; side effects live at the edges.

```
         ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐   ┌─────────┐
 files → │  parse  │ → │  match   │ → │   plan   │ → │ review │ → │  apply  │ → tidy library
         │ guessit │   │ scored   │   │ (serial- │   │ (dry-  │   │ atomic  │     + undo journal
         └─────────┘   │ vs       │   │  izable) │   │  run)  │   │ moves   │
                       │ provider │   └──────────┘   └────────┘   └─────────┘
                       └──────────┘
```

- **`parse`** — `guessit`, normalized into a typed `ParsedMedia`.
- **`match`** — scores a `ParsedMedia` against provider candidates (TMDb / TVDB /
  AniDB) and assigns a confidence tier; only `HIGH` is auto-actionable.
- **`plan`** — builds a serializable plan of file actions (pure).
- **`apply`** — executes a plan with same-filesystem atomic renames, copy-verify-swap
  across filesystems, skip-on-collision, and a crash-safe journal for `undo`.

## Install

```console
pipx install kemptd        # once published
# from source:
pip install -e ".[dev]"
```

## Usage

```console
export KEMPTD_TMDB_API_KEY=...            # free key: https://www.themoviedb.org/settings/api

kemptd scan  PATH                          # dry-run: parse → match → print the plan
kemptd scan  PATH --plan-out plan.json     # save the plan to review
kemptd apply plan.json                     # execute a reviewed plan (writes an undo journal)
kemptd undo  plan.journal.json             # reverse it
kemptd scan  PATH --apply                  # scan and execute in one step

kemptd parse PATH                          # just show what kemptd parsed (no matching)
```

Only `HIGH`-confidence, cleanly-templatable matches become moves; everything else
is reported as a skip with a reason, so a bad guess never silently reorganizes a file.

## Status

Alpha, but **end-to-end usable**: `scan` / `apply` / `undo` all work against TMDb,
with dry-run by default and a reversible journal. Next up: TVDB/AniDB providers for
anime absolute-numbering.

## License

[GPL-3.0-or-later](./LICENSE).
