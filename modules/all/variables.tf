variable "namespace" {
  default     = "namespace"
  type        = string
  description = "Defines a namespace value which will become the prefix for all AWS resources."
}

variable "project" {
  default     = "project"
  type        = string
  description = "Sets the projects name for the project which all of the AWS resources will belong to."
}

variable "environment" {
  type        = string
  description = "Sets a logical environment name. AWS resources using the same environment will work together."
}

variable "sftp_push_default_user_public_key" {
  default     = ""
  type        = string
  description = "Sets the SSH public key for the default user in our SFTP push server."
}

variable "cidr" {
  default     = "10.0.0.0/16"
  type        = string
  description = "Defines the CIDR subnet for the VPC."
}

variable "peers_config" {
  type = list(
    object(
      {
        id                                = string
        name                              = string
        method                            = string
        type                              = optional(string)
        hostname                          = optional(string)
        host-sha256-fingerprints          = optional(list(string), [])
        # List of expected SHA256 fingerprints for SFTP host verification
        # SECURITY: Empty list allows connections to any host (insecure for production)
        # Example: ["SHA256:nThbg6kXUpJWGl7E1IGOCspRomTxdCARLviKw6E5SY8"]
        port                              = optional(number)
        username                          = optional(string)
        folder                            = optional(string)
        schedule                          = optional(string)
        alert_window                      = optional(string)
        alert_threshold                   = optional(string)
        add-timestamp-to-downloaded-files = optional(bool)
        ssh-public-key                    = optional(string)
        config                            = optional(
          object({
            wise = optional(
              object({
                profile = string
                sub_accounts = list(string)
                events = object({
                  enabled = bool
                })  
              })  
            )
            arch = optional(
              object({
                entities = list(
                  object({
                    name     = string
                    resource = string
                    limit    = optional(number)
                    enabled  = bool
                  })
                )
              })
            )
          })
        ),
        categories                        = optional(
          list(
            object({
              category_id = string
              filename_patterns = list(string)
              transformations = optional(list(string))
            })
          ),
          []
        )
      }
    )
  )
  description = "Defines the peers"

  validation {
    condition = alltrue([
      for peer in var.peers_config : (
        try(peer.method, null) == null ? true : contains(["pull", "push", "email", "manual", "api"], peer.method)
      )
    ])

    error_message = "If set, 'method' must be one of: \"pull\", \"push\", \"email\", \"manual\", or \"api\"."
  }

  validation {
    condition = alltrue([
      for peer in var.peers_config : (
        alltrue([
          for category in try(peer.categories, []) : (
            try(category.transformations, null) == null ? true : alltrue([
              for t in category.transformations : contains([
                "RemoveNewlinesInCsvFieldsTransformer"
              ], t)
            ])
          )
        ])
      )
    ])

    error_message = "Each transformation in categories must be one of: \"RemoveNewlinesInCsvFieldsTransformer\"."
  }
}

variable "features" {
  type = object({
    push_server = object({
      enabled = optional(string, true)
      lock_elastic_ip = optional(string, true) 
    })
    s3 = object({
      can_be_deleted_if_not_empty = optional(string, false) 
      create_backups = optional(string, true)
    })
  })
  default = {
    push_server = {
      enabled = true 
      lock_elastic_ip = true
    }
    s3 = {
      can_be_deleted_if_not_empty = false
      create_backups = true
    }
  }
  description = "Defines which features should be enabled."
}
