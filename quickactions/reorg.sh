#!/bin/zsh
for f in "$@"; do
  "$HOME/bin/yordam-agent" reorg "$f"
done
