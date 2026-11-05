terraform {
  required_providers {
    coder = {
      source  = "coder/coder"
      version = "2.20.0"
    }
    docker = {
      source  = "kreuzwerker/docker"
      version = "4.6.0"
    }
  }
}
provider "docker" { host = "unix:///var/run/docker.sock" }
data "coder_provisioner" "me" {}
data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}

resource "coder_agent" "main" {
  arch = data.coder_provisioner.me.arch
  os = "linux"
  dir = "/home/coder/orderdesk"
  startup_script_behavior = "blocking"
  startup_script = <<-EOT
    #!/bin/bash
    set -euo pipefail
    if [ ! -d /home/coder/orderdesk ]; then
      cp -a /opt/orderdesk-seed /home/coder/orderdesk
      cd /home/coder/orderdesk
      git init -b main
      git add .
      git -c user.name="Lena Demo" -c user.email="lena@example.test" commit -m "Starting app: reproduce duplicate webhook orders"
      git tag demo-start
    fi
    cd /home/coder/orderdesk
    python3 demo.py start
    mkdir -p /home/coder/.local/share/code-server/User
    if [ ! -f /home/coder/.local/share/code-server/User/settings.json ]; then
      printf '%s' '{"workbench.colorTheme":"Default Dark Modern","editor.fontSize":16,"terminal.integrated.fontSize":16,"workbench.startupEditor":"none","telemetry.telemetryLevel":"off"}' > /home/coder/.local/share/code-server/User/settings.json
    fi
    code-server --auth none --bind-addr 127.0.0.1:13337 --disable-telemetry /home/coder/orderdesk > /home/coder/.code-server.log 2>&1 &
  EOT
  env = {
    GIT_AUTHOR_NAME = "Lena Demo"
    GIT_AUTHOR_EMAIL = "lena@example.test"
    GIT_COMMITTER_NAME = "Lena Demo"
    GIT_COMMITTER_EMAIL = "lena@example.test"
  }
}
resource "coder_app" "orders" {
  agent_id = coder_agent.main.id
  slug = "orderdesk"
  display_name = "OrderDesk"
  url = "http://localhost:8000"
  icon = "/icon/widgets.svg"
  subdomain = false
  share = "owner"
  healthcheck {
    url = "http://localhost:8000/healthz"
    interval = 5
    threshold = 6
  }
}
resource "coder_app" "editor" {
  agent_id = coder_agent.main.id
  slug = "code-server"
  display_name = "VS Code Web"
  url = "http://localhost:13337/?folder=/home/coder/orderdesk"
  icon = "/icon/code.svg"
  subdomain = false
  share = "owner"
  healthcheck {
    url = "http://localhost:13337/healthz"
    interval = 5
    threshold = 6
  }
}
resource "docker_volume" "home" {
  name = "lena-orderdesk-${data.coder_workspace.me.id}"
  labels {
    label = "lena.project"
    value = "coder-webhook-demo"
  }
}
resource "docker_container" "workspace" {
  count = data.coder_workspace.me.start_count
  image = "lena-orderdesk-workspace:2026-11-04"
  name = "lena-orderdesk-${lower(data.coder_workspace.me.name)}"
  hostname = "orderdesk"
  user = "1000:1000"
  entrypoint = ["sh", "-c", replace(coder_agent.main.init_script, "http://localhost:3000", "http://coder:7080")]
  env = ["CODER_AGENT_TOKEN=${coder_agent.main.token}"]
  networks_advanced { name = "lena-coder-demo" }
  volumes {
    container_path = "/home/coder"
    volume_name = docker_volume.home.name
  }
  labels {
    label = "lena.project"
    value = "coder-webhook-demo"
  }
}
