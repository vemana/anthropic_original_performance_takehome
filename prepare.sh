#!/bin/bash --norc

set -euEf -o pipefail
shopt -s inherit_errexit

git diff origin/main tests/

python3 tests/submission_tests.py > /tmp/log.txt && tail -n 140 /tmp/log.txt | sed -i '1e cat -' solution_readme.md

cp /tmp/program.txt xyz_program.txt

cp /tmp/output.html visual_instructions.html

