resource "aws_db_subnet_group" "sis" {
  name       = "${var.project}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
  tags       = { Name = "${var.project}-db-subnets" }
}

resource "aws_db_instance" "sis" {
  identifier     = "${var.project}-postgres"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 5 # storage autoscaling headroom
  storage_type          = "gp3"
  storage_encrypted     = true

  db_subnet_group_name   = aws_db_subnet_group.sis.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  multi_az               = true # standby in the second AZ for failover
  publicly_accessible    = false

  backup_retention_period = 7
  deletion_protection     = false # set true for production
  skip_final_snapshot     = true  # set false + final_snapshot_identifier for production

  tags = { Name = "${var.project}-postgres" }
}
