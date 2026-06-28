variable "region" {
  type        = string
  description = "Región AWS de residencia de datos (ADR-0006)."
  default     = "sa-east-1"
}

variable "account_id" {
  type        = string
  description = "ID de cuenta AWS (12 dígitos)."
  default     = "772032166382"

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id debe ser un ID de cuenta AWS de 12 dígitos."
  }
}

variable "project" {
  type        = string
  description = "Prefijo de nombres de recursos."
  default     = "respuesta"
}

variable "github_repo" {
  type        = string
  description = "Repo owner/name autorizado a consumir las credenciales del pipeline (documental)."
  default     = "jeremialcala/proyecto-respuesta"
}

variable "external_id" {
  type        = string
  description = <<-EOT
    ExternalId compartido entre el usuario CI y los roles de provisioning.
    Defensa en profundidad: una access key filtrada NO basta para asumir los
    roles sin este valor. Genera uno aleatorio: `openssl rand -hex 16`.
  EOT
  sensitive   = true
}
