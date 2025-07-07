#!/usr/bin/env bash

set -euo pipefail

REMOTE="origin"

echo "🔍 Checking current HEAD status..."

# Check if inside a git repo
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
  echo "❌ Error: This is not a Git repository."
  exit 1
fi

CURRENT_COMMIT=$(git rev-parse HEAD)
CURRENT_TAG=$(git describe --tags --exact-match "$CURRENT_COMMIT" 2>/dev/null || true)

if [[ -z "$CURRENT_TAG" ]]; then
  echo "⚠️  No tag currently checked out."
  echo "➡️  Finding highest local tag..."

  LATEST_LOCAL_TAG=$(git tag --list 'v*' --sort=-v:refname | head -n1)

  if [[ -z "$LATEST_LOCAL_TAG" ]]; then
    echo "❌ Error: No local tags matching pattern 'v*' found."
    exit 1
  fi

  echo "✅ Checking out latest local tag: $LATEST_LOCAL_TAG"
  git checkout "$LATEST_LOCAL_TAG"
  CURRENT_TAG="$LATEST_LOCAL_TAG"
else
  echo "✅ Currently checked out tag: $CURRENT_TAG"
fi

echo
echo "⬇️  Fetching remote tags..."
git fetch --tags "$REMOTE"

echo
echo "🔎 Looking for latest remote tag..."
LATEST_REMOTE_TAG=$(git tag --list 'v*' --sort=-v:refname | head -n1)

if [[ -z "$LATEST_REMOTE_TAG" ]]; then
  echo "❌ Error: No remote tags matching 'v*' found."
  exit 1
fi

echo "🗂️  Latest available tag: $LATEST_REMOTE_TAG"

if [[ "$CURRENT_TAG" == "$LATEST_REMOTE_TAG" ]]; then
  echo "✅ You are already on the latest tag ($CURRENT_TAG). No update needed."
  exit 0
fi

echo
echo "🚀 Newer tag detected: $LATEST_REMOTE_TAG"
echo
echo "🛑 Stopping Docker Compose..."
docker compose down || {
  echo "⚠️  Warning: 'docker compose down' failed, continuing..."
}

echo
echo "🔄 Checking out new tag..."
git checkout "$LATEST_REMOTE_TAG"

echo
echo "⬇️  Pulling latest changes from remote..."
git pull "$REMOTE" "$LATEST_REMOTE_TAG"

echo
echo "🏗️  Building and starting Docker Compose..."
docker compose up -d --build

echo
echo "✅ Update complete! Now on tag: $LATEST_REMOTE_TAG"