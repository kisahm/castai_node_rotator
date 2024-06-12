import os
import time
import uuid
from datetime import datetime, timezone
from typing import Tuple, Optional, List

from kubernetes import client, config
from kubernetes.client import V1DeleteOptions, AppsV1Api, CoreV1Api, CoreV1Event, V1ObjectReference, V1EventSource, \
    V1Pod, V1Node
from kubernetes.config import load_kube_config, load_incluster_config
from kubernetes.client.rest import ApiException

# Load the delay time from an environment variable or use the default value
DELAY_AFTER_READY: int = int(os.getenv("DELAY_AFTER_READY", 10))

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
        Optional[CoreV1Event]: The created event object or None if creation failed.
    """

    # Generate a unique name for the event using uuid
    event_name: str = str(uuid.uuid4())

    # Get the current time in UTC
    event_time: datetime = datetime.now(timezone.utc)

    event = CoreV1Event(
        metadata=client.V1ObjectMeta(name=event_name, namespace=namespace),
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
        print(f"Event created: {response}")
        return response
    except ApiException as e:
        print(f"Exception when calling CoreV1Api->create_namespaced_event: {e}")
        return None


def load_config() -> None:
    print("Loading Kubernetes configuration...")
    try:
        load_incluster_config()
        print("Loaded in-cluster config.")
    except:
        load_kube_config()
        print("Loaded local kube config.")


def get_cast_ai_nodes(v1: CoreV1Api) -> List[V1Node]:
    print("Retrieving CAST AI managed nodes...")
    nodes: List[V1Node] = v1.list_node(label_selector="provisioner.cast.ai/managed-by=cast.ai").items
    print(f"Found {len(nodes)} CAST AI managed nodes.")
    return nodes


def cordon_node(v1: CoreV1Api, node_name: str) -> None:
    print(f"Cordoning node: {node_name}...")
    body = {
        "spec": {
            "unschedulable": True
        }
    }
    try:
        v1.patch_node(node_name, body)
        print(f"Node {node_name} cordoned.")
    except ApiException as e:
        print(f"Error cordoning node {node_name}: {e}")


def check_controller_replicas(v1: CoreV1Api, node_name: str) -> Tuple[
    Optional[str], Optional[str], Optional[str], Optional[List[V1Pod]]]:
    print(f"Checking controller replicas on node: {node_name}...")
    pods: List[V1Pod] = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
    controllers: dict = {}
    for pod in pods:
        if pod.metadata.name.startswith("castai"):
            continue
        owner_references = pod.metadata.owner_references
        for owner in owner_references:
            key = (owner.kind, owner.name, pod.metadata.namespace)
            if key not in controllers:
                controllers[key] = []
            controllers[key].append(pod.metadata.name)

    for (kind, name, namespace), pod_names in controllers.items():
        controller_pods: List[V1Pod] = v1.list_namespaced_pod(namespace,
                                                              label_selector=f"app={name.split('-')[0]}").items
        all_pods_on_node: bool = all(pod.metadata.name in pod_names for pod in controller_pods)
        if all_pods_on_node and len(controller_pods) > 1:
            print(f"All replicas of {kind} {name} are on node {node_name}.")
            return kind, name, namespace, controller_pods

    print(f"No controllers found with all replicas on node {node_name}.")
    return None, None, None, None


def evict_pod(v1: CoreV1Api, pod: V1Pod) -> None:
    pod_name: str = pod.metadata.name
    namespace: str = pod.metadata.namespace
    print(f"Evicting pod: {pod_name} from namespace: {namespace}...")
    delete_options = V1DeleteOptions()
    try:
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace, body=delete_options)
        print(f"Pod {pod_name} evicted.")
    except ApiException as e:
        if e.status == 404:
            print(f"Pod {pod_name} not found, skipping eviction")
        else:
            print(f"Error evicting pod {pod_name}: {e}")


def wait_for_new_replica(v1: CoreV1Api, controller_name: str, namespace: str) -> None:
    print(f"Waiting for a new replica of {controller_name} to become ready...")
    while True:
        pods: List[V1Pod] = v1.list_namespaced_pod(namespace,
                                                   label_selector=f"app={controller_name.split('-')[0]}").items
        ready_pods = [pod for pod in pods if pod.status.phase == "Running" and any(
            condition.type == "Ready" and condition.status == "True" for condition in pod.status.conditions)]
        if len(ready_pods) > 0:
            print(f"A new replica of {controller_name} is ready and serving traffic.")
            return
        print(f"No new replica of {controller_name} is ready yet. Waiting...")
        time.sleep(5)


def drain_node(v1: CoreV1Api, node_name: str) -> None:
    print(f"Draining node: {node_name}...")
    pods: List[V1Pod] = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
    delete_options = V1DeleteOptions()
    for pod in pods:
        try:
            v1.delete_namespaced_pod(name=pod.metadata.name, namespace=pod.metadata.namespace, body=delete_options)
            print(f"Pod {pod.metadata.name} deleted.")
        except ApiException as e:
            print(f"Error draining pod {pod.metadata.name}: {e}")
    print(f"Node {node_name} drained.")


def is_node_running_critical_pods(v1: CoreV1Api, node_name: str) -> bool:
    pods: List[V1Pod] = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
    for pod in pods:
        for label in CRITICAL_WORKLOADS:
            label_key, label_value = label.split("=")
            if pod.metadata.labels.get(label_key) == label_value:
                return True
    return False


def wait_for_new_nodes(v1: CoreV1Api, original_nodes: List[str]) -> List[str]:
    print("Waiting for new nodes to become ready...")
    while True:
        nodes: List[V1Node] = v1.list_node().items
        new_nodes = [node.metadata.name for node in nodes if node.metadata.name not in original_nodes]
        ready_new_nodes = [node for node in nodes if node.metadata.name in new_nodes and all(
            condition.status == "True" for condition in node.status.conditions if condition.type == "Ready")]
        if len(ready_new_nodes) >= MIN_READY_NODES:
            print(
                f"Found {len(ready_new_nodes)} new ready nodes, which meets the required {MIN_READY_NODES} new ready nodes.")
            return [node.metadata.name for node in ready_new_nodes]
        print(f"Currently {len(ready_new_nodes)} new ready nodes. Waiting for new nodes to be ready...")
        time.sleep(10)


def process_node(v1: CoreV1Api, node_name: str) -> None:
    create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node cordon init", "castai-agent")
    cordon_node(v1, node_name)
    kind, name, namespace, controller_pods = check_controller_replicas(v1, node_name)
    if kind and name and namespace and controller_pods:
        for pod in controller_pods:
            evict_pod(v1, pod)
            wait_for_new_replica(v1, name, namespace)
    create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node drain start", "castai-agent")
    drain_node(v1, node_name)
    create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node drain completed",
                            "castai-agent")
    print(f"Node {node_name} drained successfully.")


def main() -> None:
    load_config()
    v1 = CoreV1Api()

    original_nodes: List[str] = [node.metadata.name for node in get_cast_ai_nodes(v1)]
    critical_nodes: List[str] = []
    non_critical_nodes: List[str] = []

    # Separate critical and non-critical nodes
    for node_name in original_nodes:
        if is_node_running_critical_pods(v1, node_name):
            critical_nodes.append(node_name)
        else:
            non_critical_nodes.append(node_name)

    # Process non-critical nodes first
    for node_name in non_critical_nodes:
        process_node(v1, node_name)

    # Wait for new nodes to be ready before processing critical nodes
    new_nodes = wait_for_new_nodes(v1, original_nodes)

    # Process critical nodes last
    for node_name in critical_nodes:
        if node_name in new_nodes:
            print(f"Skipping new node {node_name} during critical node processing.")
            continue
        process_node(v1, node_name)


if __name__ == "__main__":
    main()
