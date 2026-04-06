#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

npm install

if [ ! -f ".env" ]; then
  cp .env.example .env
fi

npm run dev
