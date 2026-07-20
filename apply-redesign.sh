#!/bin/bash
# SmartPrep AI — Apply redesign
# Run this from inside ~/Desktop/smartprep-ai-groq/

FRONTEND="$HOME/Desktop/smartprep-ai-groq/frontend/src"
ZIP="$HOME/Downloads/smartprep-redesign.zip"

if [ ! -f "$ZIP" ]; then
  echo "ERROR: Could not find $ZIP"
  echo "Please download smartprep-redesign.zip from Claude first."
  exit 1
fi

echo "Backing up current frontend..."
cp -r "$FRONTEND" "${FRONTEND}_backup_$(date +%H%M%S)"

echo "Applying redesign..."
cd /tmp
rm -rf smartprep-redesign-extract
mkdir smartprep-redesign-extract
unzip -q "$ZIP" -d smartprep-redesign-extract
cp -r smartprep-redesign-extract/smartprep-redesign/frontend/src/* "$FRONTEND/"

echo ""
echo "Done! Redesign applied successfully."
echo "Your browser should auto-refresh at http://localhost:3000"
