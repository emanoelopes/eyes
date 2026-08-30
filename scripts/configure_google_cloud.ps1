param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$TopicId = "meet-monitor-events",
  [string]$SubscriptionId = "meet-monitor-events-sub",
  [string]$ServiceAccountId = "meet-event-listener"
)
$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  throw "gcloud não encontrado. Instale o Google Cloud CLI."
}

gcloud config set project $ProjectId
gcloud services enable meet.googleapis.com workspaceevents.googleapis.com pubsub.googleapis.com people.googleapis.com

gcloud pubsub topics describe $TopicId 2>$null
if ($LASTEXITCODE -ne 0) { gcloud pubsub topics create $TopicId }

gcloud pubsub topics add-iam-policy-binding $TopicId `
  --member="serviceAccount:meet-api-event-push@system.gserviceaccount.com" `
  --role="roles/pubsub.publisher"

gcloud pubsub subscriptions describe $SubscriptionId 2>$null
if ($LASTEXITCODE -ne 0) { gcloud pubsub subscriptions create $SubscriptionId --topic=$TopicId }

$ServiceAccountEmail = "$ServiceAccountId@$ProjectId.iam.gserviceaccount.com"
gcloud iam service-accounts describe $ServiceAccountEmail 2>$null
if ($LASTEXITCODE -ne 0) {
  gcloud iam service-accounts create $ServiceAccountId --display-name="Meet event listener"
}

gcloud projects add-iam-policy-binding $ProjectId `
  --member="serviceAccount:$ServiceAccountEmail" `
  --role="roles/pubsub.subscriber"

$CurrentUser = (gcloud config get-value account).Trim()
if (-not $CurrentUser) { throw "Execute 'gcloud auth login' antes deste script." }

gcloud iam service-accounts add-iam-policy-binding $ServiceAccountEmail `
  --member="user:$CurrentUser" `
  --role="roles/iam.serviceAccountTokenCreator"

Write-Host ""
Write-Host "Infraestrutura criada. Agora execute:"
Write-Host "gcloud auth application-default login --impersonate-service-account=$ServiceAccountEmail"
Write-Host ""
Write-Host "Depois coloque GOOGLE_CLOUD_PROJECT=$ProjectId no arquivo .env"
