terraform {
  cloud {
    organization = "littlewolfacres"
    workspaces {
      name = "monolith"
    }
  }
}

resource "null_resource" "k3s_bootstrap" {
  # This runs on Monolith via your GitHub Runner
  provisioner "local-exec" {
    command = <<EOT
      curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server \
        --write-kubeconfig-mode 644 \
        --etcd-expose-metrics true \
        --datastore-endpoint='path=/mnt/k8s-etcd'" sh -
    EOT
  }
}