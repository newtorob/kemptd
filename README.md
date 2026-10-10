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

### Anime (absolute numbering)

Anime is usually released with a single running episode number (`One Piece - 1091`)
rather than season/episode. Point kemptd at the **TVDB** backend and it resolves
each absolute number to its aired season/episode before planning:

```console
export KEMPTD_TVDB_API_KEY=...             # https://thetvdb.com/api-information
kemptd scan /media/Anime --provider tvdb   # 'One Piece - 1091' → Season NN/… - SNNEMM
```

Anything it can't resolve (unknown number, or a pack spanning seasons) is skipped
rather than guessed.

### Make the servers match it, automatically

Clean filenames are what let Jellyfin/Plex/Kodi identify a file — but you can go
further and hand them the answer:

```console
kemptd scan PATH --apply --write-nfo       # drop .nfo sidecars with the provider id
kemptd scan PATH --apply --notify plex,jellyfin   # trigger a library rescan afterwards
```

- **`--write-nfo`** writes a `tvshow.nfo` (series) or `Movie (Year).nfo` (movie)
  carrying the TMDb/TVDB id, so servers match *deterministically* — no fuzzy
  guessing, even for parodies, remakes, or alternate cuts. Sidecars are journaled,
  so `undo` removes exactly what a run created.
- **`--notify`** asks the named servers to rescan once files are in place, so you
  never have to hit "Scan Library" by hand. Configure endpoints via the environment:

  ```console
  export KEMPTD_PLEX_URL=http://192.168.68.80:32400   KEMPTD_PLEX_TOKEN=...
  export KEMPTD_JELLYFIN_URL=http://192.168.68.80:8096 KEMPTD_JELLYFIN_API_KEY=...
  ```

## Fixing an existing library

`scan` organizes files so a server can match them. For items **already** in
Jellyfin that it matched *wrong* (or never matched), kemptd can diagnose and
correct them in place:

```console
export KEMPTD_JELLYFIN_URL=http://192.168.68.80:8096  KEMPTD_JELLYFIN_API_KEY=...
export KEMPTD_TMDB_API_KEY=...

kemptd diagnose --out mismatches.json      # read-only: list where TMDb disagrees
kemptd fix mismatches.json                 # dry-run: show what it would correct
kemptd fix mismatches.json --apply         # write correct-id .nfo + refresh Jellyfin
kemptd undo mismatches.fix-journal.json    # reverse it
```

`fix` only touches **never-matched** items by default (there's no correct match
to break); items where Jellyfin holds a *competing* id are skipped unless you
pass `--include-conflicts`, since those deserve a human eye.

If your server runs in Docker, its stored paths are *container* paths — map them
back to the host so `fix` writes the sidecar in the right place:

```console
kemptd fix mismatches.json --apply --path-map /media=/media/rob
```

## Status

Alpha, but **end-to-end usable**: `scan` / `apply` / `undo` all work against TMDb,
with dry-run by default, a reversible journal, optional `.nfo` sidecars, and
automatic Plex/Jellyfin rescans. Next up: TVDB/AniDB providers for anime
absolute-numbering.

## License

[GPL-3.0-or-later](./LICENSE).
