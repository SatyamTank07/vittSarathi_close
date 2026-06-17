def safe_float(val):
    """
    Safely convert a value to a float. 
    Returns None if the conversion fails or if the value is None.
    """
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def safe_int(val):
    """
    Safely convert a value to an integer.
    Returns None if the conversion fails or if the value is None.
    """
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
