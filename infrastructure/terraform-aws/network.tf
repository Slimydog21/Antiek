# ──────────────────────────────────────────────────────────────────────────────
# One VPC, one public subnet in one AZ, an internet gateway, no NAT gateway.
#
# Single-AZ is not an oversight: DuckDB is a single-writer file on one block
# device (runtime/db_lock.py), so prod is one instance in one AZ whatever the
# network looks like. The defence against losing the AZ is off-provider
# backups (R2 nightly) plus DLM snapshots, not a second subnet.
#
# No NAT gateway: instances egress through their own public IPv4. A NAT
# gateway adds an hourly charge plus per-GB processing on traffic in both
# directions, and prod pulls ~300 GB/month inbound (critic §3.1: ~USD 14/month
# of processing alone), where inbound through an internet gateway is free.
# Public IPv4 does not mean reachable: every security group below admits at
# most tcp/22 to prod and nothing at all to lane hosts.
# ──────────────────────────────────────────────────────────────────────────────

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ec2_instance_type_offerings" "by_az" {
  location_type = "availability-zone"

  filter {
    name   = "instance-type"
    values = distinct([local.prod_instance_type, var.lane_host_instance_type])
  }
}

locals {
  # AZs that offer every instance type this root may launch.
  azs_offering_all = sort([
    for az in data.aws_availability_zones.available.names : az
    if alltrue([
      for t in distinct([local.prod_instance_type, var.lane_host_instance_type]) :
      contains([
        for i, loc in data.aws_ec2_instance_type_offerings.by_az.locations : loc
        if data.aws_ec2_instance_type_offerings.by_az.instance_types[i] == t
      ], az)
    ])
  ])
  availability_zone = coalesce(var.availability_zone, try(local.azs_offering_all[0], null))
}

resource "aws_vpc" "this" {
  cidr_block                       = var.vpc_cidr
  enable_dns_support               = true
  enable_dns_hostnames             = true
  assign_generated_ipv6_cidr_block = var.enable_ipv6

  tags = { Name = "antiek" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "antiek" }
}

resource "aws_subnet" "public" {
  vpc_id                          = aws_vpc.this.id
  cidr_block                      = var.public_subnet_cidr
  availability_zone               = local.availability_zone
  map_public_ip_on_launch         = false
  ipv6_cidr_block                 = var.enable_ipv6 ? cidrsubnet(aws_vpc.this.ipv6_cidr_block, 8, 1) : null
  assign_ipv6_address_on_creation = var.enable_ipv6

  tags = { Name = "antiek-public-${local.availability_zone}" }

  lifecycle {
    precondition {
      condition     = local.availability_zone != null
      error_message = "No available AZ in ${var.region} offers every instance type in use (${join(", ", distinct([local.prod_instance_type, var.lane_host_instance_type]))}). Set availability_zone or change a type."
    }
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "antiek-public" }
}

resource "aws_route" "public_ipv4" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route" "public_ipv6" {
  count = var.enable_ipv6 ? 1 : 0

  route_table_id              = aws_route_table.public.id
  destination_ipv6_cidr_block = "::/0"
  gateway_id                  = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Every VPC gets a default security group that admits all traffic from its
# own members. Nothing here uses it; adopting it with no rules removes the
# chance of a console-launched instance landing in an allow-all group.
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "antiek-default-unused" }
}
