#!/usr/bin/env bash
set -euo pipefail

# Smoke tests for Azure DevOps CLI

echo "=== Azure DevOps CLI Smoke Tests ===" >&2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASH_CLI="${SCRIPT_DIR}/scripts/bash/ado-ticket.sh"
TESTS_PASSED=0
TESTS_FAILED=0

# Make scripts executable
chmod +x "${BASH_CLI}" || true

# Helper function to run test
run_test() {
  local test_num="$1"
  local test_name="$2"
  local test_cmd="$3"
  local expect_pass="$4"

  if bash -c "${test_cmd}" >/dev/null 2>&1; then
    if [[ "${expect_pass}" == "true" ]]; then
      echo "✓ Test ${test_num} passed: ${test_name}" >&2
      ((TESTS_PASSED++))
    else
      echo "✗ Test ${test_num} failed: ${test_name} (expected to fail)" >&2
      ((TESTS_FAILED++))
    fi
  else
    if [[ "${expect_pass}" == "false" ]]; then
      echo "✓ Test ${test_num} passed: ${test_name}" >&2
      ((TESTS_PASSED++))
    else
      echo "✗ Test ${test_num} failed: ${test_name}" >&2
      ((TESTS_FAILED++))
    fi
  fi
}

# Test 1: Check usage message includes 'init'
echo "Test 1: Checking usage message..." >&2
OUTPUT=$("${BASH_CLI}" 2>&1 || true)
if echo "${OUTPUT}" | grep -q "init"; then
  echo "✓ Test 1 passed: Usage message includes init" >&2
  ((TESTS_PASSED++))
else
  echo "✗ Test 1 failed: Usage message missing init" >&2
  ((TESTS_FAILED++))
fi

# Test 2: Verify config requirement for list action
echo "Test 2: Checking config requirement..." >&2
# Remove config if it exists for this test
CONFIG_FILE="${SCRIPT_DIR}/.ado-cli-config"
CONFIG_BACKUP=""
if [[ -f "${CONFIG_FILE}" ]]; then
  CONFIG_BACKUP=$(mktemp)
  mv "${CONFIG_FILE}" "${CONFIG_BACKUP}"
fi

OUTPUT=$("${BASH_CLI}" list 2>&1 || true)
if echo "${OUTPUT}" | grep -q "Configuration not found"; then
  echo "✓ Test 2 passed: Config requirement enforced" >&2
  ((TESTS_PASSED++))
else
  echo "✗ Test 2 failed: Should require config before list" >&2
  ((TESTS_FAILED++))
fi

# Restore config
if [[ -n "${CONFIG_BACKUP}" ]] && [[ -f "${CONFIG_BACKUP}" ]]; then
  mv "${CONFIG_BACKUP}" "${CONFIG_FILE}"
fi

# Test 3: Verify config file structure
echo "Test 3: Checking config file structure..." >&2
if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "⊘ Test 3 skipped: No config file present (run init first)" >&2
else
  if grep -q "^ORG=" "${CONFIG_FILE}" && grep -q "^PROJECT=" "${CONFIG_FILE}"; then
    echo "✓ Test 3 passed: Config file has correct structure" >&2
    ((TESTS_PASSED++))
  else
    echo "✗ Test 3 failed: Config file missing ORG or PROJECT" >&2
    ((TESTS_FAILED++))
  fi
fi

# Test 4: Verify scripts are executable
echo "Test 4: Checking script permissions..." >&2
if [[ -x "${BASH_CLI}" ]]; then
  echo "✓ Test 4 passed: Bash script is executable" >&2
  ((TESTS_PASSED++))
else
  echo "✗ Test 4 failed: Bash script is not executable" >&2
  ((TESTS_FAILED++))
fi

# Summary
echo "" >&2
echo "=== Test Summary ===" >&2
echo "Passed: ${TESTS_PASSED}" >&2
echo "Failed: ${TESTS_FAILED}" >&2

if [[ ${TESTS_FAILED} -gt 0 ]]; then
  exit 1
fi

exit 0
