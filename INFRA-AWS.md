# Timia Hub API en AWS — plan de despliegue

| | |
|---|---|
| Región | **us-east-1** |
| Ambiente | **dev** (único por ahora) |
| Repo | `amilkarbolano-glitch/timia-hub-api` — **cada merge a `main` despliega** |
| Front | `https://main.da7vpns3df0uy.amplifyapp.com` (Amplify) |
| Base de datos | MongoDB Atlas (URL, usuario y clave como parámetros del stack) |
| Red | VPC, subredes y NAT de la infraestructura base existente |

```
Navegador ─HTTPS─▶ Amplify ──rewrite /api/* (200)──▶ CloudFront ─HTTP─▶ ALB ─▶ ECS Fargate (subred privada)
                   (front)                            (HTTPS)     (solo acepta         │
                                                                   CloudFront)          ▼ NAT de la base (IP fija)
                                                                              MongoDB Atlas (allowlist = IP del NAT)

GitHub main ──merge──▶ CodePipeline: Source → Build (pytest + docker build + push ECR) → Deploy (ECS)
```

| Archivo | Qué crea |
|---|---|
| `infrastructure.yml` | ECR, secretos (`SESSION_SECRET` generado, clave de Mongo), SGs, ALB, CloudFront, cluster, task definition, servicio |
| `pipeline.yml` | Conexión GitHub, bucket de artefactos, CodeBuild, CodePipeline con disparo por push a `main` |
| `.aws/configs/buildspec.yml` | `pytest` → `docker build` → push `<sha>` y `latest` → `imagedefinitions.json` |

Variables que recibe el contenedor: `MONGO_URL`, `MONGO_USER`, `MONGO_DB` (texto) y `MONGO_PASSWORD`, `SESSION_SECRET`
(desde Secrets Manager, para que no queden visibles en la task definition). `infrastructure_dev_base.yml` ya no se usa.

---

> **Windows:** los mismos comandos en PowerShell, listos para copiar por bloques, están en `scripts/aws-deploy.ps1`.
> Los de este documento son para bash (Linux/macOS/Git Bash/WSL).

## Fase 0 — Requisitos

- AWS CLI v2 con permisos de administrador en la cuenta (crea roles IAM).
- Acceso de administrador al repo de GitHub (para instalar la conexión y proteger `main`).
- Acceso a la consola de Amplify, Firebase y MongoDB Atlas.

```bash
export AWS_REGION=us-east-1
export ENV=dev
export STACK_API=timia-hub-api-$ENV
export STACK_PIPE=timia-hub-api-pipeline-$ENV
```

## Fase 1 — Código en `main`

Mergear a `main` los cambios de este repo **antes** de crear el pipeline (CodeBuild busca `.aws/configs/buildspec.yml`):
`infrastructure.yml`, `pipeline.yml`, `.aws/configs/buildspec.yml`, `Dockerfile`, `app/config.py`, `app/db.py`,
`app/security.py`, `.env.example`, docs.

## Fase 2 — Datos de la infraestructura base

La base no exporta outputs; se leen de sus recursos (`<stack-base>` = nombre del stack de la base):

```bash
aws cloudformation describe-stack-resources --stack-name <stack-base> \
  --query "StackResources[?ResourceType=='AWS::EC2::VPC'||ResourceType=='AWS::EC2::Subnet'||ResourceType=='AWS::EC2::EIP'].[LogicalResourceId,PhysicalResourceId]" \
  --output table

aws ec2 describe-managed-prefix-lists \
  --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
  --query 'PrefixLists[0].PrefixListId' --output text
```

```bash
export VPC_ID=vpc-...
export PUBLIC_SUBNETS=subnet-...,subnet-...                 # PublicSubnet1, PublicSubnet2
export PRIVATE_SUBNETS=subnet-...,subnet-...,subnet-...     # PrivateSubnet1, 2, 3
export CF_PREFIX_LIST=pl-...
export NAT_IP=x.x.x.x                                       # PhysicalResourceId de NatGatewayEIP
```

## Fase 3 — MongoDB Atlas

1. Cluster sobre **AWS / us-east-1** (M0 gratis o Flex).
2. *Database Access* → usuario con rol `readWrite` sobre la base `timia_dev` (o *Read and write to any database*).
3. *Network Access* → **solo `NAT_IP/32`**. Las tareas salen por el NAT de la base; nada más debe poder conectarse.
   (Para pruebas desde tu equipo, agrega tu IP temporalmente y quítala al terminar).
4. *Connect → Drivers* → copia la cadena. Puede ir **con** `usuario:clave@` (así la usa el driver) o sin ellos,
   pasando usuario y clave aparte en `MongoUser` / `MongoPassword`:

```bash
export MONGO_URL='mongodb+srv://cluster0.xxxx.mongodb.net/?retryWrites=true&w=majority'
export MONGO_USER=timia_app
read -rs MONGO_PASSWORD && export MONGO_PASSWORD      # no queda en el historial
```

Prueba local opcional (con tu IP en la allowlist):

```bash
docker build -t timia-hub-api:local .
docker run --rm -p 8000:8000 -e MONGO_URL -e MONGO_USER -e MONGO_PASSWORD -e MONGO_DB=timia_dev timia-hub-api:local
curl localhost:8000/api/health
```

## Fase 4 — Stack de la API (sin servicio)

```bash
aws cloudformation deploy --stack-name $STACK_API --template-file infrastructure.yml \
  --capabilities CAPABILITY_NAMED_IAM --parameter-overrides \
    EnvironmentName=$ENV ImageExists=false \
    VpcId=$VPC_ID PublicSubnets=$PUBLIC_SUBNETS PrivateSubnets=$PRIVATE_SUBNETS CloudFrontPrefixListId=$CF_PREFIX_LIST \
    MongoUrl="$MONGO_URL" MongoUser=$MONGO_USER MongoPassword="$MONGO_PASSWORD" \
    AllowDemoLogin=false SeedOnStart=true

aws cloudformation describe-stacks --stack-name $STACK_API --query 'Stacks[0].Outputs' --output table
export API_URL=https://dxxxx.cloudfront.net        # output ApiUrl
```

Tarda ~5–10 min (CloudFront). Parámetros de login (`FirebaseProjectId`, `FirebaseApiKey`, `FirebaseAuthDomain`,
`FirebaseAppId` o `GoogleClientId`) se pueden pasar aquí o después.

## Fase 5 — Pipeline

```bash
aws cloudformation deploy --stack-name $STACK_PIPE --template-file pipeline.yml \
  --capabilities CAPABILITY_NAMED_IAM --parameter-overrides EnvironmentName=$ENV
```

`Repository=amilkarbolano-glitch/timia-hub-api` y `GitHubBranch=main` vienen por defecto. La conexión se crea en
**PENDING**: consola → Developer Tools → Settings → **Connections** → la conexión `timia-hub-api-dev` →
*Update pending connection* → instalar "AWS Connector for GitHub" en la cuenta `amilkarbolano-glitch` con acceso a
`timia-hub-api`.

> Si ya existe una conexión autorizada sobre esa cuenta de GitHub, se puede reusar con
> `ExistingConnectionArn=arn:aws:codestar-connections:us-east-1:...`.

## Fase 6 — Primera imagen y servicio

1. CodePipeline → `timia-hub-api-dev` → **Release change**.
   - *Build* corre las pruebas y publica la imagen en ECR.
   - *Deploy* **falla** porque el servicio aún no existe. Es esperado.
2. Crear el servicio (los demás parámetros conservan su valor):

```bash
aws cloudformation deploy --stack-name $STACK_API --template-file infrastructure.yml \
  --capabilities CAPABILITY_NAMED_IAM --parameter-overrides ImageExists=true
```

## Fase 7 — Verificación de la API

```bash
curl $API_URL/api/health          # {"ok":true,"db":"timia_dev","keys":21,...}
curl $API_URL/api/auth/config     # métodos de login activos
```

Logs: CloudWatch → `/aws/ecs/timia-hub-api-dev`. En el primer arranque debe aparecer `[seed] keys cargadas: ...`.

## Fase 8 — Front (Amplify) y login

1. Amplify → app `da7vpns3df0uy` → **Hosting → Rewrites and redirects → Manage → JSON**. Agrega como **primera** regla
   (antes de la regla SPA que manda todo a `/index.html`):

   ```json
   { "source": "/api/<*>", "target": "https://dxxxx.cloudfront.net/api/<*>", "status": "200" }
   ```

2. En el front, la URL base de la API queda **vacía / mismo origen** (llama a `/api/...`).
3. Firebase → Authentication → Settings → **Authorized domains** → agregar `main.da7vpns3df0uy.amplifyapp.com`
   (o en *Authorized JavaScript origins* del Client ID si usan GIS).
4. Probar: abrir el front, iniciar sesión, DevTools → Application → Cookies → `timia_session` en
   `main.da7vpns3df0uy.amplifyapp.com` con `Secure` y `HttpOnly`.

**Plan B** (si la cookie no aparece porque el proxy no reenvía `Set-Cookie`): el front llama directo a `$API_URL` con
`credentials: 'include'` y se actualiza el stack con `CookieSameSite=none` (CORS ya permite el dominio de Amplify).
Funciona en Chrome, **no en Safari**; la solución definitiva es un dominio propio.

## Fase 9 — Cierre

```bash
# El seed solo se necesitaba la primera vez
aws cloudformation deploy --stack-name $STACK_API --template-file infrastructure.yml \
  --capabilities CAPABILITY_NAMED_IAM --parameter-overrides SeedOnStart=false
```

GitHub → Settings → Branches → regla para `main`: **Require a pull request** y **Require status checks** (`test` de
`ci.yml`). Un merge a `main` es un despliegue.

---

## Operación

| Qué | Cómo |
|---|---|
| Desplegar | Merge de un PR a `main` |
| Redesplegar sin cambios | CodePipeline → *Release change* |
| Rollback automático | Si la nueva versión no pasa `/api/health`, el circuit breaker de ECS vuelve a la anterior |
| Rollback manual | `aws ecs update-service --cluster timia-hub-api-dev --service timia-hub-api-dev --task-definition timia-hub-api-dev:<revision>` |
| Cambiar clave de Mongo | `deploy` con `MongoPassword=...` y luego `aws ecs update-service --cluster timia-hub-api-dev --service timia-hub-api-dev --force-new-deployment` (el secreto cambia, la task definition no) |
| Cambiar variables | `deploy` con el parámetro; CloudFormation crea una revisión nueva de la task definition y redespliega |
| Apagar dev | `aws ecs update-service ... --desired-count 0` (ALB y CloudFront siguen cobrando) |

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| Build falla en `docker login` / `push` | El repo ECR no existe (Fase 4 no terminó) o el nombre no coincide con `timia-hub-api-dev` |
| Source falla con error de conexión | La conexión GitHub sigue en PENDING o la app no tiene acceso al repo |
| Tareas en `STOPPED` con `ResourceInitializationError` | No pueden leer secretos o bajar la imagen: revisar que las subredes privadas salgan por el NAT |
| `/api/health` responde 503 `mongo no disponible` | IP del NAT no está en Atlas o usuario/clave incorrectos (si la clave va en la URL, caracteres como `@ : /` deben ir codificados) |
| 504 desde CloudFront | Ninguna tarea sana en el target group: revisar logs del contenedor |
| Login OK pero la siguiente petición da 401 | La cookie no viaja: ver Fase 8 (proxy o plan B) |

## Costos aproximados (dev)

ALB ~18 USD/mes · Fargate 0.25 vCPU/0.5 GB ~9 USD · CloudFront ~1 USD · Secrets Manager ~1 USD · Atlas M0 gratis.
VPC y NAT ya los paga la infraestructura base.

## Siguientes pasos

- Dominio propio (`app.` y `api.` bajo el mismo dominio) para eliminar la dependencia del proxy de Amplify.
- Ambiente `prd` separado (`EnvironmentName=prd`, `GitHubBranch=main`) y dev pasando a `develop`.
- Escritura por key con transacción en `app/db.py` (hoy `delete_many` + `insert_many` sin atomicidad).
