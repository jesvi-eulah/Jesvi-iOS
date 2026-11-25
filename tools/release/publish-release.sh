#!/usr/bin/env bash
# publish-release.sh TAG DIR [INSTALLER_URL] [draft|publish]
# Add one board build (DIR = the workflow's release output) to GitHub release TAG and rewrite
# its notes (UN1CA/ExtremeROM layout: Changelog, then Download per phone). Run once per board.
#   - The installer stays ONE file (over GitHub's 2 GiB asset limit), hosted by the maintainer:
#     the notes keep a placeholder line "INSTALLER LINK: x1s" to replace by hand, unless
#     INSTALLER_URL is given.
#   - Restore ZIPs go on the release; SHA256SUMS lists every ZIP, the installer included.
#   - draft (default) stays hidden until you press Publish on GitHub.
# Needs GH_TOKEN with contents:write and GH_REPO=owner/repo.
set -euo pipefail
tag=${1:?usage: publish-release.sh TAG DIR [INSTALLER_URL] [draft|publish]}; dir=${2:?dir}; link=${3:-}; state=${4:-draft}
[[ $tag =~ ^v[0-9][0-9A-Za-z.+-]{0,31}$ ]] || { echo "tag must look like v0.4 or v0.4-beta1" >&2; exit 2; }
[[ $state == draft || $state == publish ]] || { echo "state: draft or publish" >&2; exit 2; }
[[ -z $link || $link =~ ^https://[^[:space:]]+$ ]] || { echo "installer url must be https" >&2; exit 2; }
link=${link:--}
: "${GH_REPO:?set GH_REPO}"
sha() { if command -v sha256sum >/dev/null; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }
stage=$(mktemp -d); trap 'rm -rf "$stage"' EXIT

shopt -s nullglob
inst=("$dir"/Jesvi-iOS_*.zip); rest=("$dir"/Jesvi-iOS-Restore_*.zip)
[ ${#inst[@]} -eq 1 ] || { echo "expected one installer ZIP in $dir" >&2; exit 1; }
iname=$(basename "${inst[0]}")
board=$(sed -nE 's/^Jesvi-iOS_.*_([a-z0-9-]+)\.zip$/\1/p' <<<"$iname")
[ -n "$board" ] || { echo "cannot read the board from $iname" >&2; exit 1; }
gb=$(awk -v b="$(wc -c < "${inst[0]}")" 'BEGIN{printf "%.2f", b/1e9}')

if ! gh release view "$tag" >/dev/null 2>&1; then
  gh release create "$tag" --draft --title "Jesvi iOS $tag" --notes "Building..." --target "${GITHUB_SHA:-main}"
fi
# Merge with what earlier board builds put on this release.
mkdir -p "$stage/old"
gh release download "$tag" --pattern SHA256SUMS --pattern installers.txt --dir "$stage/old" 2>/dev/null || true
{ cat "$stage/old/SHA256SUMS" 2>/dev/null || true; (cd "$dir" && sha "$iname" "${rest[@]##*/}"); } |
  awk '{seen[$2]=$0} END{for(k in seen) print seen[k]}' | sort -k2 > "$stage/SHA256SUMS"
# Keep installer links the maintainer already pasted into the notes ("- [Installer](URL)" under "### ... (board)").
gh release view "$tag" --json body --jq .body > "$stage/body.md" 2>/dev/null || true
pasted() { awk -v b="($1)" '/^### /{on=(index($0,b)>0)} on && /^- \[Installer\]\(https:/{sub(/^- \[Installer\]\(/,""); sub(/\).*$/,""); print; exit}' "$stage/body.md"; }
{
  while read -r b size name href; do
    [ "$b" = "$board" ] && continue
    p=$(pasted "$b"); echo "$b $size $name ${p:-$href}"
  done < <(cat "$stage/old/installers.txt" 2>/dev/null || true)
  p=$(pasted "$board"); [ "$link" = - ] && [ -n "$p" ] && [ "$(awk -v b="$board" '$1==b{print $3}' "$stage/old/installers.txt" 2>/dev/null)" = "$iname" ] && link=$p
  echo "$board $gb $iname $link"
} | sort > "$stage/installers.txt"
rm -f "$stage/body.md"
cp "${rest[@]}" "$stage/"
rm -rf "$stage/old"
gh release upload "$tag" --clobber "$stage"/*

url="https://github.com/$GH_REPO/releases/download/$tag"
title() { case $1 in x1s) echo "Galaxy S20 (4G/5G)";; y2s) echo "Galaxy S20+ (4G/5G)";; *) echo "$1";; esac; }
restores=$(gh release view "$tag" --json assets --jq '.assets[].name' | grep '^Jesvi-iOS-Restore_' || true)
ref=${GITHUB_SHA:-$(git rev-parse HEAD)}
prev=$(git describe --tags --abbrev=0 --match 'v*' "$ref^" 2>/dev/null || true)
{
  echo "iOS 16.5 (20F66) for Exynos 990 Galaxy phones. Needs TWRP and an unlocked bootloader."
  echo; echo "## Changelog"
  if [ -n "$prev" ]; then
    git log --no-merges --format='- %s' "$prev..$ref" -- . ':!docs' ':!*.md' | grep -viE '^- (docs|tests?|ci):' | head -15
  else
    echo "- First release built by CI"
  fi
  echo; echo "## Download"
  while read -r b size name href; do
    echo; echo "### $(title "$b") ($b)"
    if [ "$href" = - ]; then echo "- Installer: **INSTALLER LINK: $b**"; else echo "- [Installer]($href)"; fi
    for r in $(grep -E "_${b}\.zip$" <<<"$restores" || true); do echo "- [Restore to Android]($url/$r)"; done
    echo '```'
    echo "File: $name ($size GB)"
    echo "SHA256: $(awk -v n="$name" '$2==n{print $1}' "$stage/SHA256SUMS")"
    echo '```'
  done < "$stage/installers.txt"
  echo
  echo "## Install"
  echo "TWRP → Install → the installer ZIP. It checks the phone, then starts after **10 s**:"
  echo "**Volume Up** starts now, **Volume Down** or **Power** cancels. Fresh install erases userdata."
  echo
  echo "[Install guide](https://github.com/$GH_REPO/blob/$ref/docs/release/install.md) · [Back to Android](https://github.com/$GH_REPO/blob/$ref/docs/release/rollback.md) · [All checksums]($url/SHA256SUMS)"
} > "$stage/notes.md"
gh release edit "$tag" --notes-file "$stage/notes.md"
[ "$state" = publish ] && gh release edit "$tag" --draft=false
echo "release $tag: $(gh release view "$tag" --json url --jq .url) ($state)"
