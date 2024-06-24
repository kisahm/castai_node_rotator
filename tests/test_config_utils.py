import unittest
import os
import sys
from unittest.mock import patch
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from config import get_env_int


class TestGetEnvInt(unittest.TestCase):

    @patch.dict(os.environ, {}, clear=True)
    def test_env_var_not_set(self):
        self.assertEqual(get_env_int("TEST_VAR", 42), 42)

    @patch.dict(os.environ, {"TEST_VAR": "100"}, clear=True)
    def test_env_var_set_to_valid_int(self):
        self.assertEqual(get_env_int("TEST_VAR", 42), 100)

    @patch.dict(os.environ, {"TEST_VAR": ""}, clear=True)
    def test_env_var_set_to_empty_string(self):
        self.assertEqual(get_env_int("TEST_VAR", 42), 42)

    @patch.dict(os.environ, {"TEST_VAR": "   "}, clear=True)
    def test_env_var_set_to_whitespace_string(self):
        self.assertEqual(get_env_int("TEST_VAR", 42), 42)

    @patch.dict(os.environ, {"TEST_VAR": "invalid"}, clear=True)
    def test_env_var_set_to_non_int(self):
        self.assertEqual(get_env_int("TEST_VAR", 42), 42)

    @patch.dict(os.environ, {"TEST_VAR": "42.5"}, clear=True)
    def test_env_var_set_to_float_string(self):
        self.assertEqual(get_env_int("TEST_VAR", 42), 42)


if __name__ == '__main__':
    unittest.main()
