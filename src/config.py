import os
import logging
from typing import List
from kubernetes.config import load_kube_config, load_incluster_config

# Configure logging with timestamp information
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load the delay time from an environment variable or use the default value
DELAY_AFTER_READY: int = int(os.getenv("DELAY_AFTER_READY", 10))

# Define labels or names for CastAI critical pods, either from an environment variable or a default list
CRITICAL_WORKLOADS: List[str] = os.getenv(
    "CRITICAL_WORKLOADS",
    "app.kubernetes.io/name=castai-agent,app.kubernetes.io/name=castai-cluster-controller"
).split(",")

# Define the minimum number of ready nodes required before draining critical nodes
MIN_READY_NODES: int = int(os.getenv("MIN_READY_NODES", 1))

def load_config() -> None:
    logging.info("Loading Kubernetes configuration...")
    try:
        load_incluster_config()
        logging.info("Loaded in-cluster config.")
    except:
        load_kube_config()
        logging.info("Loaded local kube config.")