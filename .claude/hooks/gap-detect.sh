#!/bin/bash
# =============================================================================
# Gap Detection Hook
# =============================================================================
# Scans project directory for missing documentation and contracts.
# Run after code generation phases to catch gaps early.
#
# Usage: bash gap-detect.sh <project_path>
# Example: bash gap-detect.sh E:/AI/projects/BalloonFlow
# =============================================================================

PROJECT_DIR="${1:-.}"
GAPS=()
WARNINGS=()

if [ ! -d "$PROJECT_DIR" ]; then
    echo "[gap-detect] Project directory not found: $PROJECT_DIR"
    exit 1
fi

PROJECT_NAME=$(basename "$PROJECT_DIR")

# ---------------------------------------------------------------------------
# 1. ICS Contract Files
# ---------------------------------------------------------------------------
if [ -d "$PROJECT_DIR/output" ]; then
    CS_COUNT=$(find "$PROJECT_DIR/output" -name "*.cs" -not -path "*/Editor/*" 2>/dev/null | wc -l)

    if [ "$CS_COUNT" -gt 0 ]; then
        [ ! -f "$PROJECT_DIR/_ARCHITECTURE.md" ] && GAPS+=("Missing _ARCHITECTURE.md (required when output/ has $CS_COUNT .cs files)")
        [ ! -f "$PROJECT_DIR/_CONTRACTS.yaml" ] && GAPS+=("Missing _CONTRACTS.yaml (required for ICS integration validation)")
        [ ! -f "$PROJECT_DIR/_ASSET_MANIFEST.yaml" ] && GAPS+=("Missing _ASSET_MANIFEST.yaml (required for prefab/scene tracking)")
    fi
fi

# ---------------------------------------------------------------------------
# 2. Design Workflow Completeness
# ---------------------------------------------------------------------------
DW="$PROJECT_DIR/design_workflow"
if [ -d "$DW" ]; then
    # Layer 1
    [ ! -f "$DW/layer1/game_design.yaml" ] && [ -d "$DW/layer1" ] && \
        GAPS+=("Missing layer1/game_design.yaml")

    # Layer 2
    if [ -d "$DW/layer2" ]; then
        [ ! -f "$DW/layer2/system_spec.yaml" ] && GAPS+=("Missing layer2/system_spec.yaml")
        [ ! -f "$DW/layer2/build_order.yaml" ] && GAPS+=("Missing layer2/build_order.yaml")
    fi

    # Layer 3 coverage check
    if [ -d "$DW/layer3/nodes" ]; then
        NODE_COUNT=$(find "$DW/layer3/nodes" -name "*.yaml" 2>/dev/null | wc -l)
        if [ -f "$DW/layer2/build_order.yaml" ]; then
            # Count systems in build_order
            SYSTEM_COUNT=$(grep -cP '^\s+-\s+\w+' "$DW/layer2/build_order.yaml" 2>/dev/null || echo 0)
            if [ "$NODE_COUNT" -lt "$SYSTEM_COUNT" ]; then
                WARNINGS+=("Layer 3 coverage: $NODE_COUNT nodes / $SYSTEM_COUNT systems ($(( NODE_COUNT * 100 / (SYSTEM_COUNT > 0 ? SYSTEM_COUNT : 1) ))%)")
            fi
        fi
    fi

    # Docs directory (dual output)
    if [ ! -d "$PROJECT_DIR/docs" ]; then
        WARNINGS+=("No docs/ directory. YAML-only output detected. Run generate_docs.py for dual output.")
    fi
fi

# ---------------------------------------------------------------------------
# 3. Editor Script Completeness
# ---------------------------------------------------------------------------
if [ -d "$PROJECT_DIR/output" ] && [ -d "$PROJECT_DIR/output/Editor" ]; then
    EDITOR_FILES=$(ls "$PROJECT_DIR/output/Editor/"*.cs 2>/dev/null)
    HAS_SCENE_BUILDER=false
    HAS_PREFAB_BUILDER=false

    for f in $EDITOR_FILES; do
        grep -q "SceneBuilder" "$f" 2>/dev/null && HAS_SCENE_BUILDER=true
        grep -q "PrefabBuilder" "$f" 2>/dev/null && HAS_PREFAB_BUILDER=true
    done

    [ "$HAS_SCENE_BUILDER" = false ] && GAPS+=("Missing SceneBuilder in output/Editor/")
    [ "$HAS_PREFAB_BUILDER" = false ] && GAPS+=("Missing PrefabBuilder in output/Editor/")
elif [ -d "$PROJECT_DIR/output" ]; then
    CS_COUNT=$(find "$PROJECT_DIR/output" -maxdepth 1 -name "*.cs" 2>/dev/null | wc -l)
    if [ "$CS_COUNT" -gt 0 ]; then
        GAPS+=("No output/Editor/ directory. SceneBuilder + PrefabBuilder required.")
    fi
fi

# ---------------------------------------------------------------------------
# 4. Feedback Directory
# ---------------------------------------------------------------------------
if [ -d "$PROJECT_DIR/output" ] || [ -d "$DW" ]; then
    [ ! -d "$PROJECT_DIR/feedback" ] && WARNINGS+=("No feedback/ directory. Validation reports will have no destination.")
fi

# ---------------------------------------------------------------------------
# 5. Playable Completeness
# ---------------------------------------------------------------------------
if [ -f "$PROJECT_DIR/output/playable.html" ]; then
    # CTA check
    if ! grep -qP '(install|download|play.now|cta)' "$PROJECT_DIR/output/playable.html" 2>/dev/null; then
        GAPS+=("Playable HTML missing CTA (Install/Download button)")
    fi
fi

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
echo "=== Gap Detection: $PROJECT_NAME ==="

if [ ${#GAPS[@]} -eq 0 ] && [ ${#WARNINGS[@]} -eq 0 ]; then
    echo "  No gaps detected."
    exit 0
fi

if [ ${#GAPS[@]} -gt 0 ]; then
    echo "  GAPS (${#GAPS[@]}):"
    for g in "${GAPS[@]}"; do
        echo "    [GAP] $g"
    done
fi

if [ ${#WARNINGS[@]} -gt 0 ]; then
    echo "  WARNINGS (${#WARNINGS[@]}):"
    for w in "${WARNINGS[@]}"; do
        echo "    [WARN] $w"
    done
fi

exit 0
