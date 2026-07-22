# Secrets live in SSM Parameter Store (SecureString) and are injected into the
# container at launch — never baked into the image or the task definition text.
resource "aws_ssm_parameter" "database_url" {
  name  = "/${var.project}/DATABASE_URL"
  type  = "SecureString"
  value = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.sis.address}:5432/${var.db_name}"
}

resource "aws_ssm_parameter" "secret_key" {
  name  = "/${var.project}/SIS_SECRET_KEY"
  type  = "SecureString"
  value = var.sis_secret_key
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: pulls the image and reads the secrets to start the task.
resource "aws_iam_role" "execution" {
  name               = "${var.project}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "read_secrets" {
  statement {
    actions   = ["ssm:GetParameters"]
    resources = [aws_ssm_parameter.database_url.arn, aws_ssm_parameter.secret_key.arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${var.project}-read-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.read_secrets.json
}

# Task role: the app's own runtime identity (empty for now; extend if the app
# later talks to S3 for document storage, SES for email, etc.).
resource "aws_iam_role" "task" {
  name               = "${var.project}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}
