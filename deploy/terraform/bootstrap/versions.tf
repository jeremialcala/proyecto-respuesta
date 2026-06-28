terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }

  # La capa bootstrap arranca con state LOCAL porque es quien CREA el backend
  # remoto (bucket S3 + tabla DynamoDB). Tras el primer `apply`, descomenta el
  # bloque de abajo y ejecuta `terraform init -migrate-state` para mover el
  # state a S3. Ver README.md.
  #
  # backend "s3" {
  #   bucket         = "respuesta-tfstate-772032166382"
  #   key            = "bootstrap/terraform.tfstate"
  #   region         = "sa-east-1"
  #   dynamodb_table = "respuesta-tf-lock"
  #   encrypt        = true
  #   kms_key_id     = "alias/respuesta-tfstate"
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
      Layer     = "bootstrap"
    }
  }
}
