"""Aggregate LLM token usage and estimated costs from data/llm_token_log.csv.

Usage:
    python scripts/aggregate_llm_costs.py

This prints a concise summary by date and agent, plus grand totals.

This only reads the LLM CSV produced by the runtime logger. It does not currently track
external API calls (Google Maps, Weather) unless those tools are explicitly instrumented
to write rows to the same CSV or a separate API log.
"""
from collections import defaultdict
import csv
import os
from datetime import datetime

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'llm_token_log.csv')
CSV_PATH = os.path.normpath(CSV_PATH)

if not os.path.exists(CSV_PATH):
    print(f"No CSV found at {CSV_PATH}")
    raise SystemExit(0)

# Aggregation structures
by_date = defaultdict(lambda: {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'cost': 0.0, 'rows': 0})
by_agent = defaultdict(lambda: {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'cost': 0.0, 'rows': 0})
by_model = defaultdict(lambda: {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'cost': 0.0, 'rows': 0})

total = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'cost': 0.0, 'rows': 0}

with open(CSV_PATH, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            ts = row.get('timestamp') or row.get('time')
            dt = datetime.fromisoformat(ts) if ts else None
        except Exception:
            dt = None
        date_key = dt.date().isoformat() if dt else 'unknown'

        agent = row.get('agent', 'unknown')
        model = row.get('model', 'unknown')

        in_t = int(float(row.get('input_tokens') or 0))
        out_t = int(float(row.get('output_tokens') or 0))
        tot_t = int(float(row.get('total_tokens') or (in_t + out_t)))
        cost = float(row.get('total_cost') or 0.0)

        by_date[date_key]['input_tokens'] += in_t
        by_date[date_key]['output_tokens'] += out_t
        by_date[date_key]['total_tokens'] += tot_t
        by_date[date_key]['cost'] += cost
        by_date[date_key]['rows'] += 1

        by_agent[agent]['input_tokens'] += in_t
        by_agent[agent]['output_tokens'] += out_t
        by_agent[agent]['total_tokens'] += tot_t
        by_agent[agent]['cost'] += cost
        by_agent[agent]['rows'] += 1

        by_model[model]['input_tokens'] += in_t
        by_model[model]['output_tokens'] += out_t
        by_model[model]['total_tokens'] += tot_t
        by_model[model]['cost'] += cost
        by_model[model]['rows'] += 1

        total['input_tokens'] += in_t
        total['output_tokens'] += out_t
        total['total_tokens'] += tot_t
        total['cost'] += cost
        total['rows'] += 1

# Print report
print("LLM token usage summary")
print("========================")
print('\nBy date:')
for d, vals in sorted(by_date.items()):
    print(f"  {d}: rows={vals['rows']} tokens={vals['total_tokens']} (in={vals['input_tokens']}, out={vals['output_tokens']}) cost=${vals['cost']:.6f}")

print('\nBy agent:')
for a, vals in sorted(by_agent.items()):
    print(f"  {a}: rows={vals['rows']} tokens={vals['total_tokens']} cost=${vals['cost']:.6f}")

print('\nBy model:')
for m, vals in sorted(by_model.items()):
    print(f"  {m}: rows={vals['rows']} tokens={vals['total_tokens']} cost=${vals['cost']:.6f}")

print('\nGrand total:')
print(f"  rows={total['rows']} tokens={total['total_tokens']} (in={total['input_tokens']}, out={total['output_tokens']}) cost=${total['cost']:.6f}")

# Optional: write an aggregated JSON summary next to CSV
try:
    import json
    out_path = os.path.join(os.path.dirname(CSV_PATH), 'llm_token_log_summary.json')
    with open(out_path, 'w', encoding='utf-8') as out:
        json.dump({'by_date': by_date, 'by_agent': by_agent, 'by_model': by_model, 'total': total}, out, default=int, indent=2)
    print(f"\nWrote summary to {out_path}")
except Exception:
    pass
