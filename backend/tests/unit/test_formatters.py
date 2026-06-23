import pytest
from src.utils.formatters import safe_float, safe_int

def test_safe_float_with_valid_string():
    assert safe_float("42.5") == 42.5

def test_safe_float_with_valid_integer():
    assert safe_float(42) == 42.0

def test_safe_float_with_none():
    assert safe_float(None) is None

def test_safe_float_with_invalid_text():
    assert safe_float("invalid") is None

def test_safe_int_with_valid_string():
    assert safe_int("42") == 42

def test_safe_int_with_float_string():
    # int("42.5") raises ValueError, so safe_int should return None
    assert safe_int("42.5") is None

def test_safe_int_with_none():
    assert safe_int(None) is None

def test_safe_int_with_invalid_text():
    assert safe_int("invalid") is None
