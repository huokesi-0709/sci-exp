#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="${1:-/mnt/d/projects/RAG-sci/docs/sci-exp/}"
TARGET="${2:-radxa@192.168.66.106:/home/radxa/sci-exp/}"

if [[ ! -d "${SOURCE_ROOT}" ]]; then
  echo "本地目录不存在: ${SOURCE_ROOT}" >&2
  exit 2
fi
if [[ ! -f "${SOURCE_ROOT%/}/.radxa-sync-exclude" ]]; then
  echo "缺少同步排除清单: ${SOURCE_ROOT%/}/.radxa-sync-exclude" >&2
  exit 2
fi
if ! command -v rsync >/dev/null 2>&1; then
  echo "缺少rsync。在WSL中执行: sudo apt update && sudo apt install rsync" >&2
  exit 3
fi

# Deliberately omit --delete: Radxa上的ARM64 build、结果和校准原始日志必须保留。
# Gold/标注目录由.radxa-sync-exclude阻止传输；正式运行配置只读取Gold-free推理分区。
# rsync compares metadata and transfers only new or changed files.
rsync \
  --archive \
  --compress \
  --partial \
  --human-readable \
  --itemize-changes \
  --exclude-from="${SOURCE_ROOT%/}/.radxa-sync-exclude" \
  -e ssh \
  "${SOURCE_ROOT%/}/" \
  "${TARGET}"

echo "增量同步完成（未删除Radxa上的任何文件）"
