import csv
import os
from datetime import datetime
from typing import Dict, Any
import json


# Default estimated costs per endpoint (in USD). These can be overridden by environment variables
# using names like EST_COST_geocode_json or EST_COST_geolocate. Keys are normalized endpoint strings.
DEFAULT_EST_COST = {
    'geocode/json': 0.005,               # example: geocode request
    'geolocate': 0.002,                  # example: geolocate (IP-based)
    'currentConditions:lookup': 0.01     # example: weather lookup
}

def _get_env_est_cost(endpoint: str) -> float:
    """Look up an environment override for estimated cost for the given endpoint.

    Environment variable format: EST_COST_{UPPER_ENDPOINT_SAFE}
    e.g. endpoint 'geocode/json' -> EST_COST_GEOCODE_JSON
    """
    try:
        safe = endpoint.upper().replace('/', '_').replace(':', '_').replace('-', '_')
        env_key = f"EST_COST_{safe}"
        val = os.environ.get(env_key)
        if val:
            return float(val)
    except Exception:
        pass
    # fallback to defaults
    return float(DEFAULT_EST_COST.get(endpoint, 0.0))


def log_api_call(tool_name: str, provider: str, endpoint: str, status: int, elapsed_ms: int = None, response_bytes: int = None, params: Dict[str, Any] = None, estimated_cost: float = None):
    """Append a row describing an external API call to data/api_call_log.csv.

    This is a safe, best-effort logger. It will not raise exceptions.
    """
    try:
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        data_dir = os.path.normpath(data_dir)
        os.makedirs(data_dir, exist_ok=True)
        csv_path = os.path.join(data_dir, 'api_call_log.csv')

        header = ['timestamp','tool','provider','endpoint','status','elapsed_ms','response_bytes','params','estimated_cost']
        write_header = not os.path.exists(csv_path)
        
        # If file exists, check if it has headers by reading first line
        if os.path.exists(csv_path) and not write_header:
            try:
                with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    # If first line doesn't start with 'timestamp', it needs headers
                    if not first_line.startswith('timestamp'):
                        write_header = True
            except Exception:
                # If we can't read the file, assume it needs headers
                write_header = True

        params_short = ''
        if params:
            try:
                # keep params small
                params_short = ','.join([f"{k}={v}" for k,v in list(params.items())[:5]])
            except Exception:
                params_short = str(params)

        # If estimated_cost not provided, compute a conservative estimate from endpoint defaults/env overrides
        if estimated_cost is None:
            try:
                est = _get_env_est_cost(endpoint)
                estimated_cost = float(est)
            except Exception:
                estimated_cost = 0.0

        row = [
            datetime.utcnow().isoformat(),
            tool_name,
            provider,
            endpoint,
            int(status) if status is not None else '',
            int(elapsed_ms) if elapsed_ms is not None else '',
            int(response_bytes) if response_bytes is not None else '',
            params_short,
            f"{estimated_cost:.8f}" if estimated_cost is not None else ''
        ]

        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(header)
            writer.writerow(row)
    except Exception:
        pass
