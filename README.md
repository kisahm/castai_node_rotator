# CAST AI Node Rotation Script

This project contains a Python script to rotate CAST AI managed nodes in a Kubernetes cluster. The script is responsible for cordoning, draining, and deleting nodes. It includes safeguards to ensure services are not disrupted, particularly when all replicas of a controller are on a single node.

## Features
(Current)
- Cordon nodes to prevent new pods from being scheduled.
- Check if all replicas of any controller reside on a single node.
- Evict one replica to another node if necessary, ensuring it becomes healthy and serves traffic.
- Drain nodes by safely evicting all remaining pods.

(Next):
- Log movements in Kubernetes events.
- Package the script using Docker and deploy as a Kubernetes CronJob.
- Create e2e tests to ensure the script works as expected.

## Getting Started

### Prerequisites

- Python 3.9 or higher
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
