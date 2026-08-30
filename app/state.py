from threading import RLock
from typing import Dict, Optional
from .models import RoomState


class StateStore:
    def __init__(self):
        self.lock = RLock()
        self.rooms: Dict[str, RoomState] = {}
        self.by_space: Dict[str, str] = {}
        self.conference_to_space: Dict[str, str] = {}

    def set_rooms(self, rooms):
        with self.lock:
            self.rooms = {r.meet_url: r for r in rooms}

    def index_space(self, room: RoomState):
        if room.space_name:
            with self.lock:
                self.by_space[room.space_name] = room.meet_url

    def room_for_space(self, space_name: str) -> Optional[RoomState]:
        with self.lock:
            url = self.by_space.get(space_name)
            return self.rooms.get(url) if url else None

    def snapshot(self):
        with self.lock:
            return [r.to_dict() for r in self.rooms.values()]

STORE = StateStore()
