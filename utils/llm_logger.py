import csv
import os
from datetime import datetime
from typing import Dict, Any


def log_llm_usage(agent: str, model: str, usage: Dict[str, int], rates: Dict[str, float] = None) -> None:
    """Append a single row to data/llm_token_log.csv with usage and cost estimates.

    usage should contain keys: input_tokens, output_tokens, total_tokens
    """
    if rates is None:
        rates = {
            'input': 0.00001875,
            'output': 0.000075
        }

    input_tokens = usage.get('input_tokens', 0)
    output_tokens = usage.get('output_tokens', 0)
    total_tokens = usage.get('total_tokens', input_tokens + output_tokens)

    input_cost = input_tokens * rates['input']
    output_cost = output_tokens * rates['output']
    total_cost = input_cost + output_cost

    # Resolve project-level data directory reliably (utils/../data)
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    data_dir = os.path.normpath(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    csv_path = os.path.join(data_dir, 'llm_token_log.csv')
    header = ['timestamp','agent','model','input_tokens','output_tokens','total_tokens','input_cost','output_cost','total_cost']

    try:
        # If file exists but is empty, we still need to write header
        write_header = True
        if os.path.exists(csv_path):
            try:
                write_header = os.path.getsize(csv_path) == 0
            except Exception:
                write_header = False

        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(header)
            writer.writerow([
                datetime.utcnow().isoformat(),
                agent,
                model,
                input_tokens,
                output_tokens,
                total_tokens,
                f"{input_cost:.8f}",
                f"{output_cost:.8f}",
                f"{total_cost:.8f}"
            ])
    except Exception as e:
        # Best-effort logging; surface the error to stderr for debugging during development
        try:
            import sys
            print(f"[llm_logger] Failed to write LLM log to {csv_path}: {e}", file=sys.stderr)
        except Exception:
            pass
