output "prod_public_ip" {
  description = "Elastic IP of the prod host: the new value of the ANTIEK_PROD_HOST repository secret at cutover."
  value       = aws_eip.prod.public_ip
}

output "prod_instance_id" {
  value = aws_instance.prod.id
}

output "prod_ami_id" {
  description = "The AMI the prod host was launched from (later AMI changes are ignored)."
  value       = aws_instance.prod.ami
}

output "prod_arch" {
  value = var.prod_arch
}

output "prod_instance_type" {
  value = local.prod_instance_type
}

output "prod_data_volume_id" {
  description = "The volume mounted at /home/antiek/.antiek (by-id: nvme-Amazon_Elastic_Block_Store_<id without hyphen>)."
  value       = aws_ebs_volume.prod_data.id
}

output "prod_state_dir" {
  value = local.prod_state_dir
}

output "availability_zone" {
  description = "Pin this as availability_zone in terraform.tfvars after the first apply (README.md, Apply order)."
  value       = local.availability_zone
}

output "staging_hold_file" {
  description = "Delete on the prod host at cutover step T+12, never earlier."
  value       = local.staging_hold_file
}

output "lane_host_instance_ids" {
  value = aws_instance.lane_host[*].id
}

output "lane_host_names" {
  description = "Hostnames, which are also the Tailscale node names and the compute policy keys (hosts.nodes.<name>)."
  value       = local.lane_host_names
}

output "lane_host_compute_ssh" {
  description = "The `ssh:` value for each host's compute policy entry (the control account)."
  value       = [for n in local.lane_host_names : "${local.lane_host_control_user}@${n}"]
}

output "lane_host_helper_sha256" {
  description = "sha256 of the compute-lane-host each lane host was given (also the instance tag ComputeHelperSha256)."
  value       = var.lane_host_count > 0 ? filesha256(local.lane_host_helper_src) : null
}

output "lane_host_cap_usd" {
  description = "Instance-hour limit of the cap budget: the approved cap minus fixed EBS/IPv4 per host and the egress allowance."
  value       = var.lane_host_count > 0 ? format("%.2f", local.lane_host_cap_usd) : null
}

output "inventory_aws_ini_line" {
  description = "Host line for infrastructure/ansible/inventory.aws.ini."
  value       = "${var.prod_hostname} ansible_host=${aws_eip.prod.public_ip} ansible_user=root ansible_ssh_private_key_file=~/.ssh/antiek_ed25519"
}
