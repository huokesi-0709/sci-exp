#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/radxa/sci-exp"
SOURCE_DIR="$PROJECT_ROOT/third_party/llama.cpp-b9627"
BUILD_DIR="$SOURCE_DIR/build-e1-release"
TARGET="$PROJECT_ROOT/bin/llama-server"
REPORT="$PROJECT_ROOT/results/ARM64_llama_server构建记录_v1.0.txt"
EXPECTED_TAG="b9627"
EXPECTED_COMMIT_PREFIX="53bd47e"

cd "$PROJECT_ROOT"
mkdir -p bin results

ARCH="$(uname -m)"
if [ "$ARCH" != "aarch64" ] && [ "$ARCH" != "arm64" ]; then
  echo "拒绝构建：E1架构必须为ARM64，当前为 $ARCH" >&2
  exit 2
fi
if [ ! -f "$SOURCE_DIR/CMakeLists.txt" ]; then
  echo "缺少已冻结源码：$SOURCE_DIR" >&2
  exit 2
fi
if [ -e "$TARGET" ]; then
  echo "拒绝覆盖已有运行时：$TARGET" >&2
  exit 3
fi

ACTUAL_COMMIT="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
if [[ "$ACTUAL_COMMIT" != "$EXPECTED_COMMIT_PREFIX"* ]]; then
  echo "源码提交不匹配：期望 $EXPECTED_COMMIT_PREFIX，实际 $ACTUAL_COMMIT" >&2
  exit 4
fi

cmake -S "$SOURCE_DIR" -B "$BUILD_DIR" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=ON \
  -DGGML_OPENMP=ON \
  -DLLAMA_CURL=OFF \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_UI=OFF \
  -DLLAMA_USE_PREBUILT_UI=OFF

# b9627 仍会把可用静态资源嵌入 server；关闭 Web UI 后，若构建目录残留了
# index.html，嵌入器仍要求 loading.html。使用源码自带的静态文件补齐该唯一资产，
# 避免联网下载的 UI 包覆盖缓存后导致构建失败。
mkdir -p "$BUILD_DIR/tools/ui/dist"
install -m 0644 "$SOURCE_DIR/tools/ui/static/loading.html" \
  "$BUILD_DIR/tools/ui/dist/loading.html"
cmake --build "$BUILD_DIR" --config Release --target llama-server --parallel "$(nproc)"

BUILT="$BUILD_DIR/bin/llama-server"
if [ ! -x "$BUILT" ]; then
  echo "构建完成但未找到可执行文件：$BUILT" >&2
  exit 5
fi
install -m 0755 "$BUILT" "$TARGET"

{
  echo "device_id=E1"
  echo "architecture=$ARCH"
  echo "llama_cpp_tag=$EXPECTED_TAG"
  echo "llama_cpp_commit=$ACTUAL_COMMIT"
  echo "build_type=Release"
  echo "build_flags=-DGGML_NATIVE=ON -DGGML_OPENMP=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_UI=OFF -DLLAMA_USE_PREBUILT_UI=OFF"
  echo "llama_server_path=$TARGET"
  echo "llama_server_sha256=$(sha256sum "$TARGET" | awk '{print $1}')"
  echo "llama_server_size_bytes=$(stat -c %s "$TARGET")"
  echo "cmake_version=$(cmake --version | head -n 1)"
  echo "compiler=$(cc --version | head -n 1)"
  echo "built_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  "$TARGET" --version
  echo
  ldd "$TARGET" || true
} > "$REPORT"

cat "$REPORT"
