#!/bin/bash

NAME="pyhark-docker"

# ホストマシンのディレクトリとコンテナ内のディレクトリ（絶対パスで指定）
HOST_DIR=$(pwd -W 2>/dev/null || pwd)/mount  # カレントディレクトリに基づいて絶対パスを生成
CONTAINER_DIR="/mnt"  # コンテナ内での絶対パス

# Dockerコンテナを実行
docker run -it \
  --name ${NAME} \
  -v "${HOST_DIR}:${CONTAINER_DIR}" \
  ${NAME} fish
