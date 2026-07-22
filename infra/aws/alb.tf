# Two internet-facing Application Load Balancers (per the owner's request).
# Both point at the SAME ECS service, so either can serve all traffic — LB-level
# redundancy on top of the per-AZ redundancy an ALB already provides.
# Route 53 (see outputs) can weight or fail over between the two DNS names.
#
# Note: one ALB already spans both AZs and is highly available; the second adds
# cost. Keep both only if you want isolation/redundancy at the balancer tier.

locals {
  lbs = toset(["a", "b"])
}

resource "aws_lb" "sis" {
  for_each           = local.lbs
  name               = "${var.project}-alb-${each.key}"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
  tags               = { Name = "${var.project}-alb-${each.key}" }
}

resource "aws_lb_target_group" "sis" {
  for_each    = local.lbs
  name        = "${var.project}-tg-${each.key}"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # Fargate tasks register by IP

  health_check {
    path                = "/healthz"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
  tags = { Name = "${var.project}-tg-${each.key}" }
}

resource "aws_lb_listener" "http" {
  for_each          = local.lbs
  load_balancer_arn = aws_lb.sis[each.key].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.sis[each.key].arn
  }
  # For HTTPS: add an aws_lb_listener on 443 with an ACM certificate_arn and
  # redirect this :80 listener to :443. See DEPLOY.md.
}
