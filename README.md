# CAST AI Node Rotation Script

This project contains a Python script to rotate CAST AI managed nodes in a Kubernetes cluster. The script is responsible for cordoning, draining, and deleting nodes. It includes safeguards to ensure services are not disrupted, particularly when all replicas of a controller are on a single node.

## Features
(Current)
- Cordon nodes to prevent new pods from being scheduled.
- Check if all replicas of any controller reside on a single node.
- Evict one replica to another node if necessary, ensuring it becomes healthy and serves traffic.
- Drain nodes by safely evicting all remaining pods.
- Drain timeout configurable
- Old nodes configurable in number of days
- Log movements in Kubernetes events.
- Package the script using Docker and deploy as a Kubernetes CronJob.

(Next):
- Unit test coverage
- Create e2e tests to ensure the script works as expected.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Docker
- Kubernetes cluster
- kubectl configured to interact with your Kubernetes cluster

### Installation

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/your-organization/your-repo.git
   cd your-repo
2. Set Up a Virtual Environment:

```bash

python3 -m venv venv
source venv/bin/activate
```
3. Install Dependencies:

```bash

pip install -r requirements.txt
```


##### helm

```bash

helm repo add castai-repo https://raw.githubusercontent.com/ronakforcast/castai_node_rotator/main/helmChart/castai-node-drainer
helm install castai-node-drainer-v2  castai-repo/castai-node-drainer
```

##### Terraform

To deploy the `castai-node-drainer` Helm chart using Terraform, you can utilize the `helm_release` resource provided by the Terraform Helm provider. Here are the steps:

1. **Install the Terraform Helm Provider**:

First, you need to install the Terraform Helm provider. You can do this by adding the following code to your Terraform configuration file:

```hcl
terraform {
  required_providers {
    helm = {
      source = "hashicorp/helm"
      version = "2.9.0" # or the latest version
    }
  }
}

provider "helm" {
  kubernetes {
    config_path = "~/.kube/config" # path to your Kubernetes cluster config file
  }
}
```

2. **Define the Helm Release Resource**:

Next, create a new Terraform configuration file (e.g., `main.tf`) and define the `helm_release` resource for your `castai-node-drainer` Helm chart:

```hcl
resource "helm_release" "castai-node-drainer" {
  name       = "castai-node-drainer"
  repository = "https://raw.githubusercontent.com/ronakforcast/castai_node_rotator/main/helmChart/castai-node-drainer"
  chart      = "castai-node-drainer"
  namespace  = "castai-agent"

  # Optionally, you can set values for the Helm chart
  set {
    name  = "cronjob.schedule"
    value = "0 0 * * 0"
  }

  set {
    name  = "container.image"
    value = "ronakpatildocker/castai-node-rotate"
  }

  # Add any other values as needed
}
```

In this example:

- `name`: Specifies the release name for the Helm chart deployment.
- `repository`: Specifies the URL of the Helm repository where the chart is located.
- `chart`: Specifies the name of the Helm chart to be deployed.
- `namespace`: Specifies the namespace where the chart should be deployed.
- `set`: Allows you to set values for the Helm chart. You can add multiple `set` blocks to configure different values.

3. **Initialize Terraform**:

Before applying the Terraform configuration, you need to initialize the Terraform working directory:

```
terraform init
```

4. **Plan and Apply the Terraform Configuration**:

Review the execution plan to see the changes Terraform will make:

```
terraform plan
```

If the plan looks good, apply the configuration to deploy the Helm chart:

```
terraform apply
```

Terraform will deploy the `castai-node-drainer` Helm chart to your Kubernetes cluster using the specified values.

5. **Verify the Deployment**:

You can verify the deployment by checking the Kubernetes resources created by the Helm chart:

```
kubectl get all -n castai-agent
```

You should see the CronJob, ServiceAccount, ClusterRole, and ClusterRoleBinding resources created by the Helm chart.

6. **Update or Destroy the Deployment**:

If you need to update the Helm chart deployment, make the necessary changes to the Terraform configuration file and run `terraform apply` again.

To destroy the Helm chart deployment, run:

```
terraform destroy
```

This will remove all the resources created by the Helm chart from your Kubernetes cluster.




### Highlevl WorkFlow

```
+-------------------------+
|         Start           |
+-------------------------+
            |
            | load_config()
            | # Loads Kubernetes configuration
            |
+-------------------------+
|    get_cast_ai_nodes()  |
| # Retrieves CAST AI managed nodes
+-------------------------+
            |
            | Separate Critical and Non-Critical Nodes
            | # Separates nodes into critical and non-critical lists
            |
+-------------------------+
|  remove_cron_job_node() |
| # Removes cron job node from critical/non-critical lists
+-------------------------+
            |
+-------------------------+
|   Process Non-Critical Nodes  |
+-------------------------+
            |
+-------------------------+
|      cordon_node()      |
| # Cordons the node to prevent new pod scheduling
+-------------------------+
            |
+-------------------------+
| check_controller_replicas()|
| # Checks for controllers with all replicas on the node
+-------------------------+
            |
+-------------------------+
|       evict_pod()       |
| # Evicts a pod if a controller with all replicas is found
+-------------------------+
            |
+-------------------------+
| wait_for_none_pending() |
| # Waits for new replicas to become ready (if any pods evicted)
+-------------------------+
            |
+-------------------------+
|       drain_node()      |
| # Drains the node to evict remaining pods
+-------------------------+
            |
            | Wait for Pending Pods (if any)
            | # Waits for pending pods (if any)
            |
+-------------------------+
|  wait_for_new_nodes()   |
| # Waits for new nodes to become ready
+-------------------------+
            |
+-------------------------+
|   Process Critical Nodes   |
+-------------------------+
            |
+-------------------------+
|      cordon_node()      |
| # Cordons the node to prevent new pod scheduling
+-------------------------+
            |
+-------------------------+
| check_controller_replicas()|
| # Checks for controllers with all replicas on the node
+-------------------------+
            |
+-------------------------+
|       evict_pod()       |
| # Evicts a pod if a controller with all replicas is found
+-------------------------+
            |
+-------------------------+
| wait_for_none_pending() |
| # Waits for new replicas to become ready (if any pods evicted)
+-------------------------+
            |
+-------------------------+
|       drain_node()      |
| # Drains the node to evict remaining pods
+-------------------------+
            |
+-------------------------+
|         End             |
+-------------------------+
```
