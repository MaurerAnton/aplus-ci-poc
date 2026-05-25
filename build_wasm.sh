#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# build_wasm.sh — Build A+ WebAssembly binaries via Docker + Emscripten
# ──────────────────────────────────────────────────────────────────
#
# Usage:
#   ./build_wasm.sh              Build docker image and extract WASM
#   ./build_wasm.sh --serve      Build + start local HTTP server
#   ./build_wasm.sh --clean      Remove build artifacts
#
# Output:
#   dist/aplus.js      Emscripten JS glue
#   dist/aplus.wasm    WebAssembly binary
#   dist/index.html    Browser REPL
# ──────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"
DOCKERFILE="$SCRIPT_DIR/Dockerfile.wasm"
IMAGE_NAME="aplus-wasm:latest"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[build]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $*"; }
err()  { echo -e "${RED}[error]${NC} $*"; exit 1; }

# ── Clean ────────────────────────────────────────────────────────
do_clean() {
    log "Cleaning build artifacts..."
    rm -rf "$DIST_DIR"
    docker rmi -f "$IMAGE_NAME" 2>/dev/null || true
    log "Done."
}

# ── Build ────────────────────────────────────────────────────────
do_build() {
    if [ ! -f "$DOCKERFILE" ]; then
        err "Dockerfile.wasm not found at $DOCKERFILE"
    fi

    log "Building Docker image: $IMAGE_NAME"
    docker build -t "$IMAGE_NAME" -f "$DOCKERFILE" "$SCRIPT_DIR"

    log "Extracting WASM artifacts..."
    rm -rf "$DIST_DIR"
    mkdir -p "$DIST_DIR"

    CID=$(docker create "$IMAGE_NAME")
    docker cp "$CID:/output/aplus.js"    "$DIST_DIR/aplus.js"
    docker cp "$CID:/output/aplus.wasm"  "$DIST_DIR/aplus.wasm"
    docker rm "$CID"

    # Copy the HTML REPL
    cp "$SCRIPT_DIR/index.html" "$DIST_DIR/index.html"

    log "Artifacts in $DIST_DIR:"
    ls -lh "$DIST_DIR/"
    echo ""
    log "Build complete. Open dist/index.html in a browser to use the REPL."
    echo "   (You may need to serve via HTTP since WASM requires it:"
    echo "    python3 -m http.server 8080 -d dist/)"
}

# ── Serve ────────────────────────────────────────────────────────
do_serve() {
    if [ ! -f "$DIST_DIR/aplus.js" ] || [ ! -f "$DIST_DIR/aplus.wasm" ]; then
        warn "WASM artifacts not found. Building first..."
        do_build
    fi

    local port="${1:-8080}"
    log "Starting HTTP server on http://localhost:$port"
    log "Press Ctrl+C to stop."
    echo ""

    if command -v python3 &>/dev/null; then
        python3 -m http.server "$port" -d "$DIST_DIR"
    elif command -v python &>/dev/null; then
        python -m SimpleHTTPServer "$port" -d "$DIST_DIR" 2>/dev/null || \
        (cd "$DIST_DIR" && python -m SimpleHTTPServer "$port")
    elif command -v npx &>/dev/null; then
        npx http-server "$DIST_DIR" -p "$port" -c-1
    else
        err "No HTTP server found. Install python3 or npx."
    fi
}

# ── Main ─────────────────────────────────────────────────────────
case "${1:-}" in
    --clean|-c)
        do_clean
        ;;
    --serve|-s)
        do_serve "${2:-8080}"
        ;;
    --help|-h)
        echo "Usage: $0 [--build|--serve [port]|--clean|--help]"
        echo ""
        echo "  (no args)    Build Docker image + extract WASM artifacts"
        echo "  --serve,-s   Build (if needed) + start HTTP server"
        echo "  --clean,-c   Remove dist/ and Docker image"
        echo "  --help,-h    Show this help"
        ;;
    *)
        do_build
        ;;
esac
