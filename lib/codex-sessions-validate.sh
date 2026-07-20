#!/usr/bin/env bash

codex_session_id_is_valid() {
  local sid=${1-}

  if [[ $sid == . || $sid == .. || $sid == *..* || $sid == */* ]]; then
    return 1
  fi
  [[ $sid =~ ^[A-Za-z0-9_][A-Za-z0-9._-]*$ ]]
}
