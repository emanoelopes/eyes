from datetime import datetime, timezone
from urllib.parse import quote
import time

from google.auth.transport.requests import AuthorizedSession


class MeetClient:
    def __init__(self, credentials):
        self.session = AuthorizedSession(credentials)

    def _get(self, url, params=None):
        for attempt in range(4):
            r = self.session.get(url, params=params, timeout=20)

            if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt)
                continue

            if not r.ok:
                raise RuntimeError(
                    f"Google API {r.status_code}: {r.text[:500]}"
                )

            return r.json()

        raise RuntimeError("Falha ao consultar Google Meet API")

    def get_space(self, meeting_code):
        return self._get(
            f"https://meet.googleapis.com/v2/spaces/{quote(meeting_code)}"
        )

    def get_conference(self, conference_name):
        return self._get(
            f"https://meet.googleapis.com/v2/{conference_name}"
        )

    def active_participants(self, conference_name):
        """Retorna a lista de participantes ativos, cada um como dict com
        nome, horário de ingresso (`earliestStartTime`, ISO 8601 UTC) e o
        nome bruto do Meet. Um único participante pode ter entrado e saído
        várias vezes na mesma conferência; `earliestStartTime` é o início da
        sessão mais antiga ainda aberta (a API já filtra por
        `latest_end_time IS NULL`, ou seja, sessão atual em andamento)."""
        participants = []
        page_token = None

        while True:
            params = {
                "pageSize": 250,
                # IMPORTANTE: API usa snake_case.
                "filter": "latest_end_time IS NULL",
            }

            if page_token:
                params["pageToken"] = page_token

            data = self._get(
                f"https://meet.googleapis.com/v2/"
                f"{conference_name}/participants",
                params=params,
            )

            for p in data.get("participants", []):
                display_name = (
                    (p.get("signedinUser") or {}).get("displayName")
                    or (p.get("anonymousUser") or {}).get("displayName")
                    or (p.get("phoneUser") or {}).get("displayName")
                    or "Desconhecido"
                )
                participants.append({
                    "name": display_name,
                    "joined_at": p.get("earliestStartTime"),
                })

            page_token = data.get("nextPageToken")

            if not page_token:
                break

        return participants

    def is_recording(self, conference_name):
        data = self._get(
            f"https://meet.googleapis.com/v2/"
            f"{conference_name}/recordings"
        )

        return any(
            recording.get("state") == "STARTED"
            for recording in data.get("recordings", [])
        )

    def resolve_room(self, room):
        try:
            if not room.meeting_code:
                raise RuntimeError("Link do Meet inválido")

            data = self.get_space(room.meeting_code)

            room.space_name = data.get("name")
            room.meet_url = data.get("meetingUri") or room.meet_url

            self.refresh_room(room)

        except Exception as e:
            room.error = str(e)
            room.last_update = datetime.now(
                timezone.utc
            ).isoformat()

    def refresh_room(self, room):
        errors = []

        try:
            # Obtém o estado atual do espaço.
            if room.space_name:
                data = self._get(
                    f"https://meet.googleapis.com/v2/{room.space_name}"
                )

            elif room.meeting_code:
                data = self.get_space(room.meeting_code)
                room.space_name = data.get("name")
                room.meet_url = (
                    data.get("meetingUri") or room.meet_url
                )

            else:
                raise RuntimeError("Sala sem space_name")

        except Exception as e:
            room.error = str(e)
            room.last_update = datetime.now(
                timezone.utc
            ).isoformat()
            return

        active = data.get("activeConference") or {}
        conference_name = active.get("conferenceRecord")

        room.conference_record = conference_name
        room.active = bool(conference_name)

        if not conference_name:
            room.participants = 0
            room.participant_names = []
            room.participant_sessions = []
            room.recording = False
            room.start_time = None
            room.error = None
            room.last_update = datetime.now(
                timezone.utc
            ).isoformat()
            return

        # Informações gerais da conferência.
        try:
            conference = self.get_conference(conference_name)
            room.start_time = conference.get("startTime")

        except Exception as e:
            errors.append(f"conferência: {e}")

        # Participantes (nome + horário de ingresso de cada um).
        try:
            sessions = self.active_participants(
                conference_name
            )
            room.participant_sessions = sessions
            room.participant_names = [s["name"] for s in sessions]
            room.participants = len(sessions)

        except Exception as e:
            errors.append(f"participantes: {e}")

        # Gravação independente da consulta de participantes.
        try:
            room.recording = self.is_recording(
                conference_name
            )

        except Exception as e:
            errors.append(f"gravação: {e}")

        room.error = " | ".join(errors) if errors else None

        room.last_update = datetime.now(
            timezone.utc
        ).isoformat()