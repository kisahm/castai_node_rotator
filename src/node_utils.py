import time
from datetime import datetime, timezone, timedelta
import os
import logging
import subprocess
from typing import Tuple, Optional, List
from kubernetes.client import CoreV1Api, V1Node, ApiException, V1Pod
from config import CRITICAL_WORKLOADS, MIN_READY_NODES

def remove_cron_job_node(cron_job_node_name: Optional[str], critical_nodes: List[str], non_critical_nodes: List[str]) -> Tuple[List[str], List[str]]:
    """
    Removes the cron job node name from the critical and non-critical node lists.
    """
    if cron_job_node_name:
        if cron_job_node_name in critical_nodes:
            critical_nodes.remove(cron_job_node_name)
        if cron_job_node_name in non_critical_nodes:
            non_critical_nodes.remove(cron_job_node_name)
    return critical_nodes, non_critical_nodes

def get_cast_ai_nodes(v1: CoreV1Api) -> List[V1Node]:
    logging.info("Retrieving CAST AI managed nodes...")
    nodes: List[V1Node] = v1.list_node(label_selector="provisioner.cast.ai/managed-by=cast.ai").items
    logging.info(f"Found {len(nodes)} CAST AI managed nodes.")
    return nodes

def cordon_node(v1: CoreV1Api, node_name: str) -> None:
    logging.info(f"Cordoning node: {node_name}...")
    body = {
        "spec": {
            "unschedulable": True
        }
    }
    try:
        v1.patch_node(node_name, body)
        logging.info(f"Node {node_name} cordoned.")
    except ApiException as e:
        logging.error(f"Error cordoning node {node_name}: {e}")

def get_node_for_running_pod(v1: CoreV1Api, pod_name_substring: str) -> Optional[str]:
    """
    Returns the name of the node on which a pod with the given substring in its name is running.
    If no such running pod is found, returns None.
    """
    pods: List[V1Pod] = v1.list_pod_for_all_namespaces().items
    for pod in pods:
        if pod_name_substring in pod.metadata.name and pod.status.phase == "Running":
            return pod.spec.node_name
    return None

def drain_node(v1: CoreV1Api, node_name: str) -> None:
    try:
        logging.info(f"Draining node: {node_name}...")
        command = ["kubectl", "drain", node_name, "--ignore-daemonsets", "--delete-emptydir-data"]
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        logging.info(f"{result}.")
        logging.info(f"Node {node_name} drained.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error draining node {node_name}: {e}")

def is_node_running_critical_pods(v1: CoreV1Api, node_name: str) -> bool:
    pods: List[V1Pod] = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
    for pod in pods:
        for label in CRITICAL_WORKLOADS:
            label_key, label_value = label.split("=")
            if pod.metadata.labels.get(label_key) == label_value:
                return True
    return False

def wait_for_new_nodes(v1: CoreV1Api, original_nodes: List[str]) -> List[str]:
    total_wait_cycles = os.getenv("TOTAL_WAIT_CYCLES", 18)
    logging.info("Waiting for new nodes to become ready...")
    while int(total_wait_cycles) > 0:
        nodes: List[V1Node] = v1.list_node().items
        new_nodes = [node.metadata.name for node in nodes if node.metadata.name not in original_nodes]
        ready_new_nodes = [node for node in nodes if node.metadata.name in new_nodes and all(
            condition.status == "True" for condition in node.status.conditions if condition.type == "Ready")]
        if len(ready_new_nodes) >= MIN_READY_NODES:
            logging.info(
                f"Found {len(ready_new_nodes)} new ready nodes, which meets the required {MIN_READY_NODES} new ready nodes.")
            return [node.metadata.name for node in ready_new_nodes]
        logging.info(f"Currently {len(ready_new_nodes)} new ready nodes. Waiting for new nodes to be ready...")
        total_wait_cycles -= 1 # decrement the total_wait_cycles
        time.sleep(10)

def is_node_older_than(node: V1Node, days: int) -> bool:

    if days == 0:  # Node is always stale if zero days
        return True
    
    creation_timestamp = node.metadata.creation_timestamp
    age = datetime.now(timezone.utc) - creation_timestamp
    logging.error(f"Node age: {age}")
    logging.error(f"delta days: {timedelta(days=days)}")
    logging.error(f"age > timedelta(days=days + 1): {age > timedelta(days=days +1)}")
    return age > timedelta(days=days + 1)
