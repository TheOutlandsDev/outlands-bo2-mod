#!/usr/bin/env bash
set -euo pipefail
hosting_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd -- "$hosting_dir"
action="${1:-check}"
case "$action" in check|smoke|key|up|down|status|logs|tailnet-login|ai-up|ai-model|export-invite) ;;
    *) printf 'Usage: %s {check|smoke|up|ai-up|ai-model|export-invite|status|logs|down|tailnet-login|key}\n' "$0" >&2; exit 2 ;;
esac

docker_cmd=("$hosting_dir/docker.sh")
compose_flags=(-f "$hosting_dir/compose.yaml")
refresh_flags() {
    compose_flags=(-f "$hosting_dir/compose.yaml")
    if [[ -f "$hosting_dir/compose.local.json" ]]; then
        compose_flags+=(-f "$hosting_dir/compose.local.json")
    fi
    if [[ "$action" == ai-up || "$action" == ai-model || "$action" == down ]]; then
        compose_flags+=(-f "$hosting_dir/compose.ai.yaml")
    fi
}
compose() { "${docker_cmd[@]}" compose "${compose_flags[@]}" "$@"; }
prepare() {
    python3 -B "$hosting_dir/setup_host.py" --apply
    refresh_flags
    compose config --quiet
    "${docker_cmd[@]}" compose -f compose.yaml -f compose.smoke.yaml config --quiet
}
model() {
    compose exec -T ollama ollama pull qwen3:1.7b
    compose exec -T ollama ollama create outlands-bo2-chat -f /opt/outlands/Modelfile
}
refresh_flags
mkdir -p logs
case "$action" in
    check)
        prepare
        printf '%s\n' 'Verified private build package and Compose configuration. No containers started.'
        ;;
    key)
        data_volume="$(compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["volumes"]["t6-state"]["name"])')"
        read -r -s -p 'Optional online Plutonium T6 server key (input hidden): ' server_key
        printf '\n'
        if [[ -z "$server_key" || "$server_key" == *[$'\r\n\t ']* ]]; then
            printf '%s\n' 'Expected a nonempty, single-line server key without spaces.' >&2; exit 1
        fi
        printf '%s' "$server_key" | "${docker_cmd[@]}" run --rm -i --network none \
            --cap-drop ALL --security-opt no-new-privileges:true \
            -v "$data_volume:/data" --entrypoint python3 outlands-t6:local /opt/t6/store_key.py
        unset server_key
        ;;
    smoke)
        prepare
        compose build t6 > logs/build.log 2>&1
        smoke=("${docker_cmd[@]}" compose -p outlands-t6-smoke -f compose.yaml -f compose.smoke.yaml)
        "${smoke[@]}" up -d --no-deps t6
        cleanup_smoke() { "${smoke[@]}" stop -t 15 t6 >/dev/null 2>&1 || true; }
        trap cleanup_smoke EXIT
        container_id="$("${smoke[@]}" ps -aq t6)"
        ready=0
        for ((attempt=0; attempt<180; attempt++)); do
            state="$("${docker_cmd[@]}" inspect --format '{{.State.Status}}' "$container_id")"
            health="$("${docker_cmd[@]}" inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"
            if [[ "$health" == healthy ]]; then ready=1; break; fi
            if [[ "$state" == exited || "$state" == dead ]]; then break; fi
            if (( attempt % 15 == 0 )); then printf 'Waiting for isolated server (%s, %s)...\n' "$state" "$health"; fi
            sleep 2
        done
        "${smoke[@]}" logs --no-color t6 > logs/smoke.log
        if (( ready == 0 )); then
            printf '%s\n' 'Smoke test failed. Inspect the private hosting/logs/smoke.log.' >&2; exit 1
        fi
        printf '%s\n' 'PASS: isolated server socket and diagnostic script loaded. Gameplay needs a client.'
        ;;
    up|ai-up)
        prepare
        if [[ "$action" == ai-up ]]; then
            compose build t6 ollama chat > logs/build.log 2>&1
            compose up -d tailscale ollama
        else
            compose build t6 > logs/build.log 2>&1
            compose up -d tailscale
        fi
        compose exec tailscale tailscale up
        compose up -d --no-deps t6
        if [[ "$action" == ai-up ]]; then
            model
            compose up -d chat
        fi
        compose ps
        compose exec -T tailscale tailscale ip -4
        printf '%s\n' 'Use this tailnet address with UDP port 4977 (or your configured T6_PORT).'
        ;;
    ai-model) model ;;
    export-invite) shift; python3 "$hosting_dir/export_invite.py" "$@" ;;
    tailnet-login) compose exec tailscale tailscale up ;;
    down) compose down ;;
    status) compose ps ;;
    logs) compose logs --tail 100 t6 ;;
esac
