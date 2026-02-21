#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <model-alias>" >&2
  echo "Supported aliases: opus, sonnet, haiku, codex, minimax-m2.1, minimax-m2.5" >&2
  exit 1
fi

alias="$1"
declare -A models=(
  [opus]="anthropic/claude-opus-4-6"
  [sonnet]="anthropic/claude-3-5-sonnet"
  [haiku]="anthropic/claude-3-haiku"
  [codex]="openai-codex/gpt-5.1-codex-mini"
  ["minimax-m2.1"]="minimax-portal/MiniMax-M2.1"
  ["minimax-m2.5"]="minimax-portal/MiniMax-M2.5"
)

target_model="${models[$alias]:-}"
if [[ -z "$target_model" ]]; then
  echo "Unknown alias: $alias" >&2
  echo "Supported aliases: ${!models[*]}" >&2
  exit 1
fi

openclaw config set agents.defaults.model.primary "$target_model"

agent_model="$(openclaw config get agents.defaults.model.primary)"
if [[ "$agent_model" != "$target_model" ]]; then
  echo "Failed to update default model. Current config reports: $agent_model" >&2
  exit 1
fi

echo "Default model set to '$alias' ($target_model)."
