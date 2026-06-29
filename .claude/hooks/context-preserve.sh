#!/bin/bash
# =============================================================================
# Context Preservation Hook
# =============================================================================
# Saves critical context before conversation compression.
# Called on Notification events to preserve key state.
#
# Saves to: E:\AI\History\{project}\context_snapshot.json
# =============================================================================

PROJECT_DIR="${1:-E:/AI}"
SNAPSHOT_DIR="E:/AI/History"
TIMESTAMP=$(date -Iseconds 2>/dev/null || date +%Y-%m-%dT%H:%M:%S)

mkdir -p "$SNAPSHOT_DIR"

# ---------------------------------------------------------------------------
# 1. Gather current git state
# ---------------------------------------------------------------------------
BRANCH=$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
LAST_COMMIT=$(git -C "$PROJECT_DIR" log -1 --pretty="%h %s" 2>/dev/null || echo "none")
DIRTY_COUNT=$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null | wc -l)

# ---------------------------------------------------------------------------
# 2. Find active project (most recently modified output/ or design_workflow/)
# ---------------------------------------------------------------------------
ACTIVE_PROJECT="none"
LATEST_TIME=0

for proj_dir in E:/AI/projects/*/; do
    if [ -d "$proj_dir" ]; then
        # Find most recently modified file
        NEWEST=$(find "$proj_dir" -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1)
        if [ -n "$NEWEST" ] && [ "${NEWEST%.*}" -gt "$LATEST_TIME" ] 2>/dev/null; then
            LATEST_TIME="${NEWEST%.*}"
            ACTIVE_PROJECT=$(basename "$proj_dir")
        fi
    fi
done

# ---------------------------------------------------------------------------
# 3. Gather ICS contract state for active project
# ---------------------------------------------------------------------------
CONTRACT_STATUS="none"
if [ "$ACTIVE_PROJECT" != "none" ]; then
    PROJ_PATH="E:/AI/projects/$ACTIVE_PROJECT"
    if [ -f "$PROJ_PATH/_CONTRACTS.yaml" ]; then
        EVENT_COUNT=$(grep -c "^  - name:" "$PROJ_PATH/_CONTRACTS.yaml" 2>/dev/null || echo 0)
        POOL_COUNT=$(grep -c "^  - key:" "$PROJ_PATH/_CONTRACTS.yaml" 2>/dev/null || echo 0)
        SF_COUNT=$(grep -c "^  - class:" "$PROJ_PATH/_CONTRACTS.yaml" 2>/dev/null || echo 0)
        CONTRACT_STATUS="events:$EVENT_COUNT,pools:$POOL_COUNT,fields:$SF_COUNT"
    fi
fi

# ---------------------------------------------------------------------------
# 4. Count generated artifacts
# ---------------------------------------------------------------------------
CS_FILES=0
YAML_FILES=0
L3_NODES=0

if [ "$ACTIVE_PROJECT" != "none" ]; then
    PROJ_PATH="E:/AI/projects/$ACTIVE_PROJECT"
    CS_FILES=$(find "$PROJ_PATH/output" -name "*.cs" 2>/dev/null | wc -l)
    YAML_FILES=$(find "$PROJ_PATH/design_workflow" -name "*.yaml" 2>/dev/null | wc -l)
    L3_NODES=$(find "$PROJ_PATH/design_workflow/layer3/nodes" -name "*.yaml" 2>/dev/null | wc -l)
fi

# ---------------------------------------------------------------------------
# 5. Write snapshot
# ---------------------------------------------------------------------------
SNAPSHOT_FILE="$SNAPSHOT_DIR/context_snapshot.json"

if command -v node &>/dev/null; then
    node -e "
    const snapshot = {
        timestamp: '$TIMESTAMP',
        git: { branch: '$BRANCH', lastCommit: '$LAST_COMMIT', dirtyFiles: $DIRTY_COUNT },
        activeProject: '$ACTIVE_PROJECT',
        contracts: '$CONTRACT_STATUS',
        artifacts: { cs: $CS_FILES, yaml: $YAML_FILES, l3Nodes: $L3_NODES },
        note: 'Auto-saved on context compression'
    };
    require('fs').writeFileSync('$SNAPSHOT_FILE', JSON.stringify(snapshot, null, 2));
    " 2>/dev/null
else
    cat > "$SNAPSHOT_FILE" <<EOF
{
  "timestamp": "$TIMESTAMP",
  "git": { "branch": "$BRANCH", "lastCommit": "$LAST_COMMIT", "dirtyFiles": $DIRTY_COUNT },
  "activeProject": "$ACTIVE_PROJECT",
  "contracts": "$CONTRACT_STATUS",
  "artifacts": { "cs": $CS_FILES, "yaml": $YAML_FILES, "l3Nodes": $L3_NODES }
}
EOF
fi

echo "[context] Snapshot saved: $ACTIVE_PROJECT (${CS_FILES}cs, ${YAML_FILES}yaml)"
