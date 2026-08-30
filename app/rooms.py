import csv
import re
from .models import RoomState

MEET_RE = re.compile(r'https://meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})', re.I)


def load_rooms(path):
    rooms = []
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get('Link do Meet') or '').strip()
            title = (row.get('Titulo') or '').strip()
            if not url or not title:
                continue
            m = MEET_RE.search(url)
            code = m.group(1).lower() if m else None
            rooms.append(RoomState(
                title=title,
                meet_url=url,
                day=(row.get('Dia') or '').strip(),
                meeting_code=code,
            ))
    return rooms
