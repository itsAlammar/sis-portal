resource "aws_ecr_repository" "sis" {
  name                 = var.project
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = { Name = "${var.project}-ecr" }
}
