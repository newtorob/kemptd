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
kemptd parse PATH          # show what kemptd understands (no changes)
kemptd scan  PATH          # match + emit a plan            (next release)
kemptd apply PLAN          # execute a reviewed plan        (next release)
kemptd undo  JOURNAL       # reverse the last apply         (next release)
```

## Status

Early alpha. The pure core (parse + match) and the `parse` command are implemented
and tested; providers, planning, and apply are landing next.

## License

[GPL-3.0-or-later](./LICENSE).
