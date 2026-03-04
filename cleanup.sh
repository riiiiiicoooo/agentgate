#!/bin/bash
# Run this locally to remove agent-generated working files
cd "$(dirname "$0")"
rm -f CODEBASE_SUMMARY.md COMPLETION_REPORT.md CREATED_FILES_SUMMARY.md FILE_MANIFEST.md
echo "Cleanup complete"
