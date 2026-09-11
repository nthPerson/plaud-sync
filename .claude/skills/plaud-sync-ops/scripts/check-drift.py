#!/usr/bin/env python3
"""
check-drift.py — do the file copies of the taxonomy still agree?

Adding a Project touches five places (SKILLS-SPEC.md §8.2). Miss one and nothing errors:
the automation just writes a value the schema does not have, or scores a project it has
never heard of. `DiCE Lab` sat in the prompt with no matching Notion option from whenever
it was added until 2026-08-19.

This script checks the copies that live in files:

  1. plaud-sync-prompt.txt      the Project option list handed to the sync
  2. plaud-sync-prompt.txt      the per-option glosses under it
  3. planner-prompt.txt         the scoring weight table (every project needs a weight)
  4. planner-commands-prompt.txt the hardcoded "one of the N options" count
  5. skills/.../reference/notes.md the skill's own table

It CANNOT check Notion — that needs MCP, which a script has no access to. It prints the
two fetches to run, and `verify-notion` in SKILL.md tells Claude to do the comparison.

Usage:  check-drift.py [--repo PATH] [--quiet]
Exit:   0 = consistent, 1 = drift found
"""
import argparse
import os
import re
import sys

REPO_DEFAULT = os.environ.get("WORKDIR", "/home/robert/plaud-sync")

# Options that exist only on the Plaud Notes DB, never on Tasks.
NOTES_ONLY = {"Planner"}

NOTES_DS = "collection://bbc6c9aa-a96b-4501-a41a-8bd1b5a75866"
TASKS_DS = "collection://be0b1624-4ea6-43dd-acc2-3a828a8ab07e"


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def sync_prompt_options(text):
    """The `- Project (select — one of): A, B, C` line."""
    m = re.search(r"^- Project \(select[^)]*\):\s*(.+)$", text, re.M)
    if not m:
        return None
    return [o.strip() for o in m.group(1).split(",") if o.strip()]


def sync_prompt_glosses(text):
    """Option names that have a `- Name -> explanation` gloss beneath the list."""
    block = re.search(r"^- Project \(select.*?(?=^\s*Project tie-breakers:)", text, re.M | re.S)
    if not block:
        return None
    return [m.group(1).strip() for m in
            re.finditer(r"^\s{4}- (.+?)\s+->", block.group(0), re.M)]


def planner_weight_block(text):
    """The Step 4 `Project weight: ...` block, up to the next `  Word:` line.

    Deliberately NOT parsed into names: project names contain spaces and periods
    ("GEOG 582", "BDA M.S."), and every tokenising attempt mangles them into false
    positives. Membership is tested by literal substring instead.
    """
    m = re.search(r"Project weight:(.*?)(?=\n\s{2}\w[\w ]*:)", text, re.S)
    return m.group(1) if m else None


def weight_block_leftovers(block, known):
    """Alphabetic text left after removing every known project and the scoring vocabulary.

    Anything remaining is a project named in the weights that no longer exists.
    """
    rest = block
    for name in sorted(known, key=len, reverse=True):   # longest first: "BDA M.S." before "BDA 696"
        rest = rest.replace(name, " ")
    rest = re.sub(r"\+?\d+|High|Medium|Low", " ", rest)
    rest = re.sub(r"[=·,.\s]+", " ", rest)
    return rest.strip()


def commands_prompt_count(text):
    m = re.search(r"one of the (\d+) options", text)
    return int(m.group(1)) if m else None


def skill_table_options(text):
    """Options listed in the reference table's leading backticked-name column."""
    return [m.group(1) for m in re.finditer(r"^\|\s*`([^`]+)`\s*\|", text, re.M)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=REPO_DEFAULT)
    ap.add_argument("--quiet", action="store_true", help="only print problems")
    args = ap.parse_args()
    R = args.repo

    sync = read(os.path.join(R, "plaud-sync-prompt.txt"))
    planner = read(os.path.join(R, "planner-prompt.txt"))
    commands = read(os.path.join(R, "planner-commands-prompt.txt"))
    skill = read(os.path.join(R, "skills/plaud-sync-planner/reference/notes.md"))

    missing_files = [n for n, t in (("plaud-sync-prompt.txt", sync),
                                    ("planner-prompt.txt", planner),
                                    ("planner-commands-prompt.txt", commands),
                                    ("skills/plaud-sync-planner/reference/notes.md", skill))
                     if t is None]
    if missing_files:
        print("cannot check — missing: " + ", ".join(missing_files), file=sys.stderr)
        return 1

    canon = sync_prompt_options(sync)
    if not canon:
        print("could not parse the Project list from plaud-sync-prompt.txt", file=sys.stderr)
        return 1
    canon_set = set(canon)
    tasks_set = canon_set - NOTES_ONLY

    problems = []

    glosses = set(sync_prompt_glosses(sync) or [])
    for miss in sorted(canon_set - glosses):
        problems.append(f"plaud-sync-prompt.txt: '{miss}' is listed but has no `-> ` gloss")
    for extra in sorted(glosses - canon_set):
        problems.append(f"plaud-sync-prompt.txt: gloss for '{extra}' but it is not in the list")

    block = planner_weight_block(planner)
    if block is None:
        problems.append("planner-prompt.txt: could not find the Step 4 'Project weight:' block")
    else:
        for miss in sorted(p for p in tasks_set if p not in block):
            problems.append(f"planner-prompt.txt: '{miss}' has no project weight in Step 4 scoring")
        leftover = weight_block_leftovers(block, canon_set)
        if leftover:
            problems.append(f"planner-prompt.txt: weight block names something unknown: {leftover!r}")

    n = commands_prompt_count(commands)
    if n is None:
        problems.append("planner-commands-prompt.txt: could not find the 'one of the N options' count")
    elif n != len(tasks_set):
        problems.append(f"planner-commands-prompt.txt: says {n} options, Tasks DB should have "
                        f"{len(tasks_set)} (the {len(canon_set)} in the prompt minus "
                        f"{'/'.join(sorted(NOTES_ONLY))})")

    table = set(skill_table_options(skill))
    for miss in sorted(canon_set - table):
        problems.append(f"skills/.../reference/notes.md: '{miss}' missing from the project table")

    if not args.quiet:
        print(f"{len(canon)} projects in plaud-sync-prompt.txt "
              f"({len(tasks_set)} of them valid on Tasks)")
        print("  " + " · ".join(canon))
        print()

    if problems:
        print(f"DRIFT ({len(problems)}):")
        for p in problems:
            print(f"  ✗ {p}")
    elif not args.quiet:
        print("file copies agree ✓")

    if not args.quiet:
        print("\nNotion cannot be checked from a script. To finish the check, fetch both data")
        print("sources and compare their Project options against the list above:")
        print(f"  notion-fetch {NOTES_DS}   (should have all {len(canon_set)})")
        print(f"  notion-fetch {TASKS_DS}   (should have {len(tasks_set)}, "
              f"without {'/'.join(sorted(NOTES_ONLY))})")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
