#!/bin/bash
# Tests for MEMORY_DIR resolution in scripts/sync-memory.sh:
#   - SUTANDO_MEMORY_DIR explicit override
#   - SUTANDO_PRIVATE_DIR legacy alias
#   - find-fallback guarded against overriding an explicit override
#
# Run: bash tests/sync-memory-memory-dir.test.sh
# Exit: 0 on pass, 1 on fail.

set -u
SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/scripts/sync-memory.sh"

if [ ! -f "$SCRIPT" ]; then
    echo "FAIL: $SCRIPT not found"
    exit 1
fi

# Extract the primary MEMORY_DIR resolution block.
RESOLVE_BLOCK="$(awk '
    /^if \[ -n "\$\{SUTANDO_MEMORY_DIR/  { capture = 1 }
    capture                               { print }
    capture && /^fi$/                     { capture = 0; exit }
' "$SCRIPT")"

# Extract the find-fallback guard block.
FALLBACK_BLOCK="$(awk '
    /Auto-detect memory dir/  { capture = 1 }
    capture                   { print }
    capture && /^fi$/         { capture = 0; exit }
' "$SCRIPT")"

if [ -z "$RESOLVE_BLOCK" ]; then
    echo "FAIL: could not extract MEMORY_DIR resolution block (anchor changed?)"
    exit 1
fi

if [ -z "$FALLBACK_BLOCK" ]; then
    echo "FAIL: could not extract find-fallback block (anchor changed?)"
    exit 1
fi

PASS=0
FAIL=0

check() {
    local name="$1" got="$2" want="$3"
    if [ "$got" = "$want" ]; then
        echo "PASS: $name"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $name — got '$got', want '$want'"
        FAIL=$((FAIL + 1))
    fi
}

check_contains() {
    local name="$1" haystack="$2" needle="$3"
    if echo "$haystack" | grep -q "$needle"; then
        echo "PASS: $name"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $name — '$needle' not found in output"
        FAIL=$((FAIL + 1))
    fi
}

# Export the extracted blocks so subshells can use them.
export RESOLVE_BLOCK FALLBACK_BLOCK

# --- Test 1: SUTANDO_MEMORY_DIR absolute path is honored ---
T1_DIR="/tmp/sutando-test-mem-$$"
mkdir -p "$T1_DIR"
got=$(
    unset SUTANDO_MEMORY_DIR SUTANDO_PRIVATE_DIR 2>/dev/null || true
    export SUTANDO_MEMORY_DIR="$T1_DIR"
    SCRIPT_PARENT="/some/checkout/sutando"
    eval "$RESOLVE_BLOCK"
    eval "$FALLBACK_BLOCK"
    echo "$MEMORY_DIR"
)
check "SUTANDO_MEMORY_DIR absolute path used" "$got" "$T1_DIR"
rm -rf "$T1_DIR"

# --- Test 2: SUTANDO_MEMORY_DIR tilde-expanded ---
got=$(
    unset SUTANDO_MEMORY_DIR SUTANDO_PRIVATE_DIR 2>/dev/null || true
    export SUTANDO_MEMORY_DIR="~/some-memory"
    SCRIPT_PARENT="/some/checkout/sutando"
    eval "$RESOLVE_BLOCK"
    eval "$FALLBACK_BLOCK"
    echo "$MEMORY_DIR"
)
check "SUTANDO_MEMORY_DIR tilde expanded" "$got" "$HOME/some-memory"

# --- Test 3: SUTANDO_MEMORY_DIR non-existent — find-fallback must NOT override ---
T3_TMP="$(mktemp -d)"
T3_REAL="$T3_TMP/.claude/projects/test/memory"
mkdir -p "$T3_REAL"
T3_OVERRIDE="/tmp/nonexistent-override-$$"
got=$(
    unset SUTANDO_MEMORY_DIR SUTANDO_PRIVATE_DIR 2>/dev/null || true
    export SUTANDO_MEMORY_DIR="$T3_OVERRIDE"
    SCRIPT_PARENT="/some/checkout/sutando"
    HOME="$T3_TMP"
    eval "$RESOLVE_BLOCK"
    eval "$FALLBACK_BLOCK"
    echo "$MEMORY_DIR"
)
check "find-fallback does NOT override SUTANDO_MEMORY_DIR" "$got" "$T3_OVERRIDE"
rm -rf "$T3_TMP"

# --- Test 4: SUTANDO_PRIVATE_DIR used when SUTANDO_MEMORY_DIR unset ---
T4_DIR="/tmp/sutando-private-test-$$"
got=$(
    unset SUTANDO_MEMORY_DIR SUTANDO_PRIVATE_DIR 2>/dev/null || true
    export SUTANDO_PRIVATE_DIR="$T4_DIR"
    SCRIPT_PARENT="/some/checkout"
    eval "$RESOLVE_BLOCK"
    eval "$FALLBACK_BLOCK"
    echo "$MEMORY_DIR"
)
check "SUTANDO_PRIVATE_DIR used when MEMORY_DIR unset" "$got" "$T4_DIR"

# --- Test 5: SUTANDO_PRIVATE_DIR emits deprecation warning to stderr ---
stderr_out=$(
    unset SUTANDO_MEMORY_DIR SUTANDO_PRIVATE_DIR 2>/dev/null || true
    export SUTANDO_PRIVATE_DIR="/tmp/private-dep-test"
    SCRIPT_PARENT="/some/checkout"
    eval "$RESOLVE_BLOCK" 2>&1 1>/dev/null
)
check_contains "SUTANDO_PRIVATE_DIR deprecation warning emitted" "$stderr_out" "deprecated"

# --- Test 6: SUTANDO_MEMORY_DIR takes precedence over SUTANDO_PRIVATE_DIR ---
got=$(
    unset SUTANDO_MEMORY_DIR SUTANDO_PRIVATE_DIR 2>/dev/null || true
    export SUTANDO_MEMORY_DIR="/tmp/explicit-mem"
    export SUTANDO_PRIVATE_DIR="/tmp/legacy-mem"
    SCRIPT_PARENT="/some/checkout"
    eval "$RESOLVE_BLOCK"
    eval "$FALLBACK_BLOCK"
    echo "$MEMORY_DIR"
)
check "SUTANDO_MEMORY_DIR wins over SUTANDO_PRIVATE_DIR" "$got" "/tmp/explicit-mem"

# --- Test 7: find-fallback runs when neither override set and dir missing ---
T7_TMP="$(mktemp -d)"
T7_MEM="$T7_TMP/.claude/projects/autodetected/memory"
mkdir -p "$T7_MEM"
got=$(
    unset SUTANDO_MEMORY_DIR SUTANDO_PRIVATE_DIR 2>/dev/null || true
    SCRIPT_PARENT="/nonexistent/checkout"
    HOME="$T7_TMP"
    eval "$RESOLVE_BLOCK"
    eval "$FALLBACK_BLOCK"
    echo "$MEMORY_DIR"
)
check "find-fallback runs when no override set" "$got" "$T7_MEM"
rm -rf "$T7_TMP"

# --- Test 8: find-fallback does NOT override SUTANDO_PRIVATE_DIR ---
T8_TMP="$(mktemp -d)"
T8_REAL="$T8_TMP/.claude/projects/test/memory"
mkdir -p "$T8_REAL"
T8_OVERRIDE="/tmp/nonexistent-private-$$"
got=$(
    unset SUTANDO_MEMORY_DIR SUTANDO_PRIVATE_DIR 2>/dev/null || true
    export SUTANDO_PRIVATE_DIR="$T8_OVERRIDE"
    SCRIPT_PARENT="/some/checkout"
    HOME="$T8_TMP"
    eval "$RESOLVE_BLOCK"
    eval "$FALLBACK_BLOCK"
    echo "$MEMORY_DIR"
)
check "find-fallback does NOT override SUTANDO_PRIVATE_DIR" "$got" "$T8_OVERRIDE"
rm -rf "$T8_TMP"

# --- Structural: SUTANDO_PRIVATE_DIR branch present in script ---
if grep -q 'SUTANDO_PRIVATE_DIR' "$SCRIPT"; then
    echo "PASS: SUTANDO_PRIVATE_DIR branch present in script"
    PASS=$((PASS + 1))
else
    echo "FAIL: SUTANDO_PRIVATE_DIR branch missing from script"
    FAIL=$((FAIL + 1))
fi

# --- Structural: find-fallback guard checks both override vars ---
GUARD_PRESENT="$(grep 'SUTANDO_PRIVATE_DIR' "$SCRIPT" | grep 'SUTANDO_MEMORY_DIR')"
if [ -n "$GUARD_PRESENT" ]; then
    echo "PASS: find-fallback guard checks both SUTANDO_MEMORY_DIR and SUTANDO_PRIVATE_DIR"
    PASS=$((PASS + 1))
else
    echo "FAIL: find-fallback guard does not check both override vars"
    FAIL=$((FAIL + 1))
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo "━━━ sync-memory-memory-dir tests: $PASS passed / 0 failed ━━━"
    exit 0
else
    echo "━━━ FAILED: $FAIL failed / $PASS passed ━━━"
    exit 1
fi
