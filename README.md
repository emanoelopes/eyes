# Eyes — Monitor de Salas Google Meet

Dashboard local para acompanhar várias salas do Google Meet sem precisar entrar nas reuniões.

O sistema mostra, para cada sala:

- status **ATIVA / INATIVA**;
- quantidade de participantes;
- status de gravação;
- botão **Entrar**;
- agrupamento por sala principal e células, por exemplo `BS12`, `OS01`, etc.;
- atualização periódica e eventos do Google Workspace em tempo real.

## Arquitetura

```text
Google Meet
    │
    ├── Google Meet REST API
    │       ├── status da conferência
    │       ├── participantes
    │       └── gravação
    │
    └── Google Workspace Events API
            │
            ▼
        Cloud Pub/Sub
            │
            ▼
      Aplicação local
      Python + FastAPI
            │
            ▼
        Dashboard Web
```

A aplicação roda localmente. Não é necessário publicar o backend na internet.

---

# 1. Requisitos

## Sistema

Este tutorial usa Windows 11 + PowerShell.

Instale:

- Python 3.11 ou superior;
- Git;
- Google Cloud CLI (`gcloud`);
- acesso a um projeto Google Cloud;
- conta Google Workspace com acesso às salas Meet que serão monitoradas.

Verifique:

```powershell
python --version
git --version
gcloud --version
```

Se o `gcloud` não estiver instalado:

```powershell
winget install --id Google.CloudSDK
```

Depois feche e abra o PowerShell.

---

# 2. Clonar o projeto

```powershell
git clone https://github.com/mikaelmota13/eyes.git
cd eyes
```

---

# 3. Criar o ambiente Python

No PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

Ou manualmente:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

# 4. Criar um projeto no Google Cloud

Acesse:

https://console.cloud.google.com/

Crie um projeto exclusivo para o monitor.

Exemplo:

```text
Nome: Meet Monitor
Project ID: meet-monitor-exemplo
```

O valor utilizado nos comandos é o **Project ID**, não o nome nem o número do projeto.

Exemplo:

```text
meet-monitor-exemplo
```

---

# 5. Autenticar o Google Cloud CLI

Execute:

```powershell
gcloud auth login
```

Use uma conta que tenha permissão no projeto Google Cloud.

Configure o projeto:

```powershell
gcloud config set project SEU_PROJECT_ID
```

Exemplo:

```powershell
gcloud config set project meet-monitor-exemplo
```

Confirme:

```powershell
gcloud config get-value project
```

Também é útil verificar a conta ativa:

```powershell
gcloud auth list
```

Se necessário:

```powershell
gcloud config set account "usuario@instituicao.br"
```

---

# 6. Habilitar as APIs

Substitua `SEU_PROJECT_ID` pelo ID real.

```powershell
gcloud config set project SEU_PROJECT_ID
```

Habilite:

```powershell
gcloud services enable `
  meet.googleapis.com `
  workspaceevents.googleapis.com `
  pubsub.googleapis.com `
  people.googleapis.com
```

As APIs utilizadas são:

- Google Meet REST API;
- Google Workspace Events API;
- Cloud Pub/Sub API;
- People API.

---

# 7. Criar o tópico Pub/Sub

```powershell
gcloud pubsub topics create meet-monitor-events
```

Permita que o Google Workspace publique eventos nesse tópico:

```powershell
gcloud pubsub topics add-iam-policy-binding meet-monitor-events `
  --member="serviceAccount:meet-api-event-push@system.gserviceaccount.com" `
  --role="roles/pubsub.publisher"
```

---

# 8. Criar a subscription Pub/Sub

```powershell
gcloud pubsub subscriptions create meet-monitor-events-sub `
  --topic=meet-monitor-events
```

Essa subscription será consumida diretamente pela aplicação local.

---

# 9. Criar uma service account para o listener

```powershell
gcloud iam service-accounts create meet-event-listener `
  --display-name="Meet event listener"
```

O endereço será:

```text
meet-event-listener@SEU_PROJECT_ID.iam.gserviceaccount.com
```

Dê permissão de leitura do Pub/Sub:

```powershell
gcloud projects add-iam-policy-binding SEU_PROJECT_ID `
  --member="serviceAccount:meet-event-listener@SEU_PROJECT_ID.iam.gserviceaccount.com" `
  --role="roles/pubsub.subscriber"
```

Permita que sua conta gere credenciais temporárias para essa service account:

```powershell
gcloud iam service-accounts add-iam-policy-binding `
  meet-event-listener@SEU_PROJECT_ID.iam.gserviceaccount.com `
  --member="user:SEU_EMAIL_GOOGLE" `
  --role="roles/iam.serviceAccountTokenCreator"
```

Exemplo:

```powershell
gcloud iam service-accounts add-iam-policy-binding `
  meet-event-listener@meet-monitor-exemplo.iam.gserviceaccount.com `
  --member="user:usuario@instituicao.br" `
  --role="roles/iam.serviceAccountTokenCreator"
```

---

# 10. Configurar Application Default Credentials

Execute:

```powershell
gcloud auth application-default login `
  --impersonate-service-account=meet-event-listener@SEU_PROJECT_ID.iam.gserviceaccount.com
```

O navegador será aberto.

Após concluir, deve aparecer algo semelhante a:

```text
Credentials saved to file:
C:\Users\...\AppData\Roaming\gcloud\application_default_credentials.json
```

Essas credenciais são usadas pelo cliente Pub/Sub em Python.

---

# 11. Configurar OAuth da aplicação

No Google Cloud Console, abra:

```text
Google Auth Platform
```

Configure o aplicativo OAuth.

Para organizações Google Workspace, use **Internal** quando essa opção estiver disponível.

## Escopos

Adicione:

```text
https://www.googleapis.com/auth/meetings.space.readonly
https://www.googleapis.com/auth/userinfo.profile
```

O primeiro permite consultar informações das reuniões Meet da conta.

## Criar o cliente OAuth

Abra:

```text
Google Auth Platform
→ Clients
→ Create Client
```

Escolha:

```text
Application type: Desktop app
```

Baixe o arquivo JSON.

Renomeie para:

```text
client_secret.json
```

Coloque em:

```text
credentials/client_secret.json
```

A estrutura deve ficar:

```text
eyes/
├── credentials/
│   └── client_secret.json
├── app/
├── data/
├── static/
└── ...
```

No PowerShell, confirme:

```powershell
Test-Path .\credentials\client_secret.json
```

Resultado esperado:

```text
True
```

### Atenção no Windows

Se o arquivo aparecer como:

```text
client_secret.json.json
```

renomeie:

```powershell
Rename-Item `
  .\credentials\client_secret.json.json `
  client_secret.json
```

---

# 12. Configurar `.env`

Copie:

```powershell
Copy-Item .env.example .env
```

Edite `.env`:

```env
GOOGLE_CLOUD_PROJECT=SEU_PROJECT_ID
PUBSUB_TOPIC_ID=meet-monitor-events
PUBSUB_SUBSCRIPTION_ID=meet-monitor-events-sub
ROOMS_CSV=data/salas.csv
HOST=127.0.0.1
PORT=8000
RECONCILE_SECONDS=45
```

Exemplo:

```env
GOOGLE_CLOUD_PROJECT=meet-monitor-exemplo
PUBSUB_TOPIC_ID=meet-monitor-events
PUBSUB_SUBSCRIPTION_ID=meet-monitor-events-sub
ROOMS_CSV=data/salas.csv
HOST=127.0.0.1
PORT=8000
RECONCILE_SECONDS=45
```

Não publique o `.env`.

---

# 13. Cadastrar suas próprias salas

A aplicação lê:

```text
data/salas.csv
```

O CSV precisa conter pelo menos:

```csv
Titulo,Dia,Link do Meet
Sala - BS01,Segunda,https://meet.google.com/abc-defg-hij
Célula 01 - BS01,Segunda,https://meet.google.com/def-ghij-klm
Célula 02 - BS01,Segunda,https://meet.google.com/ghi-jklm-nop
Sala - BS02,Quarta,https://meet.google.com/jkl-mnop-qrs
```

O arquivo atual pode conter colunas extras; elas serão ignoradas.

Os campos utilizados são:

```text
Titulo
Dia
Link do Meet
```

## Agrupamento

O dashboard identifica automaticamente grupos pelo título.

Exemplos:

```text
Sala - BS12
Célula 01 - BS12
Célula 02 - BS12
```

serão apresentados dentro de:

```text
BS12
```

Da mesma forma:

```text
Sala - OS01
Célula 01 - OS01
```

serão apresentados dentro de:

```text
OS01
```

Para novos padrões, ajuste a função `getGroup()` em:

```text
static/app.js
```

---

# 14. Conta Google usada pela aplicação

Quando a aplicação executar pela primeira vez, o navegador abrirá para OAuth.

Entre com a conta Google Workspace que possui ou tem acesso às salas que deseja consultar.

Para monitoramento por assinatura no usuário, o cenário recomendado é que as salas sejam pertencentes à mesma conta Workspace autenticada.

Não informe sua senha no código.

---

# 15. Executar

No PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\run.ps1
```

Ou diretamente:

```powershell
.\.venv\Scripts\python.exe `
  -m uvicorn app.main:app `
  --host 127.0.0.1 `
  --port 8000
```

Abra:

```text
http://127.0.0.1:8000
```

Na primeira execução, o navegador pode abrir para autenticação OAuth.

---

# 16. Como funciona a atualização

Há dois mecanismos.

## Workspace Events

Os eventos incluem:

```text
google.workspace.meet.conference.v2.started
google.workspace.meet.conference.v2.ended
google.workspace.meet.participant.v2.joined
google.workspace.meet.participant.v2.left
google.workspace.meet.recording.v2.started
google.workspace.meet.recording.v2.ended
```

Eles chegam através do Pub/Sub.

## Reconciliação periódica

Mesmo com eventos em tempo real, a aplicação consulta periodicamente a Meet REST API.

Por padrão:

```env
RECONCILE_SECONDS=45
```

Isso corrige eventuais divergências e atualiza o estado mesmo se algum evento for perdido.

Não é recomendado reduzir agressivamente esse valor quando houver muitas salas, pois isso aumenta o consumo da cota da Meet API.

---

# 17. Verificar se os eventos estão chegando

Com a aplicação rodando, entre em uma das reuniões.

No terminal deve aparecer algo semelhante a:

```text
Evento Workspace recebido:
google.workspace.meet.participant.v2.joined
```

Ao sair:

```text
google.workspace.meet.participant.v2.left
```

Ao iniciar uma gravação:

```text
google.workspace.meet.recording.v2.started
```

Ao encerrar:

```text
google.workspace.meet.recording.v2.ended
```

---

# 18. Endpoints locais

## Salas

```text
GET http://127.0.0.1:8000/api/rooms
```

Retorna o estado individual das reuniões.

## Resumo

```text
GET http://127.0.0.1:8000/api/status
```

Exemplo:

```json
{
  "rooms": 70,
  "active": 4,
  "participants": 91,
  "recording": 3
}
```

---

# 19. Estrutura do projeto

```text
eyes/
├── app/
│   ├── auth.py
│   ├── config.py
│   ├── google_meet.py
│   ├── main.py
│   ├── models.py
│   ├── pubsub_listener.py
│   ├── rooms.py
│   ├── state.py
│   └── workspace_events.py
│
├── credentials/
│   └── client_secret.json
│
├── data/
│   └── salas.csv
│
├── scripts/
│   ├── setup.ps1
│   ├── configure_google_cloud.ps1
│   └── run.ps1
│
├── static/
│   ├── app.js
│   ├── index.html
│   └── style.css
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

# 20. Problemas comuns

## `run.ps1 não está assinado digitalmente`

Execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Depois:

```powershell
.\scripts\run.ps1
```

---

## `gcloud não é reconhecido`

Instale:

```powershell
winget install --id Google.CloudSDK
```

Feche e abra o PowerShell.

Teste:

```powershell
gcloud --version
```

---

## `PERMISSION_DENIED`

Veja a conta ativa:

```powershell
gcloud auth list
```

Troque:

```powershell
gcloud config set account "usuario@instituicao.br"
```

Confirme o projeto:

```powershell
gcloud config get-value project
```

---

## `client_secret.json` não encontrado

Teste:

```powershell
Test-Path .\credentials\client_secret.json
```

Deve retornar:

```text
True
```

---

## Participantes não atualizam

Confirme que `app/google_meet.py` utiliza:

```python
"filter": "latest_end_time IS NULL"
```

e não:

```python
"latestEndTime IS NULL"
```

Depois reinicie a aplicação.

---

## Gravação não atualiza

Verifique o terminal.

A aplicação deve receber:

```text
google.workspace.meet.recording.v2.started
```

Também confirme se o usuário autenticado tem acesso à conferência e se a Meet API está habilitada.

---

## Interface não mudou após editar CSS/JS

Reinicie o backend e force atualização do navegador:

```text
Ctrl + F5
```

---

# 21. Segurança

Nunca envie ao Git:

```text
.env
credentials/client_secret.json
token.json
.runtime/
```

Esses arquivos já devem permanecer no `.gitignore`.

Também evite publicar `data/salas.csv` quando ele contiver:

- links reais do Meet;
- e-mails;
- nomes de participantes;
- informações internas.

Para repositórios públicos, use um arquivo de exemplo, por exemplo:

```text
data/salas.example.csv
```

e mantenha o arquivo real ignorado pelo Git.

Exemplo de `.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc

.env
credentials/client_secret.json
token.json
.runtime/

data/salas.csv
```

---

# 22. Renovação da assinatura Workspace Events

Assinaturas da Workspace Events API possuem expiração.

Quando o payload não inclui os dados completos do recurso, a duração máxima normalmente é de até 7 dias.

A aplicação tenta encontrar/criar a assinatura ao iniciar. Para uso contínuo, mantenha a aplicação responsável por renovar a assinatura antes da expiração ou reinicie-a regularmente.

---

# 23. Documentação oficial

Google Meet REST API:

https://developers.google.com/workspace/meet/api/guides/overview

Google Meet API OAuth scopes:

https://developers.google.com/identity/protocols/oauth2/scopes#meet

Google Workspace Events API:

https://developers.google.com/workspace/events

Eventos do Google Meet:

https://developers.google.com/workspace/events/guides/events-meet

Cloud Pub/Sub:

https://cloud.google.com/pubsub/docs

---

# Resumo rápido

Depois que Google Cloud e OAuth estiverem configurados, para executar novamente normalmente basta:

```powershell
cd C:\caminho\para\eyes

Set-ExecutionPolicy -Scope Process Bypass

.\scripts\run.ps1
```

e acessar:

```text
http://127.0.0.1:8000
```
