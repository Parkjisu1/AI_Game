@echo off
chcp 65001 > nul
cd /d C:\projects\balloonflow

echo === Current branch ===
git branch --show-current
echo.

echo === Working tree status ===
git status --short
echo.

echo === All local branches ===
git branch -vv
echo.

echo === All remote branches ===
git branch -r
echo.

echo === Last 10 commits across all branches ===
git log --oneline --all -n 10 --decorate
echo.

echo === Unpushed hermes branches ===
for /f "tokens=*" %%b in ('git branch --list "hermes/*" 2^>nul') do @(
    set branch=%%b
    echo Branch: %%b
    git log origin/main..%%b --oneline 2>nul | head -5
    echo.
)

echo === Open PRs ===
gh pr list --state open 2>&1

echo === Git config (user) ===
git config --get user.name
git config --get user.email
