# state.py
def deepMerge(base, patch):
    """
    Recursively merge nested dictionaries.
    Updates 'base' in place with values from 'patch'.
    
    Args:
        base: The dictionary to update
        patch: The dictionary with updates to apply
        
    Returns:
        The updated base dictionary
    """
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deepMerge(base[k], v)
        else:
            base[k] = v
    return base


def compact_world_state(world_state):
    """Return a compact, JSON-serializable dict with only the most relevant fields
    from a WorldState-like object to reduce LLM prompt sizes.

    Keeps: query.raw, slots.origin/destination (lat,lng,name), context.lastWeather summary
    (temp, summary), context.reverse_geocode_result.formatted_address, brief plan metadata,
    and any errors. Safe for missing attributes.
    """
    try:
        compact = {}
        # Query
        try:
            compact['query'] = getattr(world_state, 'query', {}).get('raw') if hasattr(world_state, 'query') else world_state.get('query', {}).get('raw')
        except Exception:
            compact['query'] = ''

        # Slots: origin and destination limited to lat,lng,name
        compact['slots'] = {}
        try:
            origin = getattr(world_state, 'slots', {}).get('origin') if hasattr(world_state, 'slots') else world_state.get('slots', {}).get('origin')
            if origin:
                compact['slots']['origin'] = {
                    'lat': origin.get('lat'),
                    'lng': origin.get('lng'),
                    'name': origin.get('name')
                }
        except Exception:
            pass
        try:
            destination = getattr(world_state, 'slots', {}).get('destination') if hasattr(world_state, 'slots') else world_state.get('slots', {}).get('destination')
            if destination:
                compact['slots']['destination'] = {
                    'lat': destination.get('lat'),
                    'lng': destination.get('lng'),
                    'name': destination.get('name')
                }
        except Exception:
            pass

        # lastWeather: normalize common key names to ensure executor sees temp/summary/humidity/wind
        compact['weather'] = None
        try:
            ctx = getattr(world_state, 'context', {}) if hasattr(world_state, 'context') else world_state.get('context', {})
            lastw = ctx.get('lastWeather') if isinstance(ctx, dict) else None
            if lastw:
                # temperature: try several common keys
                temp = lastw.get('temp') if isinstance(lastw, dict) else None
                if temp is None:
                    temp = lastw.get('temperature')
                if temp is None:
                    # some tools nest temperature under 'raw' or other structures
                    try:
                        temp = lastw.get('raw', {}).get('temperature')
                    except Exception:
                        temp = None

                # summary/conditions
                summary = lastw.get('summary') if isinstance(lastw, dict) else None
                if not summary:
                    summary = lastw.get('conditions')
                if not summary:
                    try:
                        summary = lastw.get('raw', {}).get('weatherCondition', {}).get('description', {}).get('text')
                    except Exception:
                        summary = None

                # humidity
                humidity = lastw.get('humidity') if isinstance(lastw, dict) else None
                if humidity is None:
                    humidity = lastw.get('relativeHumidity')
                if humidity is None:
                    try:
                        humidity = lastw.get('raw', {}).get('relativeHumidity')
                    except Exception:
                        humidity = None

                # wind speed: try direct key or nested under wind.speed.value
                wind_speed = lastw.get('wind_speed') if isinstance(lastw, dict) else None
                if wind_speed is None:
                    try:
                        wind = lastw.get('wind', {})
                        if isinstance(wind, dict):
                            # check nested structures
                            ws = wind.get('speed')
                            if isinstance(ws, dict):
                                wind_speed = ws.get('value') or ws.get('speed')
                            else:
                                wind_speed = ws
                    except Exception:
                        wind_speed = None

                compact['weather'] = {
                    'temp': temp,
                    'summary': summary,
                    'humidity': humidity,
                    'wind_speed': wind_speed
                }
        except Exception:
            pass

        # reverse geocode formatted address
        compact['address'] = None
        try:
            rev = ctx.get('reverse_geocode_result', {}) if isinstance(ctx, dict) else {}
            compact['address'] = rev.get('formatted_address')
        except Exception:
            pass

        # Transit and walking directions
        compact['transit_directions'] = None
        compact['walking_directions'] = None
        try:
            compact['transit_directions'] = ctx.get('transit_directions')
            compact['walking_directions'] = ctx.get('walking_directions')
        except Exception:
            pass

        # Plan summary: status and number of steps
        compact['plan'] = {'status': None, 'steps': 0, 'completed_steps': 0}
        try:
            plan = ctx.get('plan', {}) if isinstance(ctx, dict) else {}
            compact['plan']['status'] = plan.get('status')
            compact['plan']['steps'] = len(plan.get('steps', []) or [])
            compact['plan']['completed_steps'] = len(ctx.get('completed_steps', []) or [])
        except Exception:
            pass

        # Errors
        try:
            compact['errors'] = getattr(world_state, 'errors', None) if hasattr(world_state, 'errors') else world_state.get('errors', [])
        except Exception:
            compact['errors'] = []

        return compact
    except Exception:
        return {}