from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class RoomState:
    title: str
    meet_url: str
    day: str = ''
    space_name: Optional[str] = None
    meeting_code: Optional[str] = None
    active: bool = False
    participants: int = 0
    participant_names: list = None
    recording: bool = False
    conference_record: Optional[str] = None
    start_time: Optional[str] = None
    last_update: Optional[str] = None
    error: Optional[str] = None
    group: Optional[str] = None
    formador: Optional[str] = None
    formador_presente: bool = False
    formador_localizacao: Optional[str] = None

    def __post_init__(self):
        if self.participant_names is None:
            self.participant_names = []

    def to_dict(self):
        return asdict(self)
