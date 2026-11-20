#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
docker compose up -d --wait db

module_state=$(docker compose exec -T db psql -X -U odoo -d insea_erp -Atc \
    "SELECT state FROM ir_module_module WHERE name = 'insea_hr_leave_custom'" 2>/dev/null || true)
if [[ "$module_state" != installed ]]; then
    docker compose stop odoo
    docker compose run -T --rm odoo odoo -d insea_erp \
        -i insea_hr_leave_custom --without-demo=all --stop-after-init
fi

docker compose up -d odoo
