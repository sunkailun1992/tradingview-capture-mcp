#!/usr/bin/env bash
# Fail when files that would be published contain things that must stay private:
# token-shaped strings, local absolute paths, IPv4 addresses other than loopback, and the
# maintainer's private terms, kept outside the repository (one per line, # for comments).
# A line containing the marker "private-content: allow" is skipped; use it only for test fixtures.
set -euo pipefail

mode="${1:-tracked}"
terms_file="${TRADINGVIEW_CAPTURE_PRIVATE_TERMS:-$HOME/.config/tradingview-capture-mcp/private-terms.txt}"
cd "$(git rev-parse --show-toplevel)"

token_re='(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{30,}|xox[abprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'
path_re='(/Users/[A-Za-z0-9._-]+/|/Volumes/[A-Za-z0-9._-]+/|/home/[a-z_][a-z0-9_-]*/)'
octet='(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])'
ip_re="(^|[^/A-Za-z0-9.])(${octet}\\.){3}${octet}([^0-9.]|\$)"
allow='private-content: allow'
status=0

report() {
  printf '%s:%s: %s\n' "$1" "$2" "$3"
  status=1
}

matching_lines() {  # pattern flags; content in $content
  grep -n "$1" -- "$2" <<<"$content" | grep -vF -- "$allow" || true
}

scan_file() {  # file name; content on stdin
  local file="$1" hit term
  content="$(cat; printf x)"
  content="${content%x}"
  while IFS= read -r hit; do [[ -n "$hit" ]] && report "$file" "${hit%%:*}" token; done < <(matching_lines -E "$token_re")
  while IFS= read -r hit; do [[ -n "$hit" ]] && report "$file" "${hit%%:*}" local-path; done < <(matching_lines -E "$path_re")
  while IFS= read -r hit; do
    [[ -z "$hit" ]] && continue
    if grep -Eo -- "$ip_re" <<<"${hit#*:}" | grep -Eqv '(127\.0\.0\.1|0\.0\.0\.0)'; then
      report "$file" "${hit%%:*}" ip-address
    fi
  done < <(matching_lines -E "$ip_re")
  if [[ -f "$terms_file" ]]; then
    while IFS= read -r term || [[ -n "$term" ]]; do
      [[ -z "$term" || "$term" == \#* ]] && continue
      while IFS= read -r hit; do [[ -n "$hit" ]] && report "$file" "${hit%%:*}" private-term; done < <(matching_lines -F "$term")
    done <"$terms_file"
  fi
}

if [[ "$mode" == "--staged" ]]; then
  list_files() { git diff --cached --name-only --diff-filter=ACMR; }
  show_file() { git show ":$1"; }
else
  list_files() { git ls-files; }
  show_file() { cat -- "$1"; }
fi

while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  case "$file" in *.png|*.jpg|*.jpeg|*.gif|*.ico|*.pdf|*.woff|*.woff2) continue ;; esac
  [[ "$mode" != "--staged" && ! -f "$file" ]] && continue
  scan_file "$file" < <(show_file "$file")
done < <(list_files)

if [[ $status -ne 0 ]]; then
  echo "private-content check failed: remove these lines, or mark deliberate test fixtures with \"$allow\"" >&2
fi
exit $status
