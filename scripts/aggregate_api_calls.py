"""Aggregate external API call logs from data/api_call_log.csv.

Usage:
    python scripts/aggregate_api_calls.py

Produces a JSON summary `data/api_call_log_summary.json` with totals by date, provider, tool, and endpoint.
"""
from collections import defaultdict
import csv
import os
from datetime import datetime
import re

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'api_call_log.csv')
CSV_PATH = os.path.normpath(CSV_PATH)

if not os.path.exists(CSV_PATH):
    print(f"No CSV found at {CSV_PATH}")
    raise SystemExit(0)

# Aggregation structures
by_date = defaultdict(lambda: {'calls': 0, 'elapsed_ms': 0, 'response_bytes': 0, 'errors': 0, 'estimated_cost': 0.0})
by_provider = defaultdict(lambda: {'calls': 0, 'elapsed_ms': 0, 'response_bytes': 0, 'errors': 0, 'estimated_cost': 0.0})
by_tool = defaultdict(lambda: {'calls': 0, 'elapsed_ms': 0, 'response_bytes': 0, 'errors': 0, 'estimated_cost': 0.0})
by_endpoint = defaultdict(lambda: {'calls': 0, 'elapsed_ms': 0, 'response_bytes': 0, 'errors': 0, 'estimated_cost': 0.0})

total = {'calls': 0, 'elapsed_ms': 0, 'response_bytes': 0, 'errors': 0, 'estimated_cost': 0.0}

with open(CSV_PATH, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            ts = row.get('timestamp') or row.get('time')
            dt = datetime.fromisoformat(ts) if ts else None
        except Exception:
            dt = None
        date_key = dt.date().isoformat() if dt else 'unknown'

        tool = row.get('tool') or 'unknown'
        provider = row.get('provider') or 'unknown'
        endpoint = row.get('endpoint') or 'unknown'

        try:
            elapsed = int(float(row.get('elapsed_ms') or 0))
        except Exception:
            elapsed = 0
        try:
            resp_bytes = int(float(row.get('response_bytes') or 0))
        except Exception:
            resp_bytes = 0
        try:
            status = int(row.get('status') or 0)
        except Exception:
            status = 0
        try:
            est_cost = float(row.get('estimated_cost') or 0.0)
        except Exception:
            est_cost = 0.0

        # If estimated cost is zero, attempt to compute a conservative estimate from env/defaults
        if est_cost == 0.0:
            try:
                # Normalize endpoint to env var style: replace non-alphanumeric with underscores and uppercase
                safe = re.sub(r'[^0-9A-Za-z]', '_', endpoint).upper()
                env_key = f"EST_COST_{safe}"
                val = os.environ.get(env_key)
                if val:
                    est_cost = float(val)
                else:
                    # conservative defaults matching utils/api_logger.DEFAULT_EST_COST
                    defaults = {
                        'GEOCODE_JSON': 0.005,
                        'GEOLOCATE': 0.002,
                        'CURRENTCONDITIONS_LOOKUP': 0.01
                    }
                    est_cost = float(defaults.get(safe, 0.0))
            except Exception:
                est_cost = 0.0

        is_error = 1 if (status >= 400 or status == 0) else 0

        by_date[date_key]['calls'] += 1
        by_date[date_key]['elapsed_ms'] += elapsed
        by_date[date_key]['response_bytes'] += resp_bytes
        by_date[date_key]['errors'] += is_error
        by_date[date_key]['estimated_cost'] += est_cost

        by_provider[provider]['calls'] += 1
        by_provider[provider]['elapsed_ms'] += elapsed
        by_provider[provider]['response_bytes'] += resp_bytes
        by_provider[provider]['errors'] += is_error
        by_provider[provider]['estimated_cost'] += est_cost

        by_tool[tool]['calls'] += 1
        by_tool[tool]['elapsed_ms'] += elapsed
        by_tool[tool]['response_bytes'] += resp_bytes
        by_tool[tool]['errors'] += is_error
        by_tool[tool]['estimated_cost'] += est_cost

        by_endpoint[endpoint]['calls'] += 1
        by_endpoint[endpoint]['elapsed_ms'] += elapsed
        by_endpoint[endpoint]['response_bytes'] += resp_bytes
        by_endpoint[endpoint]['errors'] += is_error
        by_endpoint[endpoint]['estimated_cost'] += est_cost

        total['calls'] += 1
        total['elapsed_ms'] += elapsed
        total['response_bytes'] += resp_bytes
        total['errors'] += is_error
        total['estimated_cost'] += est_cost

# Print a short summary
print("API call usage summary")
print("======================")
print('\nBy date:')
for d, vals in sorted(by_date.items()):
    print(f"  {d}: calls={vals['calls']} errors={vals['errors']} elapsed_ms={vals['elapsed_ms']} response_bytes={vals['response_bytes']} est_cost=${vals['estimated_cost']:.6f}")

print('\nBy provider:')
for p, vals in sorted(by_provider.items()):
    print(f"  {p}: calls={vals['calls']} errors={vals['errors']} elapsed_ms={vals['elapsed_ms']} est_cost=${vals['estimated_cost']:.6f}")

print('\nBy tool:')
for t, vals in sorted(by_tool.items()):
    print(f"  {t}: calls={vals['calls']} errors={vals['errors']} elapsed_ms={vals['elapsed_ms']} est_cost=${vals['estimated_cost']:.6f}")

print('\nGrand total:')
print(f"  calls={total['calls']} errors={total['errors']} elapsed_ms={total['elapsed_ms']} response_bytes={total['response_bytes']} est_cost=${total['estimated_cost']:.6f}")

# Write JSON summary
try:
    import json
    out_path = os.path.join(os.path.dirname(CSV_PATH), 'api_call_log_summary.json')
    with open(out_path, 'w', encoding='utf-8') as out:
        json.dump({'by_date': by_date, 'by_provider': by_provider, 'by_tool': by_tool, 'by_endpoint': by_endpoint, 'total': total}, out, default=int, indent=2)
    print(f"\nWrote summary to {out_path}")
except Exception:
    pass
