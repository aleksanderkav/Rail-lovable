#!/usr/bin/env bash
set -euo pipefail

# -------- Config --------
: "${BASE:=https://rail-lovable-production.up.railway.app}"
: "${TOKEN:=c0bfbad7-33f4-4d8a-b5e0-77f0b5af98a1}"
ORIGIN="https://card-pulse-watch.lovable.app"

# jq optional; detect
HAVE_JQ=0; command -v jq >/dev/null 2>&1 && HAVE_JQ=1

line() { printf '%s\n' "--------------------------------------------------------------------"; }
title() { printf "🔎 %s\n" "$*"; line; }
pass() { printf "✅ %s\n" "$*"; }
fail() { printf "❌ %s\n" "$*"; }
note() { printf "ℹ️  %s\n" "$*"; }

# curl helper: prints status, headers, body files
req() {
  local method="$1"; shift
  local url="$1"; shift
  local outdir
  outdir="$(mktemp -d)"
  local hdr="$outdir/headers.txt"
  local body="$outdir/body.txt"
  local code

  # shellcheck disable=SC2068
  code=$(curl -sS -X "$method" -D "$hdr" -o "$body" "$url" $@ -w "%{http_code}" || true)
  echo "$outdir|$code|$hdr|$body"
}

# extract header (case-insensitive)
get_header() {
  local file="$1" key="$2"
  if [[ -f "$file" ]]; then
    awk -v IGNORECASE=1 -v k="$key:" '
      tolower($0) ~ tolower("^"k) {sub("\r$",""); sub("^[^:]*:[[:space:]]*",""); print; exit}
    ' "$file" 2>/dev/null || echo ""
  else
    echo ""
  fi
}

# Expect helpers
expect_status() { # url code hdrfile bodyfile expected
  local url="$1" code="$2" hdr="$3" body="$4" expected="$5"
  if [[ "$code" == "$expected" ]]; then
    pass "[$expected] $url"
    return 0
  else
    fail "Expected $expected but got [$code] for $url"
    if [[ -f "$hdr" ]]; then
      note "Headers:"; head -n 50 "$hdr" | sed 's/^/  /' 2>/dev/null || true
    fi
    if [[ -f "$body" ]]; then
      note "Body:"; head -n 200 "$body" | sed 's/^/  /' 2>/dev/null || true
    fi
    return 1
  fi
}

expect_ok_true() { # bodyfile
  local body="$1"
  if [[ -f "$body" ]]; then
    if [[ $HAVE_JQ -eq 1 ]]; then
      if jq -e '.ok == true' "$body" >/dev/null 2>&1; then
        pass "ok=true"
        return 0
      fi
    else
      if grep -q '"ok":true' "$body" 2>/dev/null; then
        pass "ok=true (grep)"
        return 0
      fi
    fi
  fi
  fail "ok != true"
  if [[ -f "$body" ]]; then
    head -n 100 "$body" | sed 's/^/  /' 2>/dev/null || true
  fi
  return 1
}

expect_json_field() { # bodyfile jq_filter description
  local body="$1" filter="$2" desc="$3"
  if [[ -f "$body" ]]; then
    if [[ $HAVE_JQ -eq 1 ]]; then
      if jq -e "$filter" "$body" >/dev/null 2>&1; then
        pass "$desc"
        return 0
      fi
    fi
    # fallback: best-effort grep
    if grep -q '"items":' "$body" 2>/dev/null; then
      pass "$desc (grep)"
      return 0
    fi
  fi
  fail "$desc missing"
  if [[ -f "$body" ]]; then
    head -n 100 "$body" | sed 's/^/  /' 2>/dev/null || true
  fi
  return 1
}

print_trace() { # hdrfile
  local hdr="$1"
  if [[ -f "$hdr" ]]; then
    local tr; tr="$(get_header "$hdr" "X-Trace-Id")"
    [[ -n "$tr" ]] && note "Trace: $tr"
  fi
}

# ----------------- Tests -----------------

title "0) Health"
R0=$(req GET "$BASE/health" -H "Origin: $ORIGIN")
IFS="|" read -r D0 C0 H0 B0 <<<"$R0"
expect_status "$BASE/health" "$C0" "$H0" "$B0" 200 || true

title "1) CORS Preflight (OPTIONS)"
for path in /scrape-now /scrape-now-fast /ingest; do
  R=$(req OPTIONS "$BASE$path" -H "Origin: $ORIGIN" -H "Access-Control-Request-Method: POST")
  IFS="|" read -r D C H B <<<"$R"
  expect_status "$BASE$path [OPTIONS]" "$C" "$H" "$B" 200 || true
  ACO="$(get_header "$H" "Access-Control-Allow-Origin")"
  if [[ "$ACO" == "$ORIGIN" ]]; then 
    pass "Allow-Origin echoed: $ACO"
  else 
    fail "Wrong/missing Allow-Origin (got: $ACO)"
  fi
  ACE="$(get_header "$H" "Access-Control-Expose-Headers")"
  if echo "$ACE" | grep -qi "x-trace-id"; then
    pass "Expose X-Trace-Id"
  else
    fail "Missing expose X-Trace-Id"
  fi
done

title "2) Instant scrape (dryRun)"
R1=$(req POST "$BASE/scrape-now" -H "Origin: $ORIGIN" -H "Content-Type: application/json" --data '{"query":"Charizard Base PSA 8","dryRun":true}')
IFS="|" read -r D1 C1 H1 B1 <<<"$R1"
expect_status "$BASE/scrape-now [POST]" "$C1" "$H1" "$B1" 200 || true
print_trace "$H1"
expect_ok_true "$B1" || true
[[ $HAVE_JQ -eq 1 ]] && expect_json_field "$B1" '.items|type=="array"' "items array" || true

title "3) Fast scrape (dryRun)"
R2=$(req POST "$BASE/scrape-now-fast" -H "Origin: $ORIGIN" -H "Content-Type: application/json" --data '{"query":"Charizard Base PSA 8","dryRun":true}')
IFS="|" read -r D2 C2 H2 B2 <<<"$R2"
expect_status "$BASE/scrape-now-fast [POST]" "$C2" "$H2" "$B2" 200 || true
print_trace "$H2"
expect_ok_true "$B2" || true

title "4) Ingest (Save) – normalized URL/ID"
PAYLOAD='{"query":"Charizard Base PSA 8","marketplace":"ebay","items":[
  {"title":"OK 1","debug_url":"https://www.ebay.com/itm/306444665735","price":"300 USD"},
  {"title":"OK 2","itemId":"123456789","price":"150 USD"},
  {"title":"OK 3","permalink":"https://www.ebay.com/itm/987654321","price":"200 USD"}
]}'
R3=$(req POST "$BASE/ingest?dryRun=true" -H "Origin: $ORIGIN" -H "Content-Type: application/json" -H "X-Admin-Token: $TOKEN" --data "$PAYLOAD")
IFS="|" read -r D3 C3 H3 B3 <<<"$R3"
expect_status "$BASE/ingest?dryRun=true [POST]" "$C3" "$H3" "$B3" 200 || true
print_trace "$H3"
[[ $HAVE_JQ -eq 1 ]] && jq -r '.accepted, .total, .skipped' "$B3" 2>/dev/null || true
expect_ok_true "$B3" || true

title "5) Ingest – only ID (URL synthesis)"
R4=$(req POST "$BASE/ingest?dryRun=true" -H "Origin: $ORIGIN" -H "Content-Type: application/json" -H "X-Admin-Token: $TOKEN" --data '{"query":"Only ID","marketplace":"ebay","items":[{"title":"OnlyID","itemId":"306444665735"}]}')
IFS="|" read -r D4 C4 H4 B4 <<<"$R4"
expect_status "$BASE/ingest?dryRun=true [OnlyID]" "$C4" "$H4" "$B4" 200 || true
print_trace "$H4"
expect_ok_true "$B4" || true

title "6) Ingest – bad item (no URL/ID)"
R5=$(req POST "$BASE/ingest?dryRun=true" -H "Origin: $ORIGIN" -H "Content-Type: application/json" -H "X-Admin-Token: $TOKEN" --data '{"query":"No URL/ID","marketplace":"ebay","items":[{"title":"Bad"}]}')
IFS="|" read -r D5 C5 H5 B5 <<<"$R5"
expect_status "$BASE/ingest?dryRun=true [Bad]" "$C5" "$H5" "$B5" 200 || true
print_trace "$H5"
expect_ok_true "$B5" || true

title "7) Auth negative (missing token)"
R6=$(req POST "$BASE/ingest?dryRun=true" -H "Origin: $ORIGIN" -H "Content-Type: application/json" --data '{"query":"No token","marketplace":"ebay","items":[]}')
IFS="|" read -r D6 C6 H6 B6 <<<"$R6"
expect_status "$BASE/ingest?dryRun=true [No token]" "$C6" "$H6" "$B6" 401 || true
print_trace "$H6"

title "8) Method enforcement (GET on fast)"
R7=$(req GET "$BASE/scrape-now-fast")
IFS="|" read -r D7 C7 H7 B7 <<<"$R7"
expect_status "$BASE/scrape-now-fast [GET]" "$C7" "$H7" "$B7" 405 || true
print_trace "$H7"

title "9) Admin diagnostics"
R8=$(req GET "$BASE/admin/diag-db" -H "X-Admin-Token: $TOKEN")
IFS="|" read -r D8 C8 H8 B8 <<<"$R8"
expect_status "$BASE/admin/diag-db" "$C8" "$H8" "$B8" 200 || true
print_trace "$H8"
expect_ok_true "$B8" || true

echo
line
echo "✅ Test run complete. Review any ❌ above. Keep X-Trace-Id for debugging in /admin/logs?trace=<id>."
line

# Cleanup temp files
for dir in "$D0" "$D1" "$D2" "$D3" "$D4" "$D5" "$D6" "$D7" "$D8"; do
  if [[ -d "$dir" ]]; then
    rm -rf "$dir" 2>/dev/null || true
  fi
done
