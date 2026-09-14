# Timia Hub en AWS — plantillas CloudFormation

Tres stacks, en este orden (mismo `ProjectName` y `EnvironmentName` en los tres para que los `Export`/`ImportValue` encajen):

| # | Stack | Repo / archivo | Qué crea |
|---|---|---|---|
| 1 | `timia-<env>-base` | `timia-hub-api/infrastructure_dev_base.yml` | VPC, subredes públicas/privadas, NAT, **Amazon DocumentDB** (Mongo compatible, TLS, cifrado), secreto `MONGO_URL` |
| 2 | `timia-hub-api-<env>` | `timia-hub-api/infrastructure.yml` | ECR, ECS Fargate + ALB, logs, secretos (`SESSION_SECRET`, `GOOGLE_CLIENT_ID`, `TIMIA_API_KEY`). Output **ApiUrl** |
| 3 | `timia-hub-<env>` | `timia-hub/infrastructure.yml` | Amplify Hosting desde GitHub (rama `develop` = dev, `main` = prd). Output **FrontendUrl** |

## Pasos
1. **Base**: parámetros `DBUsername`/`DBPassword`. Tarda ~10 min (DocumentDB).
2. **API**: primero desplegar el stack (crea el ECR vacío; el servicio quedará esperando imagen), luego publicar la
   imagen con el workflow `deploy-aws.yml` del repo (secrets `AWS_ROLE_ARN`, vars `AWS_REGION`, `PROJECT_NAME`, `APP_NAME`)
   o a mano: `docker build -t <EcrRepositoryUri>:latest . && docker push …` y `aws ecs update-service --force-new-deployment`.
   Parámetro `FrontendOrigin`: la URL que dará Amplify (`https://develop.<appid>.amplifyapp.com`); si aún no existe,
   poner un valor provisional y actualizar el stack después.
3. **Front**: `ApiUrl` = output del stack 2; `GitHubToken` = token clásico con `repo` (como en los otros proyectos).
   Amplify construye con `npm run build:client` e inyecta la API en `public/config.js` (sin recompilar por ambiente).
4. Actualizar el stack 2 con `FrontendOrigin` = output `FrontendUrl` del stack 3 (CORS y cookies).

## Autenticación
- Con `GoogleClientId` vacío la app queda en **modo demo** (cuentas de prueba). Cuando el equipo de Google entregue el Client ID,
  se actualiza el parámetro en el stack de la API y el login pasa a Google automáticamente.
- Front y API viven en dominios distintos ⇒ la API se despliega con `COOKIE_SAMESITE=none`, `COOKIE_SECURE=true` y `CORS_ORIGINS=<FrontendOrigin>`.
  **Requiere HTTPS en la API**: agregar un listener 443 al ALB con certificado ACM y un dominio (`api.<dominio>`), y usar esa URL como `ApiUrl`.
  Mientras no haya HTTPS en la API, para pruebas en `dev` se puede usar `COOKIE_SECURE=false` (editar la TaskDefinition).

## Alternativa sin DocumentDB
Si prefieren MongoDB Atlas: no desplegar el stack base; crear el secreto `timia/<env>/MONGO_URL` a mano en Secrets Manager con la
cadena `mongodb+srv://…` y crear los exports de VPC/subredes de una VPC existente, o simplificar el stack de la API para recibir `MongoUrl` como parámetro.

## Costos aproximados (dev, us-east-1)
NAT Gateway ~32 USD/mes · DocumentDB db.t3.medium ~60 USD/mes · Fargate 0.25 vCPU ~10 USD/mes · ALB ~18 USD/mes · Amplify ~1 USD.
Para abaratar dev: el `docker-compose.yml` en una sola EC2 t3.small (~15 USD/mes) sigue siendo la opción más barata.
