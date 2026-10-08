output "state_bucket" {
  description = "Bucket for the main root's state. Copy into ../backend.hcl."
  value       = aws_s3_bucket.tfstate.bucket
}

output "backend_hcl" {
  description = "Paste into infrastructure/terraform-aws/backend.hcl (gitignored). Region, encryption and locking are fixed in ../versions.tf."
  value       = <<-EOT
    bucket = "${aws_s3_bucket.tfstate.bucket}"
    key    = "antiek/main.tfstate"
  EOT
}

output "account_id" {
  value = data.aws_caller_identity.current.account_id
}
