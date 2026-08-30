# Monitor Google Meet — 70 salas

Dashboard local para Windows 11 que monitora as salas do CSV sem entrar nas chamadas.

Exibe:

- sala ativa/inativa;
- quantidade de participantes ativos;
- gravação ativa ou não;
- botão **Entrar**;
- totais gerais.

A aplicação usa Google Meet REST API + Google Workspace Events API + Google Cloud Pub/Sub. A assinatura é feita no usuário proprietário, portanto recebe eventos de todos os espaços Meet pertencentes a essa conta.

## Estrutura

```text
meet_monitor/
  app/                  backend FastAPI
  static/               dashboard
  data/salas.csv        CSV fornecido
  credentials/          OAuth client_secret.json
  scripts/setup.ps1
  scripts/configure_google_cloud.ps1
  scripts/run.ps1
```

## 1. Requisitos

- Windows 11
- Python 3.11+
- Google Cloud CLI (`gcloud`)
- Conta Google Workspace proprietária das salas
- Projeto Google Cloud

## 2. Criar cliente OAuth

No Google Cloud Console, no MESMO projeto:

1. Configure a Google Auth Platform / tela de consentimento.
2. Crie um **OAuth Client ID**.
3. Tipo: **Desktop app / Aplicativo para computador**.
4. Baixe o JSON.
5. Renomeie para `client_secret.json`.
6. Salve em:

```text
credentials\client_secret.json
```

A aplicação pedirá login no navegador na primeira execução e salvará `token.json` localmente.

## 3. Instalar

No PowerShell, dentro da pasta do projeto:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
```

## 4. Configurar Google Cloud / Pub/Sub

Primeiro autentique o CLI:

```powershell
gcloud auth login
```

Depois:

```powershell
.\scripts\configure_google_cloud.ps1 -ProjectId "SEU_PROJECT_ID"
```

O script:

- habilita Meet REST API, Workspace Events API, Pub/Sub e People API;
- cria tópico `meet-monitor-events`;
- concede `Pub/Sub Publisher` para `meet-api-event-push@system.gserviceaccount.com`;
- cria a subscription pull `meet-monitor-events-sub`;
- cria service account `meet-event-listener` com `Pub/Sub Subscriber`;
- concede ao usuário atual permissão de impersonar essa service account.

No final execute exatamente o comando mostrado, semelhante a:

```powershell
gcloud auth application-default login --impersonate-service-account=meet-event-listener@SEU_PROJECT_ID.iam.gserviceaccount.com
```

Isso configura as credenciais que o processo local usa para consumir Pub/Sub.

## 5. Configurar `.env`

O `setup.ps1` cria `.env` copiando `.env.example`.

Edite:

```env
GOOGLE_CLOUD_PROJECT=SEU_PROJECT_ID
PUBSUB_TOPIC_ID=meet-monitor-events
PUBSUB_SUBSCRIPTION_ID=meet-monitor-events-sub
ROOMS_CSV=data/salas.csv
HOST=127.0.0.1
PORT=8000
RECONCILE_SECONDS=45
```

## 6. Executar

```powershell
.\scripts\run.ps1
```

Na primeira execução, o navegador abrirá para autorizar sua conta institucional.

Depois acesse:

```text
http://127.0.0.1:8000
```

## Como funciona

### Inicialização

Para cada URL do CSV, a aplicação extrai o meeting code e chama `spaces.get`. O retorno fornece o ID canônico do espaço e informa se existe uma `activeConference`.

Se a sala estiver ativa, a aplicação consulta:

- participantes com `latestEndTime IS NULL`;
- recursos de gravação e considera `state == STARTED` como gravação ativa.

### Tempo real

A aplicação cria/renova uma única Workspace Events subscription no usuário proprietário para:

```text
google.workspace.meet.conference.v2.started
google.workspace.meet.conference.v2.ended
google.workspace.meet.participant.v2.joined
google.workspace.meet.participant.v2.left
google.workspace.meet.recording.v2.started
google.workspace.meet.recording.v2.ended
```

Os eventos vão ao tópico Pub/Sub e o processo local usa uma pull subscription. Ao receber um evento, ele identifica o `conferenceRecord`, recupera o `space` correspondente e atualiza a sala.

Também existe reconciliação periódica (`RECONCILE_SECONDS`) para corrigir eventual evento perdido ou estado obtido antes do listener iniciar.

## Segurança

Não versione nem compartilhe:

```text
credentials/client_secret.json
token.json
.env
```

O servidor escuta somente `127.0.0.1`, portanto o dashboard não fica acessível por outros computadores da rede.

## Observações

- A Workspace Events subscription expira. O aplicativo tenta encontrar e renovar a assinatura para o TTL máximo (até 7 dias sem dados de recurso) em toda inicialização.
- O meeting code do URL é usado apenas para resolver o ID canônico do espaço em cada inicialização.
- Se uma sala do CSV não pertencer à conta autenticada, a API pode negar dados de participantes/gravações.
