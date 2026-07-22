# النشر: من SQLite إلى بنية سحابية (PostgreSQL + Docker + موازِنا حِمل)

يعمل النظام على أي مزوّد يشغّل Docker. جاهز في المستودع لثلاثة مسارات:
- **محلي بشكل الإنتاج** — `docker-compose.yml` (القسم 1).
- **AWS** — `infra/aws/` (القسم 2).
- **Hetzner** — `infra/hetzner/` (القسم 7).

المحرّك يُختار بمتغيّر `DATABASE_URL` (فارغ ⇒ SQLite، `postgresql://…` ⇒ Postgres) — بلا تغيير كود.

## بنية AWS


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

---

## 7) النشر على Hetzner (بديل أوروبي)

البنية (`infra/hetzner/`):
```
            مستخدمون
          ┌────┴────┐
        LB1        LB2      ← موازِنا حِمل مُدارَان من Hetzner Cloud
          └────┬────┘
      app سيرفر 1..N         ← Docker (صورة التطبيق)
              │ (شبكة خاصة)
       Postgres سيرفر         ← Docker + قرص بيانات (Volume)
```

> **فرق مهم عن AWS:** Hetzner **لا يوفّر قاعدة مُدارة** — Postgres يُستضاف على سيرفر
> (حاوية Docker + قرص). للترقية لاحقًا: Patroni/تكرار، أو قاعدة مُدارة من طرف ثالث أوروبي.

### أ) ابنِ الصورة وادفعها لسجلّ
Hetzner بلا سجلّ صور مُدار — استخدم GHCR أو Docker Hub:
```bash
docker build -t ghcr.io/<you>/sis:latest .
docker push ghcr.io/<you>/sis:latest
```

### ب) أنشئ البنية
```bash
cd infra/hetzner
cp terraform.tfvars.example terraform.tfvars   # التوكن، مفتاح SSH، الصورة، كلمات المرور
terraform init
terraform apply     # شبكة خاصة + جدار حماية + سيرفرا تطبيق + سيرفر Postgres + موازِنَين
terraform output load_balancer_ips             # عنوانا الموازنَين
```
- التوسّع: زد `app_count` (سيرفرات تطبيق أكثر) — الموازنان يلتقطانها تلقائيًا عبر الوسم `role=app`.
- الأسرار (`DATABASE_URL`, `SIS_SECRET_KEY`) تُحقن عبر cloud-init، و`terraform.tfvars` مُستثنى من Git.

### ج) الحماية والنسخ الاحتياطي على Hetzner
- ضع **Cloudflare** أمام الموازنَين لحماية DDoS/WAF وHTTPS.
- نسخ Postgres: `pg_dump` مجدول إلى **Storage Box** من Hetzner، أو لقطة للقرص.
- HTTPS: أضف شهادة عبر خدمة الشهادات في موازن Hetzner (managed certificate) وحوّل 80→443.
