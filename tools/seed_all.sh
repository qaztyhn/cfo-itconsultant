#!/usr/bin/env bash
# Chạy migrate + seed CFO và seed hệ thống nguồn (08 mục 5). Owner: Dev 2.
set -euo pipefail
make migrate
make seed
