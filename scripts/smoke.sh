#!/usr/bin/env bash
# Smoke-test the running stack. Exits non-zero on the first failure.
#
# Usage:  make smoke
#         (or)  bash scripts/smoke.sh http://localhost:8000
set -eu -o pipefail

BASE="${1:-http://localhost:8000}"
DEMO_EMAIL="${DEMO_EMAIL:-demo@lumen.com}"
DEMO_PASSWORD="${DEMO_PASSWORD:-demo12345}"
JAR=$(mktemp)
trap 'rm -f "$JAR" /tmp/lumen_smoke_body' EXIT
PASS=0
FAIL=0

record() {
  local name="$1" code="$2" expect="$3"
  if [[ "$code" == "$expect" ]]; then
    printf '  \033[32m✓\033[0m  %-40s  %s\n' "$name" "$code"
    PASS=$((PASS+1))
  else
    printf '  \033[31m✗\033[0m  %-40s  %s (expected %s)\n' "$name" "$code" "$expect"
    [[ -s /tmp/lumen_smoke_body ]] && head -c 200 /tmp/lumen_smoke_body && echo
    FAIL=$((FAIL+1))
  fi
}

check() {
  local name="$1" url="$2" expect="${3:-200}"
  record "$name" "$(curl -sS -o /tmp/lumen_smoke_body -w '%{http_code}' "$url" || echo 000)" "$expect"
}

# Same, but carrying the session cookie jar so the shopper flow stays logged in.
check_session() {
  local name="$1" method="$2" url="$3" expect="$4" body="${5:-}"
  local args=(-sS -b "$JAR" -c "$JAR" -o /tmp/lumen_smoke_body -w '%{http_code}' -X "$method" "$url")
  [[ -n "$body" ]] && args+=(-H 'content-type: application/json' -d "$body")
  record "$name" "$(curl "${args[@]}" || echo 000)" "$expect"
}

echo
echo "▸ Smoking $BASE"
echo

# Liveness
check "healthz"               "$BASE/healthz"

# UI pages
check "home page"             "$BASE/"
check "catalog page"          "$BASE/catalog"
check "product detail page"   "$BASE/products/1"
check "login page"            "$BASE/login"
check "register page"         "$BASE/register"
check "cart page"             "$BASE/cart"
check "dashboards index"      "$BASE/dashboards"
check "dashboards/sales"      "$BASE/dashboards/sales"
check "dashboards/inventory"  "$BASE/dashboards/inventory"

# Shopper flow — guest cart, login, checkout
check_session "guest session cookie"           GET  "$BASE/api/cart"            200
check_session "add to cart (guest)"            POST "$BASE/api/cart/items"      201 '{"product_id":1,"quantity":2}'
check_session "login"                          POST "$BASE/api/auth/login"      200 "{\"email\":\"$DEMO_EMAIL\",\"password\":\"$DEMO_PASSWORD\"}"
check_session "whoami"                         GET  "$BASE/api/auth/me"         200
check_session "cart claimed after login"       GET  "$BASE/api/cart"            200
check_session "checkout"                       POST "$BASE/api/orders/checkout" 201 '{}'
check_session "order history"                  GET  "$BASE/api/orders"          200
check_session "logout"                         POST "$BASE/api/auth/logout"     204
check "protected route rejects anonymous"      "$BASE/api/auth/me"              401

# REST APIs — catalog
check "GET /api/catalog/categories"      "$BASE/api/catalog/categories"
check "GET /api/catalog/products"        "$BASE/api/catalog/products?limit=5"
check "GET /api/catalog/products/1"      "$BASE/api/catalog/products/1"

# REST APIs — analytics (these query the DB; require seed data)
check "GET /api/analytics/kpi"                       "$BASE/api/analytics/kpi"
check "GET /api/analytics/revenue-by-day"            "$BASE/api/analytics/revenue-by-day?days=30"
check "GET /api/analytics/top-products"              "$BASE/api/analytics/top-products?limit=5"
check "GET /api/analytics/slow-movers"               "$BASE/api/analytics/slow-movers"
check "GET /api/analytics/revenue-by-channel"        "$BASE/api/analytics/revenue-by-channel"
check "GET /api/analytics/cart-abandonment"          "$BASE/api/analytics/cart-abandonment"
check "GET /api/analytics/repeat-purchase-rate"      "$BASE/api/analytics/repeat-purchase-rate"
check "GET /api/analytics/aov-by-device"             "$BASE/api/analytics/aov-by-device"
check "GET /api/analytics/gross-margin-by-category"  "$BASE/api/analytics/gross-margin-by-category"
check "GET /api/analytics/stockouts-at-risk"         "$BASE/api/analytics/stockouts-at-risk"
check "GET /api/analytics/funnel"                    "$BASE/api/analytics/funnel"

# Static asset that ML produces
check "forecast.json"          "$BASE/static/forecast.json"

# OpenAPI
check "OpenAPI schema"         "$BASE/openapi.json"

echo
if [[ $FAIL -eq 0 ]]; then
  printf '  \033[32m%d passed, %d failed\033[0m\n' "$PASS" "$FAIL"
  exit 0
else
  printf '  \033[31m%d passed, %d failed\033[0m\n' "$PASS" "$FAIL"
  exit 1
fi
