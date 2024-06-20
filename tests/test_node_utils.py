import sys, os
import unittest
from datetime import datetime, timedelta, timezone
from kubernetes.client import V1Node, V1ObjectMeta

# Add src directory to the system path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from node_utils import is_node_older_than

class TestNodeUtils(unittest.TestCase):

    def test_is_node_older_than_true(self):
        # Create a node with a creation timestamp older than 7 days
        creation_timestamp = datetime.now(timezone.utc) - timedelta(days=8)
        node = V1Node(metadata=V1ObjectMeta(creation_timestamp=creation_timestamp))
        result = is_node_older_than(node, 7)
        self.assertTrue(result, "Node older than 7 days should return True")

    def test_is_node_older_than_false(self):
        # Create a node with a creation timestamp less than 7 days
        creation_timestamp = datetime.now(timezone.utc) - timedelta(days=6)
        node = V1Node(metadata=V1ObjectMeta(creation_timestamp=creation_timestamp))
        result = is_node_older_than(node, 7)
        self.assertFalse(result, "Node younger than 7 days should return False")

    def test_is_node_older_than_exact(self):
        # Create a node with a creation timestamp exactly 7 days old
        creation_timestamp = datetime.now(timezone.utc) - timedelta(days=7)
        node = V1Node(metadata=V1ObjectMeta(creation_timestamp=creation_timestamp))
        result = is_node_older_than(node, 7)
        self.assertFalse(result, "Node exactly 7 days old should return False")

if __name__ == '__main__':
    unittest.main()