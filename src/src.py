import os
import time
import uuid
from datetime import datetime, timezone
from typing import Tuple, Optional, List
import logging
import subprocess
import signal
import sys

from kubernetes import client, config
from kubernetes.client import V1DeleteOptions, AppsV1Api, CoreV1Api, CoreV1Event, V1ObjectMeta, V1ObjectReference, \
    V1EventSource, V1Pod, V1Node
from kubernetes.config import load_kube_config, load_incluster_config
from kubernetes.client.rest import ApiException

# Configure logging with timestamp information
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load the delay time from an environment variable or use the default value
DELAY_AFTER_READY: int = int(os.getenv("DELAY_AFTER_READY", 10))

def handle_sigterm(signum, frame):
    logging.info("Received SIGTERM. Exiting gracefully...")
    sys.exit(0)

# Register the signal handler for SIGTERM
signal.signal(signal.SIGTERM, handle_sigterm)

# Define labels or names for CastAI critical pods, either from an environment variable or a default list
CRITICAL_WORKLOADS: List[str] = os.getenv(
    "CRITICAL_WORKLOADS",
    "app.kubernetes.io/name=castai-agent,app.kubernetes.io/name=castai-cluster-controller"
).split(",")

# Define the minimum number of ready nodes required before draining critical nodes
MIN_READY_NODES: int = int(os.getenv("MIN_READY_NODES", 1))


def create_kubernetes_event(
        v1: CoreV1Api,
        kind: str,
        name: str,
        namespace: str,
        reason: str,
        message: str,
        component: str,
        action: str = "Update",
        type: str = "Normal"
) -> Optional[CoreV1Event]:
    """
    Create a Kubernetes event for a given resource (node or pod).

    Args:
        v1 (CoreV1Api): The CoreV1Api instance.
        kind (str): The kind of resource (e.g., "Node" or "Pod").
        name (str): The name of the resource.
        namespace (str): The namespace of the resource.
        reason (str): The reason for the event.
        message (str): The message for the event.
        component (str): The component that generated the event.
        action (str, optional): The action that led to the event. Defaults to "Update".
        type (str, optional): The type of event (e.g., "Normal" or "Warning"). Defaults to "Normal".

    Returns:
        Optional[V1Event]: The created event object or None if creation failed.
    """

    # Generate a unique name for the event using uuid
    event_name: str = str(uuid.uuid4())

    # Get the current time in UTC
    event_time: datetime = datetime.now(timezone.utc)

    event = CoreV1Event(
        metadata=V1ObjectMeta(name=event_name, namespace=namespace),
        involved_object=V1ObjectReference(
            kind=kind,
            name=name,
            namespace=namespace
        ),
        reason=reason,
        message=message,
        type=type,
        source=V1EventSource(component=component, host=os.getenv("HOSTNAME", "unknown")),
        event_time=event_time.isoformat(),
        first_timestamp=event_time,
        last_timestamp=event_time,
        reporting_component=component,
        reporting_instance=os.getenv("HOSTNAME", "unknown"),
        action=action
    )

    try:
        response = v1.create_namespaced_event(namespace, event)
        # logging.info(f"Event created: {response}")
        return response
    except ApiException as e:
        logging.error(f"Exception when calling CoreV1Api->create_namespaced_event: {e}")
        return None

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

def load_config() -> None:
    logging.info("Loading Kubernetes configuration...")
    try:
        load_incluster_config()
        logging.info("Loaded in-cluster config.")
    except:
        load_kube_config()
        logging.info("Loaded local kube config.")


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


def check_controller_replicas(v1: CoreV1Api, node_name: str) -> Tuple[
    Optional[str], Optional[str], Optional[str], Optional[List[V1Pod]]]:
    logging.info(f"Checking controller replicas on node: {node_name}...")
    pods: List[V1Pod] = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
    controllers: dict = {}
    for pod in pods:
        owner_references = pod.metadata.owner_references or []
        for owner in owner_references:
            key = (owner.kind, owner.name, pod.metadata.namespace)
            if key not in controllers:
                controllers[key] = []
            controllers[key].append(pod)

    for (kind, name, namespace), controller_pods in controllers.items():
        if len(controller_pods) > 1:
            controller_pod_names = [pod.metadata.name for pod in controller_pods]
            label_selector = ",".join([f"{key}={value}" for key, value in controller_pods[0].metadata.labels.items()])
            all_controller_pods: List[V1Pod] = v1.list_namespaced_pod(namespace, label_selector=label_selector).items
            all_pods_on_node = all(pod in controller_pods for pod in all_controller_pods)
            if all_pods_on_node:
                logging.info(f"All replicas of {kind} {name} are on node {node_name}.")
                return kind, name, namespace, controller_pods

    logging.info(f"No controllers found with all replicas on node {node_name}.")
    return None, None, None, None


def evict_pod(v1: CoreV1Api, pod: V1Pod) -> None:
    pod_name: str = pod.metadata.name
    namespace: str = pod.metadata.namespace
    logging.info(f"Evicting pod: {pod_name} from namespace: {namespace}...")
    delete_options = V1DeleteOptions()
    try:
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace, body=delete_options)
        logging.info(f"Pod {pod_name} evicted.")
    except ApiException as e:
        if e.status == 404:
            logging.error(f"Pod {pod_name} not found, skipping eviction")
        else:
            logging.error(f"Error evicting pod {pod_name}: {e}")

# Not used for now
def wait_for_new_replica(v1: CoreV1Api, controller_name: str, namespace: str) -> None:
    logging.info(f"Waiting for a new replica of {controller_name} to become ready...")
    while True:
        pods: List[V1Pod] = v1.list_namespaced_pod(namespace, label_selector=f"app={controller_name.split('-')[0]}").items
        ready_pods = [pod for pod in pods if pod.status.phase == "Running" and any(
            condition.type == "Ready" and condition.status == "True" for condition in pod.status.conditions)]
        if len(ready_pods) > 0:
            logging.info(f"A new replica of {controller_name} is ready and serving traffic.")
            return
        logging.info(f"No new replica of {controller_name} is ready yet. Waiting...")
        time.sleep(5)



def wait_for_none_pending(v1: CoreV1Api, controller_name: str, namespace: str) -> None:
    still_pending = True
    controller_prefix = controller_name.split('-')[0]

    while still_pending:
        pending_pods = v1.list_namespaced_pod(
            namespace=namespace,
            field_selector="status.phase=Pending",
            label_selector=f"app={controller_prefix}"
        ).items
        if len(pending_pods) == 0:
            logging.info(f"No more pending pods for {controller_prefix}.")
            still_pending = False
        else:
            logging.info(f"Still pending pods for {controller_prefix}. Waiting...")
            time.sleep(5)


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
    while total_wait_cycles > 0:
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


def process_node(v1: CoreV1Api, node_name: str) -> None:
    logging.info(f"Processing node: {node_name}...")

    create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node cordon init", "castai-agent")
    cordon_node(v1, node_name)

    # The check_controller_replicas function is used to identify if all replicas of a controller 
    # are running on a single node. It returns the controller’s kind, name, namespace, and the 
    # list of pods if such a controller is found. If no such controller is found, it returns None values. 
    # This function is useful for scenarios where you need to ensure that controller replicas are 
    # distributed across different nodes to avoid single points of failure.
    while True:
        kind, name, namespace, controller_pods = check_controller_replicas(v1, node_name)
        if kind and name and namespace and controller_pods:
            # we want to evict the first pod in the list of controller_pods (not all of them)
            pod = controller_pods[0]
            logging.info(f"about to evict pod {pod.metadata.name} from namespace {namespace}")
            evict_pod(v1, pod)
            wait_for_none_pending(v1, name, namespace)
        else:
            logging.info(f"Breaking from check controllers loop.")
            break

    create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node drain start", "castai-agent")
    drain_node(v1, node_name)
    create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node drain completed", "castai-agent")
    logging.info(f"Node {node_name} drained successfully.")



def main() -> None:
    logging.info("************************************************")
    logging.info("Starting node rotator...")
    logging.info("************************************************")

    # check an environment variable for startup sleep time, default 20 seconds
    startup_sleep_time = int(os.getenv("STARTUP_SLEEP_TIME", 20))
    delay_wait_pending_pods = int(os.getenv("DELAY_WAIT_PENDING_PODS", 20))

    logging.info(f"Sleeping for {startup_sleep_time} seconds before starting node rotation.")
    time.sleep(startup_sleep_time)

    load_config()
    v1 = CoreV1Api()

    # Get the node name for the running cron job pod
    cron_job_pod_substring = "castai-node-drainer"  # Replace with the desired substring
    cron_job_node_name = get_node_for_running_pod(v1, cron_job_pod_substring)
    logging.info(f" cronjob node {cron_job_node_name}")

    original_nodes: List[str] = [node.metadata.name for node in get_cast_ai_nodes(v1)]
    critical_nodes: List[str] = []
    non_critical_nodes: List[str] = []

    logging.info(f"CAST AI Managed nodes: {original_nodes}")

    # Separate critical and non-critical nodes
    for node_name in original_nodes:
        if is_node_running_critical_pods(v1, node_name):
            critical_nodes.append(node_name)
        else:
            non_critical_nodes.append(node_name)

    # Remove the cron job node from critical and non-critical node lists, as the cron job node should be processed last
    critical_nodes, non_critical_nodes = remove_cron_job_node(cron_job_node_name, critical_nodes, non_critical_nodes)

    logging.info(f"Critical nodes: {critical_nodes}")
    logging.info(f"Non-critical nodes: {non_critical_nodes}")

    # Process non-critical nodes first
    for node_name in non_critical_nodes:
        process_node(v1, node_name)

    #logging.info("Pausing just after processing non-critical nodes...")
    #input()
    time.sleep(delay_wait_pending_pods)

    # Check for Pending pods to determine if we need to wait for new nodes
    pending_pods = v1.list_pod_for_all_namespaces(field_selector="status.phase=Pending").items
    # iterate through pendiing_pods and log the name
    for pod in pending_pods:
        logging.info(f"Pending pod: {pod.metadata.name}")
    
    new_nodes = [] # List of new nodes that have become ready
    if len(pending_pods) > 0:
        logging.info(f"Found {len(pending_pods)} Pending pods. Waiting for new nodes to be ready...")
        # Wait for new nodes to be ready before processing critical nodes
        new_nodes = wait_for_new_nodes(v1, original_nodes)
    else:
        logging.info("No Pending pods found. Continuing.")

    logging.info(f"Processing critical nodes... {critical_nodes}")

    # Process critical nodes last
    for node_name in critical_nodes:
        if node_name in new_nodes:
            logging.info(f"Skipping new node {node_name} during critical node processing.")
            continue
        process_node(v1, node_name)

    # If the cron job node is not processed yet, process it last
    # if cron_job_node_name :
    #     logging.info(f"Processing cronjob node {cron_job_node_name}")
    #     process_node(v1, cron_job_node_name)

    logging.info("Node rotation completed successfully.")
    exit(0)


if __name__ == "__main__":
    main()
