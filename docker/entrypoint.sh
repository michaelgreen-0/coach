#!/bin/sh
# Trust X-Forwarded-* only from Caddy, so no other container on the shared
# network can forge a client IP past the per-IP rate limiter. Caddy's address is
# Docker-assigned, so resolve it by its stable DNS name at startup. If it can't
# be resolved we fall closed to loopback-only trust rather than trusting everyone.
set -e

caddy_ip="$(python -c "import socket; print(socket.gethostbyname('caddy'))" 2>/dev/null || true)"
if [ -z "$caddy_ip" ]; then
    echo "entrypoint: could not resolve 'caddy'; trusting loopback only" >&2
    caddy_ip="127.0.0.1"
fi

exec uvicorn --factory coach.backend.app:create_app \
    --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips "$caddy_ip"
