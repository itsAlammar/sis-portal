resource "aws_ecs_cluster" "sis" {
  name = "${var.project}-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "sis" {
  name              = "/ecs/${var.project}"
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "sis" {
  family                   = var.project
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name         = "app"
      image        = var.container_image
      essential    = true
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment = [
        { name = "GUNICORN_CMD_ARGS", value = "--workers=3 --timeout=60" }
      ]
      secrets = [
        { name = "DATABASE_URL", valueFrom = aws_ssm_parameter.database_url.arn },
        { name = "SIS_SECRET_KEY", valueFrom = aws_ssm_parameter.secret_key.arn }
      ]
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://localhost:8000/healthz')\" || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 20
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.sis.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "app"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "sis" {
  name            = "${var.project}-svc"
  cluster         = aws_ecs_cluster.sis.id
  task_definition = aws_ecs_task_definition.sis.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  # Register the same tasks with BOTH load balancers' target groups.
  dynamic "load_balancer" {
    for_each = local.lbs
    content {
      target_group_arn = aws_lb_target_group.sis[load_balancer.value].arn
      container_name   = "app"
      container_port   = 8000
    }
  }

  depends_on = [aws_lb_listener.http]
}

# Scale out on CPU — grows with enrollment, shrinks when quiet.
resource "aws_appautoscaling_target" "sis" {
  max_capacity       = 10
  min_capacity       = var.desired_count
  resource_id        = "service/${aws_ecs_cluster.sis.name}/${aws_ecs_service.sis.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.project}-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.sis.resource_id
  scalable_dimension = aws_appautoscaling_target.sis.scalable_dimension
  service_namespace  = aws_appautoscaling_target.sis.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 65
  }
}
