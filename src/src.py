import os
import time
import uuid
from datetime import datetime, timezone
from typing import Tuple, Optional, List

from kubernetes import client, config
from kubernetes.client import V1DeleteOptions, AppsV1Api, CoreV1Api, CoreV1Event, V1ObjectReference, V1EventSource, V1Pod, V1Node
from kubernetes.config import load_kube_config, load_incluster_config
from kubernetes.client.rest import ApiException

# Load the delay time from an environment variable or use the default value
DELAY_AFTER_READY: int = int(os.getenv("DELAY_AFTER_READY", 10))


def create_kubernetes_event(
    v1: CoreV1Api,
    kind: str,
    name: str,
    namespace: str,
    reason: str,
    message: str,
    component: Optional[str] = None,
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
        component (str, optional): The component that generated the event.
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
        source=V1EventSource(component=component) if component else None,
        event_time=event_time.isoformat(),
        first_timestamp=event_time.isoformat(),
        last_timestamp=event_time.isoformat()
    )

    try:
        response = v1.create_namespaced_event(namespace, event)
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


def check_controller_replicas(v1: CoreV1Api, node_name: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[List[V1Pod]]]:
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
        controller_pods: List[V1Pod] = v1.list_namespaced_pod(namespace, label_selector=f"app={name.split('-')[0]}").items
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


def wait_for_pod_health(v1: CoreV1Api, controller_pods: List[V1Pod]) -> None:
    print("Waiting for evicted pod to become healthy...")
    while True:
        for pod in controller_pods:
            try:
                pod_status = v1.read_namespaced_pod_status(pod.metadata.name, pod.metadata.namespace)
                if pod_status.status.phase == "Running" and pod_status.status.conditions:
                    for condition in pod_status.status.conditions:
                        if condition.type == "Ready" and condition.status == "True":
                            print(f"Pod {pod.metadata.name} is healthy and serving traffic.")
                            print(f"Waiting {DELAY_AFTER_READY} seconds after pod becomes ready before continuing.")
                            time.sleep(DELAY_AFTER_READY)
                            return
            except ApiException as e:
                if e.status == 404:
                    print(f"Pod {pod.metadata.name} not found. It might have been evicted, continuing to wait")
                else:
                    print(f"Error checking pod status for {pod.metadata.name}: {e}")
        time.sleep(5)


def drain_node(v1: CoreV1Api, node_name: str) -> None:
    print(f"Draining node: {node_name}...")
    pods: List[V1Pod] = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
    delete_options = V1DeleteOptions()
    for pod in pods:
        if pod.metadata.name.startswith("castai"):
            print(f"Skipping CAST AI pod: {pod.metadata.name}")
            continue
        try:
            v1.delete_namespaced_pod(name=pod.metadata.name, namespace=pod.metadata.namespace, body=delete_options)
            print(f"Pod {pod.metadata.name} deleted.")
        except ApiException as e:
            print(f"Error draining pod {pod.metadata.name}: {e}")
    print(f"Node {node_name} drained.")


def main() -> None:
    load_config()
    v1 = CoreV1Api()
    apps_v1 = AppsV1Api()

    nodes: List[V1Node] = get_cast_ai_nodes(v1)
    for node in nodes:
        node_name: str = node.metadata.name
        create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node cordon init", "castai-agent")
        cordon_node(v1, node_name)
        kind, name, namespace, controller_pods = check_controller_replicas(v1, node_name)
        if kind and name and namespace and controller_pods:
            evict_pod(v1, controller_pods[0])
            wait_for_pod_health(v1, controller_pods[1:])
        create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node drain start", "castai-agent")
        drain_node(v1, node_name)
        create_kubernetes_event(v1, "Node", node_name, "default", "CastNodeRotation", "Node drain completed", "castai-agent")
        print(f"Node {node_name} drained successfully.")


if __name__ == "__main__":
    main()
