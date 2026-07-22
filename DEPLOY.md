# النشر: من SQLite إلى AWS (PostgreSQL + Docker + موازِنا حِمل)

هذا الدليل يشرح تشغيل النظام على بنية سحابية تتحمّل آلاف الطلاب. البنية:

```
        مستخدمون
       ┌───┴────┐
     ALB a     ALB b        ← موازِنا حِمل (internet-facing) — طلبك
       └───┬────┘
        ECS Fargate
      app task 1 … N         ← نسخ التطبيق (توسّع تلقائي على CPU)
           │
     RDS PostgreSQL          ← قاعدة مُدارة، Multi-AZ، نسخ احتياطي
```

المحرّك يُختار بمتغيّر البيئة **`DATABASE_URL`**:
- غير مضبوط ⇒ SQLite (التطوير المحلي و73 اختبارًا — بدون أي تغيير).
- `postgresql://…` ⇒ PostgreSQL (الإنتاج). لا حاجة لتعديل أي كود.

---

## 1) تجربة محلية بشكل الإنتاج (Docker Compose)

نسختان من التطبيق + موازِنان (nginx) + Postgres:

```bash
export SIS_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
export DB_PASSWORD="dev-pass"
docker compose up --build
# موازن 1:  http://localhost:8081
# موازن 2:  http://localhost:8082
```

أول طلب يهيّئ المخطط تلقائيًا. لإدخال بيانات تجريبية:
```bash
docker compose exec app1 python seed_demo.py
```

---

## 2) النشر على AWS

المتطلبات: حساب AWS، وأدوات `aws` و`docker` و`terraform`.

### أ) إنشاء البنية
```bash
cd infra/aws
cp terraform.tfvars.example terraform.tfvars   # عدّل القيم (كلمة مرور القاعدة، المفتاح السري)
terraform init
terraform apply        # ينشئ VPC + RDS + ECR + ECS + موازِنَي ALB
```
> ملاحظة: الموازن الواحد أصلًا عالي التوفّر (يمتد على منطقتَي إتاحة). الموازن الثاني إضافي حسب طلبك ويضيف تكلفة؛ أبقِ الاثنين إن رغبت بعزل/تكرار على مستوى الموازن.

### ب) بناء الصورة ودفعها إلى ECR
```bash
ECR=$(terraform output -raw ecr_repository_url)
REGION=$(terraform output -raw ... 2>/dev/null || echo me-central-1)
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin ${ECR%/*}
docker build -t sis ../..
docker tag sis:latest $ECR:latest
docker push $ECR:latest
```

### ج) تشغيل الخدمة بالصورة
عدّل `container_image = "<ECR>:latest"` في `terraform.tfvars` ثم:
```bash
terraform apply
terraform output load_balancer_dns   # عنوانا الموازنَين — افتح أيًّا منهما
```

### د) أول مستخدم
افتح `/setup` على عنوان الموازن لإنشاء حساب الأدمن الأول.

---

## 3) الأسرار
- `DATABASE_URL` و`SIS_SECRET_KEY` تُخزَّن في **SSM Parameter Store (SecureString)** وتُحقن في الحاوية عند الإقلاع — لا تُكتب في الصورة ولا في نص التعريف.
- `terraform.tfvars` مُستثنى من Git.

## 4) HTTPS (موصى قبل الإطلاق)
أنشئ شهادة في ACM، أضف listener على 443 بالشهادة لكل ALB، وحوّل 80→443. راجع تعليقات `infra/aws/alb.tf` و`security.tf`.

## 5) الحماية من DDoS والترافيك العالي
- ضع **Cloudflare** أو **AWS WAF + Shield** أمام الموازنَين (حدّ معدّل، تصفية، تخفيف DDoS).
- التوسّع التلقائي مضبوط على 65% CPU (2 → 10 مهام) في `ecs.tf`.
- لأعداد اتصالات عالية أضف **RDS Proxy** أو PgBouncer لتجميع الاتصالات.

## 6) النسخ الاحتياطي
- RDS: نسخ تلقائي يومي (7 أيام) + لقطات يدوية. للترحيل من SQLite: `pg_restore`/`psql` أو أداة ترحيل لمرة واحدة.
- SQLite المحلي: `python manage.py backup`.
