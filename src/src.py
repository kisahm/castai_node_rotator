import os
import time
import kubernetes.client
from kubernetes.client import V1DeleteOptions, AppsV1Api, CoreV1Api
from kubernetes.config import load_kube_config, load_incluster_config
from kubernetes.client.rest import ApiException

# Load the delay time from an environment variable or use the default value
DELAY_AFTER_READY = int(os.getenv("DELAY_AFTER_READY", 10))


def load_config():
    print("Loading Kubernetes configuration...")
    try:
        load_incluster_config()
        print("Loaded in-cluster config.")
    except:
        load_kube_config()
        print("Loaded local kube config.")


def get_cast_ai_nodes(v1):
    print("Retrieving CAST AI managed nodes...")
    nodes = v1.list_node(label_selector="provisioner.cast.ai/managed-by=cast.ai").items
    print(f"Found {len(nodes)} CAST AI managed nodes.")
    return nodes


def cordon_node(v1, node_name):
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


def check_controller_replicas(v1, node_name):
    print(f"Checking controller replicas on node: {node_name}...")
    pods = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
    controllers = {}
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
        controller_pods = v1.list_namespaced_pod(namespace, label_selector=f"app={name.split('-')[0]}").items
        all_pods_on_node = all(pod.metadata.name in pod_names for pod in controller_pods)
        if all_pods_on_node and len(controller_pods) > 1:
            print(f"All replicas of {kind} {name} are on node {node_name}.")
            return kind, name, namespace, controller_pods

    print(f"No controllers found with all replicas on node {node_name}.")
    return None, None, None, None


def evict_pod(v1, pod):
    pod_name = pod.metadata.name
    namespace = pod.metadata.namespace
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


def wait_for_pod_health(v1, controller_pods):
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
                            return
            except ApiException as e:
                if e.status == 404:
                    print(f"Pod {pod.metadata.name} not found. It might have been evicted, continuing to wait")
                else:
                    print(f"Error checking pod status for {pod.metadata.name}: {e}")
        time.sleep(5)


def drain_node(v1, node_name):
    print(f"Draining node: {node_name}...")
    pods = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items
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


def main():
    load_config()
    v1 = CoreV1Api()
    apps_v1 = AppsV1Api()

    nodes = get_cast_ai_nodes(v1)
    for node in nodes:
        node_name = node.metadata.name
        cordon_node(v1, node_name)
        kind, name, namespace, controller_pods = check_controller_replicas(v1, node_name)
        if kind and name and namespace and controller_pods:
            evict_pod(v1, controller_pods[0])
            wait_for_pod_health(v1, controller_pods[1:])
        drain_node(v1, node_name)
        print(f"Node {node_name} drained successfully.")


if __name__ == "__main__":
    main()