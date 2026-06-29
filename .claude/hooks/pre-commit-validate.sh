#!/bin/bash
# =============================================================================
# Pre-Commit Validation Hook
# =============================================================================
# Checks staged files for common issues before committing:
#   1. Hardcoded values (magic numbers, hardcoded paths)
#   2. TODO format enforcement (TODO(owner): description)
#   3. JSON validity
#   4. Design doc required sections
#   5. Unity forbidden patterns in runtime code
#
# Exit 0 = pass, Exit 1 = block commit
# =============================================================================

ERRORS=()
WARNINGS=()

# Get staged files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null)

if [ -z "$STAGED_FILES" ]; then
    exit 0
fi

# ---------------------------------------------------------------------------
# 1. Hardcoded Values Detection (C# runtime files only)
# ---------------------------------------------------------------------------
for file in $STAGED_FILES; do
    if [[ "$file" == *.cs ]] && [[ "$file" != *Editor/* ]] && [[ "$file" != *Test/* ]]; then
        # Magic numbers in gameplay logic (skip enums, consts, switch cases)
        if grep -nP '(?<!const\s\w+\s=\s)(?<!\[)\b[0-9]{3,}\b(?!f?\s*[;,\)])' "$file" 2>/dev/null | \
           grep -vP '(enum|const|case|0x|#if|#region|SerializeField|Range\(|\.Length|\.Count|switch)' | head -3; then
            WARNINGS+=("$file: Possible hardcoded magic numbers detected. Consider using const/SerializeField.")
        fi

        # Hardcoded file paths
        if grep -nP '"(Assets/|Resources/|C:\\|D:\\|E:\\)[^"]*"' "$file" 2>/dev/null | head -3; then
            WARNINGS+=("$file: Hardcoded file paths detected. Use const or config.")
        fi
    fi
done

# ---------------------------------------------------------------------------
# 2. TODO Format Enforcement
# ---------------------------------------------------------------------------
for file in $STAGED_FILES; do
    if [[ "$file" == *.cs ]] || [[ "$file" == *.yaml ]] || [[ "$file" == *.md ]]; then
        # Check for bare TODO without owner
        BAD_TODOS=$(grep -nP '//\s*TODO[^(]' "$file" 2>/dev/null | head -5)
        if [ -n "$BAD_TODOS" ]; then
            WARNINGS+=("$file: TODO without owner. Use format: TODO(owner): description")
        fi
    fi
done

# ---------------------------------------------------------------------------
# 3. JSON Validity
# ---------------------------------------------------------------------------
for file in $STAGED_FILES; do
    if [[ "$file" == *.json ]]; then
        if command -v node &>/dev/null; then
            if ! node -e "JSON.parse(require('fs').readFileSync('$file','utf8'))" 2>/dev/null; then
                ERRORS+=("$file: Invalid JSON syntax")
            fi
        elif command -v python &>/dev/null; then
            if ! python -c "import json; json.load(open('$file'))" 2>/dev/null; then
                ERRORS+=("$file: Invalid JSON syntax")
            fi
        fi
    fi
done

# ---------------------------------------------------------------------------
# 4. Design Doc Required Sections
# ---------------------------------------------------------------------------
for file in $STAGED_FILES; do
    if [[ "$file" == *design_workflow/*.yaml ]] || [[ "$file" == *design_workflow/**/*.yaml ]]; then
        # Layer 1 must have: game_name, genre, platform, core_loop
        if [[ "$file" == *game_design.yaml ]]; then
            for section in "game_name" "genre" "platform" "core_loop"; do
                if ! grep -q "$section:" "$file" 2>/dev/null; then
                    ERRORS+=("$file: Missing required section '$section' in game design")
                fi
            done
        fi

        # Layer 3 nodes must have: nodeId, contracts, logicFlow
        if [[ "$file" == *nodes/*.yaml ]]; then
            for section in "nodeId" "contracts" "logicFlow"; do
                if ! grep -q "$section:" "$file" 2>/dev/null; then
                    ERRORS+=("$file: Missing required section '$section' in L3 node")
                fi
            done
        fi
    fi
done

# ---------------------------------------------------------------------------
# 5. Unity Runtime Forbidden Patterns
# ---------------------------------------------------------------------------
for file in $STAGED_FILES; do
    if [[ "$file" == *output/*.cs ]] && [[ "$file" != *output/Editor/* ]]; then
        # new GameObject() in runtime
        if grep -nP 'new\s+GameObject\s*\(' "$file" 2>/dev/null; then
            ERRORS+=("$file: 'new GameObject()' forbidden in runtime code. Use Resources.Load/ObjectPool.")
        fi

        # Find/FindObjectOfType in runtime
        if grep -nP '\.(Find|FindObjectOfType|FindWithTag|FindGameObjectsWithTag)\s*[<(]' "$file" 2>/dev/null; then
            ERRORS+=("$file: Find() methods forbidden in runtime. Use [SerializeField] or cached references.")
        fi

        # SDK using without #if guard
        if grep -nP '^using\s+(Firebase|Google\.MobileAds|UnityEngine\.Purchasing)' "$file" 2>/dev/null; then
            ERRORS+=("$file: SDK using statement must be inside #if conditional compilation block.")
        fi
    fi
done

# ---------------------------------------------------------------------------
# Output Results
# ---------------------------------------------------------------------------
if [ ${#WARNINGS[@]} -gt 0 ]; then
    echo "=== WARNINGS ==="
    for w in "${WARNINGS[@]}"; do
        echo "  [WARN] $w"
    done
fi

if [ ${#ERRORS[@]} -gt 0 ]; then
    echo "=== ERRORS (commit blocked) ==="
    for e in "${ERRORS[@]}"; do
        echo "  [ERROR] $e"
    done
    exit 1
fi

echo "[pre-commit] All checks passed."
exit 0
