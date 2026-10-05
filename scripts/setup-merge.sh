#!/bin/sh
set -eu
git config merge.webloc-json.name "webloc JSON three-way merge"
git config merge.webloc-json.driver 'python3 -m webloc.merge %O %A %B'
echo "JSON merge driver configured. Install webloc in the Python environment used by Git."
