#!/bin/bash
# =============================================================================
# Post-Commit Audit Trail Hook
# =============================================================================
# Logs every commit with agent/file metadata for traceability.
# Output: E:\AI\History\audit_log.jsonl
# =============================================================================

AUDIT_DIR="E:/AI/History"
AUDIT_FILE="$AUDIT_DIR/audit_log.jsonl"

mkdir -p "$AUDIT_DIR"

# Get commit info
COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null)
COMMIT_MSG=$(git log -1 --pretty=%s 2>/dev/null)
COMMIT_AUTHOR=$(git log -1 --pretty=%an 2>/dev/null)
COMMIT_DATE=$(git log -1 --pretty=%aI 2>/dev/null)
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

# Get changed files in this commit
CHANGED_FILES=$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null | tr '\n' ',' | sed 's/,$//')

# Detect agent from commit message (Co-Authored-By pattern)
AGENT="unknown"
if echo "$COMMIT_MSG" | grep -qi "Main.Coder\|main-coder"; then
    AGENT="main-coder"
elif echo "$COMMIT_MSG" | grep -qi "Sub.Coder\|sub-coder"; then
    AGENT="sub-coder"
elif echo "$COMMIT_MSG" | grep -qi "Designer\|designer"; then
    AGENT="designer"
elif echo "$COMMIT_MSG" | grep -qi "Validator\|validator"; then
    AGENT="validator"
elif echo "$COMMIT_MSG" | grep -qi "Lead\|lead"; then
    AGENT="lead"
elif echo "$COMMIT_MSG" | grep -qi "Playable\|playable"; then
    AGENT="playable-coder"
elif echo "$COMMIT_MSG" | grep -qi "Claude"; then
    AGENT="claude-direct"
fi

# Count files by category
CS_COUNT=$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null | grep -c '\.cs$' || echo 0)
YAML_COUNT=$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null | grep -c '\.yaml$' || echo 0)
MD_COUNT=$(git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null | grep -c '\.md$' || echo 0)

# Write audit entry
if command -v node &>/dev/null; then
    node -e "
    const entry = {
        timestamp: '$COMMIT_DATE',
        commit: '$COMMIT_HASH',
        branch: '$BRANCH',
        agent: '$AGENT',
        message: $(echo "$COMMIT_MSG" | node -e "process.stdout.write(JSON.stringify(require('fs').readFileSync('/dev/stdin','utf8').trim()))"),
        files: '$CHANGED_FILES'.split(',').filter(Boolean),
        stats: { cs: $CS_COUNT, yaml: $YAML_COUNT, md: $MD_COUNT }
    };
    require('fs').appendFileSync('$AUDIT_FILE', JSON.stringify(entry) + '\n');
    " 2>/dev/null
else
    echo "{\"timestamp\":\"$COMMIT_DATE\",\"commit\":\"$COMMIT_HASH\",\"branch\":\"$BRANCH\",\"agent\":\"$AGENT\",\"message\":\"$COMMIT_MSG\",\"files\":\"$CHANGED_FILES\"}" >> "$AUDIT_FILE"
fi

echo "[audit] Logged commit $COMMIT_HASH by $AGENT"
