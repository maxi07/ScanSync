#!/usr/bin/env bash

set -euo pipefail

REMOTE="origin"
TAG_PATTERN="v*"

echo "🔍 Checking if we're in a Git repository..."
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
  echo "❌ Error: This is not a Git repository."
  exit 1
fi

echo
echo "⬇️  Fetching all remote tags..."
git fetch --tags "$REMOTE"

echo
echo "🔎 Determining the latest available tag..."
LATEST_TAG=$(git tag --list "$TAG_PATTERN" --sort=-v:refname | head -n 1)

if [[ -z "$LATEST_TAG" ]]; then
  echo "❌ Error: No tags found matching pattern '$TAG_PATTERN'."
  exit 1
fi

echo "✅ Latest available tag is: $LATEST_TAG"

echo
echo "🔍 Checking current HEAD status..."
CURRENT_COMMIT=$(git rev-parse HEAD)
CURRENT_TAG=$(git describe --tags --exact-match "$CURRENT_COMMIT" 2>/dev/null || true)

if [[ -z "$CURRENT_TAG" ]]; then
  echo "⚠️  Currently not on a tag (detached HEAD or branch)."
else
  echo "✅ Currently checked out tag: $CURRENT_TAG"
fi

# Always make sure local tag matches remote
echo
echo "🧹 Deleting local tag (if exists) to avoid mismatch..."
if git show-ref --tags "$LATEST_TAG" &>/dev/null; then
  git tag -d "$LATEST_TAG" || true
fi

echo "⬇️  Re-fetching the latest tag to ensure it's up to date..."
git fetch --tags "$REMOTE"

# Get latest tag again after re-fetch
LATEST_TAG=$(git tag --list "$TAG_PATTERN" --sort=-v:refname | head -n 1)
if [[ -z "$LATEST_TAG" ]]; then
  echo "❌ Error: No tags found after re-fetch. Exiting."
  exit 1
fi

echo "✅ Confirmed latest remote tag: $LATEST_TAG"

# Check if we need to update
if [[ "$CURRENT_TAG" == "$LATEST_TAG" ]]; then
  echo
  echo "✅ You are already on the latest tag ($CURRENT_TAG). No update needed."
  exit 0
fi

echo
echo "🚀 Newer tag detected: $LATEST_TAG"
echo
echo "🛑 Stopping Docker Compose..."
if ! docker compose down; then
  echo "⚠️  Warning: 'docker compose down' failed or containers were already stopped."
fi

echo
echo "🔄 Checking out latest tag: $LATEST_TAG"
git checkout "$LATEST_TAG"

echo
echo "⬇️  Pulling latest changes for tag (if any)..."
if git ls-remote --tags "$REMOTE" | grep "refs/tags/$LATEST_TAG" &>/dev/null; then
  git fetch "$REMOTE" tag "$LATEST_TAG" --force
else
  echo "⚠️  Warning: Remote does not have tag $LATEST_TAG anymore."
fi

echo
echo "🏗️  Building and starting Docker Compose..."
docker compose up -d --build

echo
echo "✅ Update complete! Now on tag: $LATEST_TAG"
