#!/usr/bin/env bash
# publish-release.sh TAG DIR INSTALLER_URL [draft|publish]
# Add one board build (DIR = the workflow's release output) to GitHub release TAG and rewrite
# its notes for every board the release holds. Run once per board (x1s, y2s, ...).
#   - The installer stays ONE file. It is over GitHub's 2 GiB release-asset limit, so the
#     notes link INSTALLER_URL (the build's artifact download) instead of uploading it.
#     Artifact links need a GitHub login and expire with the artifact's retention.
#   - Restore ZIPs go on the release; SHA256SUMS lists every ZIP, the installer included.
#   - draft (default) stays hidden until you press Publish on GitHub.
# Needs GH_TOKEN with contents:write and GH_REPO=owner/repo.
set -euo pipefail
tag=${1:?usage: publish-release.sh TAG DIR INSTALLER_URL [draft|publish]}; dir=${2:?dir}; link=${3:?installer url}; state=${4:-draft}
[[ $tag =~ ^v[0-9][0-9A-Za-z.+-]{0,31}$ ]] || { echo "tag must look like v0.4 or v0.4-beta1" >&2; exit 2; }
[[ $state == draft || $state == publish ]] || { echo "state: draft or publish" >&2; exit 2; }
[[ $link =~ ^https://[^[:space:]]+$ ]] || { echo "installer url must be https" >&2; exit 2; }
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
{ grep -v "^$board " "$stage/old/installers.txt" 2>/dev/null || true; echo "$board $gb $iname $link"; } | sort > "$stage/installers.txt"
cp "${rest[@]}" "$stage/"
rm -rf "$stage/old"
gh release upload "$tag" --clobber "$stage"/*

url="https://github.com/$GH_REPO/releases/download/$tag"
title() { case $1 in x1s) echo "Galaxy S20 · SM-G980F / SM-G981B";; y2s) echo "Galaxy S20+ · SM-G986B / SM-G985F";; *) echo "$1";; esac; }
restores=$(gh release view "$tag" --json assets --jq '.assets[].name' | grep '^Jesvi-iOS-Restore_' || true)
{
  echo "iOS 16.5 (20F66) for Exynos 990 Galaxy phones."
  while read -r b size name href; do
    echo; echo "### $b Downloads ($(title "$b"))"; echo
    echo "- [Jesvi iOS installer · $size GB]($href) (\`$name\`, inside the download's artifact ZIP; GitHub login needed)"
    for r in $(grep -E "_${b}\.zip$" <<<"$restores" || true); do echo "- [Restore to Android]($url/$r)"; done
  done < "$stage/installers.txt"
  echo; echo "- [SHA256SUMS]($url/SHA256SUMS)"
  echo
  echo "Install: unzip the download, then TWRP → Install → the \`Jesvi-iOS_…zip\`. It checks the phone, then starts"
  echo "after **10 seconds**: press **Volume Up** to start at once, **Volume Down** or **Power** to cancel. Fresh install erases userdata."
  echo "Restore checks the phone and erases iOS data only after you press **Volume Up**."
  echo
  ref=${GITHUB_SHA:-$(git rev-parse HEAD)}
  echo "[Install guide](https://github.com/$GH_REPO/blob/$ref/docs/release/install.md) · [Rollback guide](https://github.com/$GH_REPO/blob/$ref/docs/release/rollback.md)"
} > "$stage/notes.md"
gh release edit "$tag" --notes-file "$stage/notes.md"
[ "$state" = publish ] && gh release edit "$tag" --draft=false
echo "release $tag: $(gh release view "$tag" --json url --jq .url) ($state)"
