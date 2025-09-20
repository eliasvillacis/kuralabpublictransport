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