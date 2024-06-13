cat <<EOF > castai-node-drainer/templates/clusterrolebinding.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: castai-node-drainer
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: castai-node-drainer
subjects:
- kind: ServiceAccount
  name: castai-node-drainer
  namespace: castai-agent
EOF