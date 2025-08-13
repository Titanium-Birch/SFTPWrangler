resource "aws_vpc" "default" {
  cidr_block            = var.cidr
  enable_dns_hostnames  = true
  tags                  = { Name = "${local.resource_prefix}-vpc" }
}

resource "aws_subnet" "public" {
  cidr_block              = cidrsubnet(aws_vpc.default.cidr_block, 8, 1)
  availability_zone       = data.aws_availability_zones.available.names[0]
  vpc_id                  = aws_vpc.default.id
  map_public_ip_on_launch = true
  tags                    = { Name = "${local.resource_prefix}-public" }
}

resource "aws_internet_gateway" "default" {
  vpc_id = aws_vpc.default.id
  tags = { Name = local.resource_prefix }
}

resource "aws_route" "internet_access" {
  route_table_id         = aws_vpc.default.main_route_table_id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.default.id
}

resource "aws_route_table_association" "public" {
  subnet_id       = aws_subnet.public.id
  route_table_id  = aws_vpc.default.main_route_table_id
}

resource "aws_security_group" "sftp" {
  name        = local.resource_prefix
  description = "controls access to our SFTP server"
  vpc_id      = aws_vpc.default.id
  tags        = { Name = "${local.resource_prefix}-sftp" }

  ingress {
    protocol    = "tcp"
    from_port   = 22
    to_port     = 22
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}