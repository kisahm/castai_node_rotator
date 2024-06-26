import unittest
from unittest.mock import MagicMock, patch
from kubernetes.client import CoreV1Api, V1Pod, V1ObjectMeta
import subprocess
import sys
import os

# Add src directory to the system path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from node_utils import drain_node_with_timeout

class TestNodeDrain(unittest.TestCase):

    def test_drain_node_with_timeout_success(self):
        v1 = MagicMock()
        node_name = "test-node"
        timeout = 10

        # Mock subprocess.run to simulate successful drain
        with patch('subprocess.run', return_value=MagicMock()) as mock_subprocess:
            result = drain_node_with_timeout(v1, node_name, timeout)

            # Assert the function returns None on success
            self.assertIsNone(result)
            mock_subprocess.assert_called_once_with(
                ["kubectl", "drain", node_name, "--ignore-daemonsets", "--delete-emptydir-data"],
                check=True,
                text=True,
                capture_output=True,
                timeout=timeout
            )

    def test_drain_node_with_timeout_timeout(self):
        v1 = MagicMock()
        node_name = "test-node"
        timeout = 10

        # Simulate pods on the node
        pod1 = V1Pod(metadata=V1ObjectMeta(name="pod1", namespace="default"))
        pod2 = V1Pod(metadata=V1ObjectMeta(name="pod2", namespace="default"))
        v1.list_pod_for_all_namespaces.return_value.items = [pod1, pod2]

        # Mock subprocess.run to simulate timeout
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd="kubectl drain", timeout=timeout)):
            result = drain_node_with_timeout(v1, node_name, timeout)

            # Assert the function returns the list of pods on timeout
            self.assertEqual(result, [pod1, pod2])

    def test_drain_node_with_timeout_exception(self):
        v1 = MagicMock()
        node_name = "test-node"
        timeout = 10

        # Mock subprocess.run to simulate an exception
        with patch('subprocess.run', side_effect=subprocess.CalledProcessError(returncode=1, cmd="kubectl drain")):
            with self.assertRaises(subprocess.CalledProcessError):
                drain_node_with_timeout(v1, node_name, timeout)

if __name__ == '__main__':
    unittest.main()