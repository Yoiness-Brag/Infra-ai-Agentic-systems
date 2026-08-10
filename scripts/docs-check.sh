#!/usr/bin/env bash
# Folder-discipline gate: every layer and stage folder carries its required docs.
# Referenced by `make docs-check` and by STAGE-00's acceptance criteria.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
ok()   { printf '  \033[32mOK  \033[0m %s\n' "$1"; }
bad()  { printf '  \033[31mMISS\033[0m %s\n' "$1"; fail=1; }

echo "== docs/layers: README.md + FLOW.mmd =="
for d in docs/layers/L*/; do
  [ -d "$d" ] || continue
  [ -f "$d/README.md" ] && ok "$d/README.md" || bad "$d/README.md"
  [ -f "$d/FLOW.mmd" ]  && ok "$d/FLOW.mmd"  || bad "$d/FLOW.mmd"
done

echo "== docs/stages: README.md =="
for d in docs/stages/STAGE-*/; do
  [ -d "$d" ] || continue
  [ -f "$d/README.md" ] && ok "$d/README.md" || bad "$d/README.md"
done

echo "== docs/adr: numbered and non-empty =="
count=$(find docs/adr -maxdepth 1 -name '[0-9][0-9][0-9][0-9]-*.md' | wc -l)
[ "$count" -ge 12 ] && ok "$count ADRs present" || bad "expected >=12 ADRs, found $count"

echo "== platform/: every folder has a README.md =="
while IFS= read -r d; do
  [ -f "$d/README.md" ] && ok "$d/README.md" || bad "$d/README.md"
done < <(find platform -type d -not -path '*/.*' | sort)

echo "== infra-code: contract documents =="
for f in infra-code/SPEC.md infra-code/README.md infra-code/docs/PRODUCTION-READINESS.md; do
  [ -f "$f" ] && ok "$f" || bad "$f"
done

echo "== banned terminology (outside immutable ADRs and their own definitions) =="
hits=$(grep -rniE '\b(bootstrap\w*|tenancy)\b' docs platform infra-code .backlog \
        --include='*.md' --include='*.yaml' --include='*.yml' \
        --exclude-dir=.venv --exclude-dir=adr 2>/dev/null \
      | grep -viE 'use \*|replaces the term|— use |banned|never write|terminology|per-app isolation|workload separation|namespace boundary|platform initialization|cluster-b' || true)
if [ -z "$hits" ]; then
  ok "no banned terms"
else
  echo "$hits" | sed 's/^/  /'
  fail=1
fi

echo
[ $fail -eq 0 ] && echo "DOCS-CHECK PASSED" || { echo "DOCS-CHECK FAILED"; exit 1; }
