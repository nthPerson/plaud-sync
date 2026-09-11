#!/usr/bin/env bash
#
# publish.sh — push the portable skill from this repo to the syncthing workbench,
# and build a dated zip for uploading to claude.ai.
#
# Git is the source of truth; syncthing is only delivery (SKILLS-SPEC.md §6):
#
#   skills/plaud-sync-planner/          edited, reviewed, committed here
#            |  publish.sh
#   ~/sync/workbench/claude-skills/     syncthing → thinkpad, mf-pc, bg-pc
#            |  one symlink per machine, once
#   ~/.claude/skills/plaud-sync-planner
#
# The ops skill is NOT published: it lives in .claude/skills/ inside the repo and
# arrives with `git clone`.
#
# Usage:  skills/publish.sh [--no-zip] [--dry-run]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL="plaud-sync-planner"
SRC="$REPO/skills/$SKILL"
DEST_ROOT="${WORKBENCH:-$HOME/sync/workbench}/claude-skills"
DEST="$DEST_ROOT/$SKILL"
STAMP="$(date +%Y-%m-%d)"

ZIP=1
DRY=0
RSYNC_FLAGS=(-a --delete)
for arg in "$@"; do
  case "$arg" in
    --no-zip)  ZIP=0 ;;
    --dry-run) RSYNC_FLAGS+=(--dry-run); ZIP=0; DRY=1; echo "[dry-run] nothing will be written" ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

[[ -f "$SRC/SKILL.md" ]] || { echo "no SKILL.md at $SRC" >&2; exit 1; }

# The version stamp is how a Claude Chat session reports which copy it has; Chat cannot
# sync, so a drifted stamp there is the only detectable symptom. Keep it current.
FILE_STAMP="$(grep -oP '(?<=skill-version: )[0-9-]+' "$SRC/SKILL.md" || true)"
if [[ "$FILE_STAMP" != "$STAMP" ]]; then
  echo "note: SKILL.md says skill-version: ${FILE_STAMP:-<none>}, today is $STAMP"
  echo "      bump it before publishing if the content changed."
fi

if [[ ! -d "$DEST_ROOT" ]]; then
  if [[ "$DRY" == "1" ]]; then
    echo "[dry-run] would create $DEST_ROOT"
    echo "[dry-run] would publish $SKILL → $DEST"
    exit 0
  fi
  echo "creating $DEST_ROOT"
  mkdir -p "$DEST_ROOT"
fi

echo "publishing $SKILL → $DEST"
rsync "${RSYNC_FLAGS[@]}" "$SRC/" "$DEST/"

if [[ "$ZIP" == "1" ]]; then
  OUT="$DEST_ROOT/$SKILL-$STAMP.zip"
  rm -f "$OUT"
  ( cd "$REPO/skills" && zip -qr "$OUT" "$SKILL" -x '*.sync-conflict-*' )
  echo "zip for claude.ai → $OUT"
  # Keep only the three most recent zips; they are snapshots, not history (git has that).
  ls -1t "$DEST_ROOT/$SKILL"-*.zip 2>/dev/null | tail -n +4 | xargs -r rm --
fi

cat <<EOF

Done. Syncthing will carry this to the other machines within seconds.

One-time setup, on each machine that has not got it yet:
    mkdir -p ~/.claude/skills
    ln -s $DEST ~/.claude/skills/$SKILL

Claude Chat cannot sync — upload the zip by hand at claude.ai when the content changes.
EOF
