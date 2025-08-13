locals {
  peers = [
    {
      id: "peer1",
      name: "Peer 1",
      method: "pull",
      hostname: "sftp.host.com",
      port: 22,
      username: "sftp_user",
      folder: "/files",
      schedule: "0 0 1 1 ? 2300"
    },
    {
      "id": "peer2",
      "name": "Peer 2",
      "method": "api",
      "schedule": "0/5 * ? * MON-FRI *",
      "config": {
        "wise": {
          "profile": "12345678",
          "sub_accounts": ["abc", "def"],
          "events": {
            "enabled": false
          }
        }
      }
    },
    {
      "id": "peer3",
      "name": "Peer 3",
      "method": "api",
      "schedule": "0/5 * ? * MON-FRI *",
      "config": {
        "arch": {
          "entities": [
            {
              "name": "Holdings",
              "resource": "holdings",
              "enabled": true
            },
            {
              "name": "Investing Entities",
              "resource": "investing-entities",
              "enabled": true
            },
            {
              "name": "Issuing Entities",
              "resource": "issuing-entities",
              "enabled": true
            },
            {
              "name": "Offerings",
              "resource": "offerings",
              "enabled": true
            },
            {
              "name": "Activities",
              "resource": "activities",
              "enabled": true
            },
            {
              "name": "Cash Flows",
              "resource": "cash-flows",
              "enabled": true
            },
            {
              "name": "Tasks",
              "resource": "tasks",
              "enabled": true
            }
          ]
        }
      }
    },
  ]
  features = {
    push_server: {
      enabled: true,
      lock_elastic_ip: false
    },
    s3: {
      can_be_deleted_if_not_empty: true,
      create_backups: true
    }
  }
}

resource "tls_private_key" "sftp_default_user" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

module "infrastructure" {
  source = "../../modules/all"

  environment                             = "development"
  sftp_push_default_user_public_key       = tls_private_key.sftp_default_user.public_key_openssh
  peers_config                            = local.peers
  features                                = local.features
}