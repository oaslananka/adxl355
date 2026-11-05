#!/usr/bin/env bash
# Compare clean, isolated Linux package builds without publishing artifacts.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "${1:-}" == '--components' ]]; then shift; fi
if (($# == 0)); then set -- c python rust npm; fi
for component in "$@"; do
  case "$component" in
    c|python|rust|npm) ;;
    *) printf 'unsupported component: %s\n' "$component" >&2; exit 2 ;;
  esac
done

if [[ "$*" == *npm* && ! -f "$ROOT/node/node_modules/.bin/tsc" ]]; then
  printf 'Install Node development dependencies first: cd node && npm ci --ignore-scripts\n' >&2
  exit 2
fi

SOURCE_DATE_EPOCH="$(git -C "$ROOT" show -s --format=%ct HEAD)"
export SOURCE_DATE_EPOCH TZ=UTC LC_ALL=C
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/adxl355-repro.XXXXXXXX")"
trap 'rm -rf -- "$SCRATCH"' EXIT

build_component() {
  local component="$1" attempt="$2" dest="$SCRATCH/$2/$1"
  mkdir -p "$dest"
  case "$component" in
    c)
      cmake -S "$ROOT/c" -B "$SCRATCH/$attempt/c-build" -DCMAKE_BUILD_TYPE=Release \
        -DADXL355_BUILD_TESTS=OFF -DADXL355_BUILD_EXAMPLES=OFF >/dev/null
      cmake --build "$SCRATCH/$attempt/c-build" --parallel 2 >/dev/null
      cp -- "$SCRATCH/$attempt/c-build/libadxl355.a" "$dest/libadxl355.a"
      ;;
    python)
      (cd "$ROOT" && uvx --from 'build==1.5.0' --with 'setuptools==84.2.1' \
        pyproject-build --no-isolation python --outdir "$dest" >/dev/null)
      local sdists=("$dest"/*.tar.gz)
      ((${#sdists[@]} == 1)) && [[ -f "${sdists[0]}" ]] || {
        echo 'expected one Python source archive' >&2; return 3;
      }
      python3 "$ROOT/scripts/normalize_sdist.py" "${sdists[0]}" --epoch "$SOURCE_DATE_EPOCH"
      ;;
    rust)
      (cd "$ROOT" && CARGO_TARGET_DIR="$SCRATCH/$attempt/rust-target" \
        cargo package --locked --manifest-path rust/Cargo.toml --no-verify >/dev/null)
      local crates=("$SCRATCH/$attempt/rust-target/package/"*.crate)
      ((${#crates[@]} == 1)) && [[ -f "${crates[0]}" ]] || {
        echo 'expected one Rust crate' >&2; return 3;
      }
      cp -- "${crates[0]}" "$dest/"
      ;;
    npm)
      local copy="$SCRATCH/$attempt/npm-source"
      mkdir -p "$copy"
      tar -C "$ROOT/node" --exclude='./node_modules' --exclude='./dist' \
        --exclude='./.npm-*' --exclude='./.vitest-*' -cf - . | tar -C "$copy" -xf -
      ln -s -- "$ROOT/node/node_modules" "$copy/node_modules"
      (cd "$copy" && npm run build >/dev/null && \
        npm pack --ignore-scripts --silent --pack-destination "$dest" >/dev/null)
      ;;
    *)
      printf 'unsupported component during build: %s\n' "$component" >&2
      return 2
      ;;
  esac
}

for component in "$@"; do
  build_component "$component" a
  build_component "$component" b
  a="$SCRATCH/a/$component" b="$SCRATCH/b/$component"
  shopt -s nullglob
  items=("$a"/*)
  shopt -u nullglob
  ((${#items[@]} > 0)) || { echo "no $component artifacts" >&2; exit 3; }
  for artifact in "${items[@]}"; do
    name="$(basename -- "$artifact")"
    if [[ ! -f "$b/$name" ]] || ! cmp -s -- "$artifact" "$b/$name"; then
      echo "NOT REPRODUCIBLE: $component $name" >&2
      exit 3
    fi
    printf 'PASS %s: %s sha256=%s\n' "$component" "$name" \
      "$(sha256sum -- "$artifact" | cut -d ' ' -f 1)"
  done
  shopt -s nullglob
  others=("$b"/*)
  shopt -u nullglob
  ((${#others[@]} == ${#items[@]})) || {
    echo "artifact set mismatch: $component" >&2; exit 3;
  }
done
printf 'All selected packages reproduced byte-for-byte in independent scratch builds.\n'
