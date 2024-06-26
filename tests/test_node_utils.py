import sys, os
import unittest
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone
from kubernetes.client import V1Node, V1ObjectMeta, V1Pod, V1PodList, V1NodeList

# Add src directory to the system path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from node_utils import is_node_older_than
from node_utils import is_node_running_critical_pods
from node_utils import get_cast_ai_nodes

# Mock the CRITICAL_WORKLOADS to match the tests
CRITICAL_WORKLOADS = ["app.kubernetes.io/name=castai-agent", "app.kubernetes.io/name=castai-cluster-controller"]

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

    def test_is_node_older_than_zero_days(self):
        # Create a node with a creation timestamp of today
        creation_timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
        node = V1Node(metadata=V1ObjectMeta(creation_timestamp=creation_timestamp))
        result = is_node_older_than(node, 0)
        self.assertTrue(result, "Node tested against zero days should return True")

    def test_is_node_running_critical_pods_true(self):
        # Mock the CoreV1Api instance and its list_pod_for_all_namespaces method
        v1 = MagicMock()
        node_name = "test-node"
        
        # Create a pod that matches the critical workloads
        pod = V1Pod(metadata=V1ObjectMeta(labels={"app.kubernetes.io/name": "castai-agent"}))
        pod_list = V1PodList(items=[pod])
        
        v1.list_pod_for_all_namespaces.return_value = pod_list

        # Test the function
        result = is_node_running_critical_pods(v1, node_name)
        self.assertTrue(result, "Node running critical pod should return True")

    def test_is_node_running_critical_pods_false(self):
        # Mock the CoreV1Api instance and its list_pod_for_all_namespaces method
        v1 = MagicMock()
        node_name = "test-node"
        
        # Create a pod that does not match the critical workloads
        pod = V1Pod(metadata=V1ObjectMeta(labels={"app.kubernetes.io/name": "non-critical-app"}))
        pod_list = V1PodList(items=[pod])
        
        v1.list_pod_for_all_namespaces.return_value = pod_list

        # Test the function
        result = is_node_running_critical_pods(v1, node_name)
        self.assertFalse(result, "Node not running critical pod should return False")

    def test_is_node_running_critical_pods_empty(self):
        # Mock the CoreV1Api instance and its list_pod_for_all_namespaces method
        v1 = MagicMock()
        node_name = "test-node"
        
        # Create an empty pod list
        pod_list = V1PodList(items=[])
        
        v1.list_pod_for_all_namespaces.return_value = pod_list

        # Test the function
        result = is_node_running_critical_pods(v1, node_name)
        self.assertFalse(result, "Node with no pods should return False")

    def test_get_cast_ai_nodes_positive(self):
        # Mock the CoreV1Api instance and its list_node method
        v1 = MagicMock()
        
        # Create a list of nodes that match the CAST AI managed label
        node1 = V1Node(metadata=V1ObjectMeta(name="node1"))
        node2 = V1Node(metadata=V1ObjectMeta(name="node2"))
        node_list = V1NodeList(items=[node1, node2])
        
        v1.list_node.return_value = node_list

        # Test the function
        result = get_cast_ai_nodes(v1)
        
        # Verify the label selector was used
        v1.list_node.assert_called_with(label_selector="provisioner.cast.ai/managed-by=cast.ai")
        
        # Verify the result
        self.assertEqual(len(result), 2, "Should return 2 nodes")
        self.assertEqual(result[0].metadata.name, "node1", "First node name should be 'node1'")
        self.assertEqual(result[1].metadata.name, "node2", "Second node name should be 'node2'")

    def test_get_cast_ai_nodes_negative(self):
        # Mock the CoreV1Api instance and its list_node method
        v1 = MagicMock()
        
        # Create an empty list of nodes
        node_list = V1NodeList(items=[])
        
        v1.list_node.return_value = node_list

        # Test the function
        result = get_cast_ai_nodes(v1)
        
        # Verify the label selector was used
        v1.list_node.assert_called_with(label_selector="provisioner.cast.ai/managed-by=cast.ai")
        
        # Verify the result
        self.assertEqual(len(result), 0, "Should return 0 nodes")

if __name__ == '__main__':
    unittest.main()