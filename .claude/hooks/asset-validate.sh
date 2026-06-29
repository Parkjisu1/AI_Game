#!/bin/bash
# =============================================================================
# Asset Validation Hook
# =============================================================================
# Validates asset files on save/stage:
#   1. Naming conventions (PascalCase for prefabs, lowercase for resources)
#   2. Path correctness (_ASSET_MANIFEST.yaml cross-check)
#   3. Editor scripts in correct directory
#   4. Playable HTML size limits
# =============================================================================

ERRORS=()
WARNINGS=()

# Target: file path passed as argument or from staged files
TARGET_FILES="${1:-$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null)}"

if [ -z "$TARGET_FILES" ]; then
    exit 0
fi

for file in $TARGET_FILES; do
    basename=$(basename "$file")
    dirname=$(dirname "$file")

    # ---------------------------------------------------------------------------
    # 1. C# Naming: PascalCase required
    # ---------------------------------------------------------------------------
    if [[ "$file" == *.cs ]]; then
        name="${basename%.cs}"
        if [[ ! "$name" =~ ^[A-Z][a-zA-Z0-9]*$ ]]; then
            WARNINGS+=("$file: C# filename should be PascalCase (got '$name')")
        fi
    fi

    # ---------------------------------------------------------------------------
    # 2. Editor scripts must be in Editor/ directory
    # ---------------------------------------------------------------------------
    if [[ "$file" == *.cs ]]; then
        if grep -qP '\[InitializeOnLoad\]|EditorWindow|EditorSceneManager|PrefabUtility' "$file" 2>/dev/null; then
            if [[ "$dirname" != *Editor* ]]; then
                ERRORS+=("$file: Editor script detected outside Editor/ directory. Move to output/Editor/")
            fi
        fi
    fi

    # ---------------------------------------------------------------------------
    # 3. Playable HTML size check
    # ---------------------------------------------------------------------------
    if [[ "$file" == *playable*.html ]] || [[ "$file" == *playable.html ]]; then
        SIZE=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null || wc -c < "$file")
        SIZE_MB=$((SIZE / 1048576))

        if [ "$SIZE" -gt 5242880 ]; then
            ERRORS+=("$file: Playable HTML exceeds 5MB limit (${SIZE_MB}MB). Max for most networks is 5MB.")
        elif [ "$SIZE" -gt 2097152 ]; then
            WARNINGS+=("$file: Playable HTML exceeds 2MB (${SIZE_MB}MB). Will fail Facebook/Meta limit.")
        fi

        # Check for external requests
        if grep -qP '(https?://|fetch\(|XMLHttpRequest|import\s+.*from\s+["\x27]http)' "$file" 2>/dev/null; then
            ERRORS+=("$file: External HTTP requests detected. Playable ads must be fully self-contained.")
        fi
    fi

    # ---------------------------------------------------------------------------
    # 4. YAML schema basic check
    # ---------------------------------------------------------------------------
    if [[ "$file" == *design_workflow/*.yaml ]] || [[ "$file" == *design_workflow/**/*.yaml ]]; then
        # Check for tab characters (YAML forbids tabs)
        if grep -Pn '\t' "$file" 2>/dev/null | head -1; then
            ERRORS+=("$file: Tab characters found in YAML. Use spaces only.")
        fi
    fi

    # ---------------------------------------------------------------------------
    # 5. _CONTRACTS.yaml cross-check (if manifest exists)
    # ---------------------------------------------------------------------------
    if [[ "$file" == *output/*.cs ]] && [[ "$file" != *Editor/* ]]; then
        PROJECT_DIR=$(echo "$file" | grep -oP 'projects/[^/]+' 2>/dev/null)
        if [ -n "$PROJECT_DIR" ]; then
            MANIFEST="E:/AI/$PROJECT_DIR/_ASSET_MANIFEST.yaml"
            if [ -f "$MANIFEST" ]; then
                # Check if file is referenced in manifest
                CS_NAME="${basename%.cs}"
                if ! grep -q "$CS_NAME" "$MANIFEST" 2>/dev/null; then
                    WARNINGS+=("$file: Not referenced in _ASSET_MANIFEST.yaml. Verify ICS registration.")
                fi
            fi
        fi
    fi
done

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
if [ ${#WARNINGS[@]} -gt 0 ]; then
    echo "=== ASSET WARNINGS ==="
    for w in "${WARNINGS[@]}"; do
        echo "  [WARN] $w"
    done
fi

if [ ${#ERRORS[@]} -gt 0 ]; then
    echo "=== ASSET ERRORS ==="
    for e in "${ERRORS[@]}"; do
        echo "  [ERROR] $e"
    done
    exit 1
fi

exit 0
