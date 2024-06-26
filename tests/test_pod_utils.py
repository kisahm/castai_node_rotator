import unittest
from unittest.mock import MagicMock
from typing import List, Optional, Tuple
from kubernetes.client import CoreV1Api, V1Pod, V1PodList, V1ObjectMeta, V1OwnerReference
import sys
import os

# Add src directory to the system path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from pod_utils import check_controller_replicas

class TestPodUtils(unittest.TestCase):

    def test_check_controller_replicas_happy_path(self):
        v1 = MagicMock()
        node_name = "test-node"
        namespace = "default"

        # Create pods that match the controller replicas
        owner_reference = V1OwnerReference(api_version="v1", kind="ReplicaSet", name="test-controller", uid="123")
        pod1 = V1Pod(metadata=V1ObjectMeta(name="pod1", namespace=namespace, owner_references=[owner_reference], labels={"app": "test-app"}))
        pod2 = V1Pod(metadata=V1ObjectMeta(name="pod2", namespace=namespace, owner_references=[owner_reference], labels={"app": "test-app"}))
        pod_list = V1PodList(items=[pod1, pod2])

        v1.list_pod_for_all_namespaces.return_value = pod_list
        v1.list_namespaced_pod.return_value = pod_list

        result = check_controller_replicas(v1, node_name)
        self.assertEqual(result, ("ReplicaSet", "test-controller", namespace, [pod1, pod2]))

    def test_check_controller_replicas_no_pods(self):
        v1 = MagicMock()
        node_name = "test-node"

        # Create an empty list of pods
        pod_list = V1PodList(items=[])

        v1.list_pod_for_all_namespaces.return_value = pod_list

        result = check_controller_replicas(v1, node_name)
        self.assertEqual(result, (None, None, None, None))

    def test_check_controller_replicas_single_replica(self):
        v1 = MagicMock()
        node_name = "test-node"
        namespace = "default"

        # Create a pod with a single replica
        owner_reference = V1OwnerReference(api_version="v1", kind="ReplicaSet", name="test-controller", uid="123")
        pod = V1Pod(metadata=V1ObjectMeta(name="pod1", namespace=namespace, owner_references=[owner_reference], labels={"app": "test-app"}))
        pod_list = V1PodList(items=[pod])

        v1.list_pod_for_all_namespaces.return_value = pod_list

        result = check_controller_replicas(v1, node_name)
        self.assertEqual(result, (None, None, None, None))

    def test_check_controller_replicas_not_all_replicas_on_node(self):
        v1 = MagicMock()
        node_name = "test-node"
        namespace = "default"

        # Create pods that match the controller replicas
        owner_reference = V1OwnerReference(api_version="v1", kind="ReplicaSet", name="test-controller", uid="123")
        pod1 = V1Pod(metadata=V1ObjectMeta(name="pod1", namespace=namespace, owner_references=[owner_reference], labels={"app": "test-app"}))
        pod2 = V1Pod(metadata=V1ObjectMeta(name="pod2", namespace=namespace, owner_references=[owner_reference], labels={"app": "test-app"}))
        pod3 = V1Pod(metadata=V1ObjectMeta(name="pod3", namespace=namespace, owner_references=[owner_reference], labels={"app": "test-app"}))
        pod_list_node = V1PodList(items=[pod1, pod2])
        pod_list_all = V1PodList(items=[pod1, pod2, pod3])

        v1.list_pod_for_all_namespaces.return_value = pod_list_node
        v1.list_namespaced_pod.return_value = pod_list_all

        result = check_controller_replicas(v1, node_name)
        self.assertEqual(result, (None, None, None, None))

if __name__ == '__main__':
    unittest.main()