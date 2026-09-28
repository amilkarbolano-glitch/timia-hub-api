# Timia Hub API - despliegue en AWS desde Windows (PowerShell). Ver INFRA-AWS.md para el detalle de cada fase.
#
# NO ejecutar el archivo completo: hay pasos manuales entre fases (Atlas, aprobar la conexion GitHub, Amplify).
# Copiar y pegar bloque por bloque en PowerShell. Las plantillas se toman SIEMPRE de $Repo (FASE 0).
# Las variables viven mientras la ventana este abierta; si la cierras, vuelve a pegar las FASES 0, 2 y 3.
# Requiere AWS CLI v2 (instalador MSI) con `aws configure` hecho.

# ─── FASE 0: variables ───────────────────────────────────────────────────────
# Carpeta con los infrastructure.yml y pipeline.yml DE TIMIA (basta con esos dos archivos; no hace falta el repo completo).
# Ojo: el otro proyecto tiene su propio infrastructure.yml; el chequeo de abajo evita desplegar el equivocado.
$Repo = "C:\ruta\a\timia-hub-api"
if ((Test-Path "$Repo\pipeline.yml") -and (Select-String -Path "$Repo\infrastructure.yml" -Pattern "Timia Hub API" -Quiet)) {
    Set-Location $Repo; "OK: plantillas de timia en $Repo"
} else { Write-Error "En $Repo no estan las plantillas de timia (infrastructure.yml de Timia Hub API + pipeline.yml)" }
$env:AWS_DEFAULT_REGION = "us-east-1"          # equivalente a `export` en bash: vale para esta ventana
$EnvName    = "dev"
$StackApi   = "timia-hub-api-$EnvName"
$StackPipe  = "timia-hub-api-pipeline-$EnvName"
aws sts get-caller-identity                    # confirma cuenta y usuario

# ─── FASE 2: datos de la infraestructura base ────────────────────────────────
# Nombre del stack base (si no lo sabes, listalos):
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query "StackSummaries[].StackName" --output table

$BaseStack = "<nombre-del-stack-base>"

function Get-BaseId($LogicalId) {
    aws cloudformation describe-stack-resource --stack-name $BaseStack --logical-resource-id $LogicalId `
        --query "StackResourceDetail.PhysicalResourceId" --output text
}
$VpcId          = Get-BaseId "VPC"
$PublicSubnets  = "$(Get-BaseId 'PublicSubnet1'),$(Get-BaseId 'PublicSubnet2')"
$PrivateSubnets = "$(Get-BaseId 'PrivateSubnet1'),$(Get-BaseId 'PrivateSubnet2'),$(Get-BaseId 'PrivateSubnet3')"
$NatIp          = Get-BaseId "NatGatewayEIP"
$CfPrefixList   = aws ec2 describe-managed-prefix-lists `
    --filters "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing" `
    --query "PrefixLists[0].PrefixListId" --output text

"VPC: $VpcId`nPublicas: $PublicSubnets`nPrivadas: $PrivateSubnets`nNAT IP: $NatIp  (esta va en Atlas)`nPrefix list: $CfPrefixList"

# ─── FASE 3: MongoDB Atlas ───────────────────────────────────────────────────
# En Atlas: cluster en AWS us-east-1, usuario readWrite, Network Access = <NAT IP>/32.
# Cadena de Atlas entre comillas simples (PowerShell no interpreta & ni ?).
# Si trae usuario:clave@, $MongoUser y la clave de Read-Host se pueden omitir.
$MongoUrl  = 'mongodb+srv://amilkarbolano_db_user:Y2b9hnlsiYJIxHU5@clustertimhub.fp1rsuc.mongodb.net'
$MongoUser = 'amilkarbolano_db_user'
$sec = Read-Host "Clave de Atlas" -AsSecureString
$MongoPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))

# (Opcional, requiere el repo completo y Docker) probar la imagen en local contra Atlas (agrega tu IP en Atlas mientras pruebas)
docker build -t timia-hub-api:local $Repo
docker run --rm -p 8000:8000 -e "MONGO_URL=$MongoUrl" -e "MONGO_USER=$MongoUser" -e "MONGO_PASSWORD=$MongoPassword" -e "MONGO_DB=timia_dev" timia-hub-api:local
# en otra ventana:  Invoke-RestMethod http://localhost:8000/api/health

# ─── FASE 4: stack de la API (sin servicio) ──────────────────────────────────
$ApiParams = @(
    "EnvironmentName=$EnvName", "ImageExists=false",
    "VpcId=$VpcId", "PublicSubnets=$PublicSubnets", "PrivateSubnets=$PrivateSubnets", "CloudFrontPrefixListId=$CfPrefixList",
    "MongoUrl=$MongoUrl",
    "AllowDemoLogin=false", "SeedOnStart=true"
)
if ($MongoUrl -notmatch '@') { $ApiParams += "MongoUser=$MongoUser", "MongoPassword=$MongoPassword" }   # credenciales aparte
# Solo despliega si las fases 0, 2 y 3 dejaron todas las variables con valor
$Requeridas = @('Repo','EnvName','StackApi','VpcId','PublicSubnets','PrivateSubnets','CfPrefixList','MongoUrl')
if ($MongoUrl -notmatch '@') { $Requeridas += 'MongoUser','MongoPassword' }
$Faltan = @($Requeridas |
    Where-Object { $v = Get-Variable $_ -ValueOnly -ErrorAction SilentlyContinue; -not $v -or $v -eq 'None' -or $v -match '(^|,)None(,|$)' })
if ($Faltan) {
    Write-Warning "Variables vacias o sin resolver: $($Faltan -join ', '). Pega de nuevo las fases 0, 2 y 3 y luego esta."
} else {
    aws cloudformation deploy --stack-name $StackApi --template-file "$Repo\infrastructure.yml" --capabilities CAPABILITY_NAMED_IAM --parameter-overrides $ApiParams
}

$ApiUrl = aws cloudformation describe-stacks --stack-name $StackApi --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text
"ApiUrl: $ApiUrl"

# ─── FASE 5: pipeline ────────────────────────────────────────────────────────
aws cloudformation deploy --stack-name $StackPipe --template-file "$Repo\pipeline.yml" --capabilities CAPABILITY_NAMED_IAM --parameter-overrides "EnvironmentName=$EnvName"
# Manual: consola -> Developer Tools -> Settings -> Connections -> timia-hub-api-dev -> Update pending connection
#         -> instalar "AWS Connector for GitHub" en amilkarbolano-glitch con acceso a timia-hub-api

# ─── FASE 6: primera imagen y servicio ───────────────────────────────────────
aws codepipeline start-pipeline-execution --name "timia-hub-api-$EnvName"
# Esperar a que Build termine OK (Deploy falla la primera vez: aun no hay servicio). Ver estado:
aws codepipeline get-pipeline-state --name "timia-hub-api-$EnvName" --query "stageStates[].[stageName,latestExecution.status]" --output table

aws cloudformation deploy --stack-name $StackApi --template-file "$Repo\infrastructure.yml" --capabilities CAPABILITY_NAMED_IAM --parameter-overrides "ImageExists=true"

# ─── FASE 7: verificacion ────────────────────────────────────────────────────
Invoke-RestMethod "$ApiUrl/api/health"
Invoke-RestMethod "$ApiUrl/api/auth/config"
aws logs tail "/aws/ecs/timia-hub-api-$EnvName" --since 15m

# ─── FASE 8: Amplify y Firebase (consola) ────────────────────────────────────
# Regla para Amplify -> Hosting -> Rewrites and redirects (primera regla, antes de la del SPA):
"{ `"source`": `"/api/<*>`", `"target`": `"$ApiUrl/api/<*>`", `"status`": `"200`" }"
# Firebase -> Authentication -> Settings -> Authorized domains -> main.da7vpns3df0uy.amplifyapp.com

# ─── FASE 9: cierre ──────────────────────────────────────────────────────────
aws cloudformation deploy --stack-name $StackApi --template-file "$Repo\infrastructure.yml" --capabilities CAPABILITY_NAMED_IAM --parameter-overrides "SeedOnStart=false"
Remove-Variable MongoPassword, sec

# ─── Operacion ───────────────────────────────────────────────────────────────
# Forzar redespliegue (ej. tras cambiar la clave de Mongo con MongoPassword=...):
#   aws ecs update-service --cluster "timia-hub-api-$EnvName" --service "timia-hub-api-$EnvName" --force-new-deployment
# Apagar dev:
#   aws ecs update-service --cluster "timia-hub-api-$EnvName" --service "timia-hub-api-$EnvName" --desired-count 0
