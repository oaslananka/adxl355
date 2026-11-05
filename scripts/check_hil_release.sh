#!/usr/bin/env bash
# Exact-commit HIL risk evaluation. Never runs physical hardware.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if (($# != 1)) || [[ ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Expected exact 40-character release SHA" >&2
  exit 2
fi
head="$1"
mapfile -t metadata < <(python3 "$root/scripts/hil_release_policy.py" --metadata)
if (("${#metadata[@]}" != 2)); then
  echo "Invalid HIL baseline metadata" >&2
  exit 2
fi
base="${metadata[0]%$'\r'}"
tag="${metadata[1]%$'\r'}"
test "$(git -C "$root" rev-parse --verify "${head}^{commit}")" = "$head"
git -C "$root" merge-base --is-ancestor "$base" "$head"
if [[ "$tag" != "-" ]]; then
  test "$(git -C "$root" rev-parse --verify "refs/tags/${tag}^{commit}")" = "$base"
fi
git -C "$root" diff --name-only --no-renames -z "$base" "$head" |
  python3 "$root/scripts/hil_release_policy.py" --head "$head" --require-software-only
