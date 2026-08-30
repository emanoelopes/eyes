from datetime import datetime, timezone
from urllib.parse import quote
import requests
from google.auth.transport.requests import AuthorizedSession


class MeetClient:
    def __init__(self, credentials):
        self.session = AuthorizedSession(credentials)

    def _get(self, url, params=None):
        r = self.session.get(url, params=params, timeout=20)
        if not r.ok:
            raise RuntimeError(f'Google API {r.status_code}: {r.text[:500]}')
        return r.json()

    def get_space(self, meeting_code):
        return self._get(f'https://meet.googleapis.com/v2/spaces/{quote(meeting_code)}')

    def get_conference(self, conference_name):
        return self._get(f'https://meet.googleapis.com/v2/{conference_name}')

    def active_participant_count(self, conference_name):
        # Pagina para não depender de totalSize e contar corretamente >250 participantes.
        count = 0
        page_token = None
        while True:
            params = {'pageSize': 250, 'filter': 'latestEndTime IS NULL'}
            if page_token:
                params['pageToken'] = page_token
            data = self._get(
                f'https://meet.googleapis.com/v2/{conference_name}/participants',
                params=params,
            )
            count += len(data.get('participants', []))
            page_token = data.get('nextPageToken')
            if not page_token:
                break
        return count

    def is_recording(self, conference_name):
        data = self._get(f'https://meet.googleapis.com/v2/{conference_name}/recordings')
        return any(r.get('state') == 'STARTED' for r in data.get('recordings', []))

    def resolve_room(self, room):
        try:
            if not room.meeting_code:
                raise RuntimeError('Link do Meet inválido')
            data = self.get_space(room.meeting_code)
            room.space_name = data.get('name')
            room.meet_url = data.get('meetingUri') or room.meet_url
            active = data.get('activeConference') or {}
            room.conference_record = active.get('conferenceRecord')
            room.active = bool(room.conference_record)
            self.refresh_room(room)
        except Exception as e:
            room.error = str(e)
            room.last_update = datetime.now(timezone.utc).isoformat()

    def refresh_room(self, room):
        try:
            if not room.space_name and room.meeting_code:
                data = self.get_space(room.meeting_code)
                room.space_name = data.get('name')
                room.meet_url = data.get('meetingUri') or room.meet_url
            elif room.space_name:
                data = self._get(f'https://meet.googleapis.com/v2/{room.space_name}')
            else:
                raise RuntimeError('Sala sem space_name')

            active = data.get('activeConference') or {}
            conf = active.get('conferenceRecord')
            room.conference_record = conf
            room.active = bool(conf)
            if conf:
                c = self.get_conference(conf)
                room.start_time = c.get('startTime')
                room.participants = self.active_participant_count(conf)
                room.recording = self.is_recording(conf)
            else:
                room.participants = 0
                room.recording = False
                room.start_time = None
            room.error = None
        except Exception as e:
            room.error = str(e)
        finally:
            room.last_update = datetime.now(timezone.utc).isoformat()
