#!/usr/bin/env bash
# Dry-run by default, GET-only, no guest-list endpoint.
# Do not source this script. Invoke the CLI explicitly from this checkout.
set +x
set -euo pipefail
export LC_ALL=C

# Keep the future owner's key out of subprocess environments and curl argv.
export -n luma_key
luma_key=${LUMA_API_KEY-}
unset LUMA_API_KEY
readonly base='https://public-api.luma.com'

die() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }
usage() {
  cat <<'EOF'
Usage: bash integrations/luma/scripts/luma.sh [--dry-run|--live] COMMAND [ARGS]

  calendar                      Calendar name, slug and URL
  events [AFTER_UTC] [CURSOR]    One page of up to 50 events; no auto-pagination
  event evt-ID                  Basic event details and aggregate RSVP counts
  slug URL_OR_SLUG              Local parsing ONLY; never resolves an API ID

Default: --dry-run prints a GET plan without making a request or needing a key.
--live also requires LUMA_ENABLE_READS=1 and a securely supplied LUMA_API_KEY.
No write commands, invitations, exports, guest lists, webhooks or raw responses.
EOF
}

mode=dry-run
case "${1-}" in
  --live) mode=live; shift ;;
  --dry-run) shift ;;
  --help|-h|'') usage; exit 0 ;;
esac
command=${1-}
[[ $# -gt 0 ]] && shift
case "$command" in
  slug)
    [[ $# == 1 ]] || die 'slug requires exactly one URL or slug.'
    slug=$1
    case "$slug" in
      https://lu.ma/*) slug=${slug#https://lu.ma/} ;;
      https://luma.com/*) slug=${slug#https://luma.com/} ;;
      lu.ma/*) slug=${slug#lu.ma/} ;;
      luma.com/*) slug=${slug#luma.com/} ;;
      *://*|*/*) die 'Use a plain slug or an exact lu.ma/luma.com HTTPS URL.' ;;
    esac
    slug=${slug%%\?*}
    slug=${slug%%\#*}
    slug=${slug%/}
    [[ "$slug" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$ ]] || die 'Invalid event slug.'
    printf '%s\n' "$slug"
    exit 0 ;;
  calendar|events|event) ;;
  *) die 'Unsupported command; writes and guest exports are intentionally absent.' ;;
esac
command -v jq >/dev/null || die 'jq is required.'
uri() { jq -rn --arg value "$1" '$value|@uri'; }
case "$command" in
  calendar)
    [[ $# == 0 ]] || die 'calendar takes no arguments.'
    path='/v1/calendars/get'
    filter='
      if type != "object" or (.name|type) != "string"
      then error("schema") else {name,slug,url} end' ;;
  events)
    [[ $# -le 2 ]] || die 'events takes at most AFTER_UTC and CURSOR.'
    after=${1:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}
    [[ "$after" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] ||
      die 'AFTER_UTC must use YYYY-MM-DDTHH:MM:SSZ.'
    [[ $(date -u -d "$after" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null) == "$after" ]] ||
      die 'AFTER_UTC must be a real UTC date and time.'
    path="/v1/calendars/events/list?pagination_limit=50&sort_column=start_at&sort_direction=asc&after=$(uri "$after")"
    [[ -z "${2-}" ]] || path+="&pagination_cursor=$(uri "$2")"
    filter='
      if type != "object" or (.entries|type) != "array"
        or (.has_more|type) != "boolean"
      then error("schema") else
        {entries:[.entries[] | {id,name,start_at,end_at,url,visibility}],
         has_more,next_cursor:(.next_cursor // null)}
      end' ;;
  event)
    [[ $# == 1 ]] || die 'event requires exactly one evt-ID.'
    [[ "$1" =~ ^evt-[A-Za-z0-9-]{1,100}$ ]] || die 'Invalid event ID.'
    path="/v1/events/get?event_id=$(uri "$1")"
    filter='
      if type != "object" or (.id|type) != "string"
        or (.name|type) != "string"
      then error("schema") else
        {id,name,start_at,end_at,url,timezone,visibility,max_capacity,
         guest_counts:(
           if (.guest_counts|type) == "object" then
             .guest_counts | with_entries(
               select(.key == "approved" or .key == "pending_approval" or
                      .key == "waitlist" or .key == "declined" or .key == "invited")) |
             map_values({guests:(.guests|numbers),tickets:(.tickets|numbers)})
           else null end)}
      end' ;;
esac
url="${base}${path}"
if [[ "$mode" == dry-run ]]; then
  jq -n --arg url "$url" '{dry_run:true,method:"GET",url:$url}'
  exit 0
fi
[[ "${LUMA_ENABLE_READS-}" == 1 ]] || die 'Live reads are disabled; owner must explicitly enable them.'
[[ -n "$luma_key" ]] || die 'Live reads require a securely supplied new LUMA_API_KEY.'
# Only printable ASCII, with no whitespace/header injection. Never echo the key.
[[ "$luma_key" =~ ^[[:graph:]]+$ && "$luma_key" != *$'\r'* && "$luma_key" != *$'\n'* ]] ||
  die 'Invalid key format.'
command -v curl >/dev/null || die 'curl is required for live reads.'

# -q disables user curl config. Header flows through stdin, not argv or a file.
# No redirects/retries; fixed HTTPS host, bounded transfer and generic failures.
response=$(
  printf 'x-luma-api-key: %s\n' "$luma_key" |
    curl -q --silent --proto '=https' --request GET --header @- \
      --header 'Accept: application/json' --connect-timeout 5 --max-time 20 \
      --max-filesize 1048576 --write-out $'\n%{http_code}' --url "$url" 2>/dev/null
) || die 'Request failed; no response body was logged.'
unset luma_key
status=${response##*$'\n'}
body=${response%$'\n'*}
[[ "$status" =~ ^[0-9]{3}$ ]] || die 'Invalid HTTP status.'
[[ "$status" == 200 ]] || die "HTTP ${status}; no response body was logged. No automatic retry."
result=$(printf '%s' "$body" | jq -ce "$filter" 2>/dev/null) ||
  die 'Unexpected JSON response; no response body was logged.'
printf '%s\n' "$result"
