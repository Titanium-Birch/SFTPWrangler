from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from dataclasses_json import DataClassJsonMixin


@dataclass
class BackfillApiArch(DataClassJsonMixin):
    peer_id: str
    start_date: date
    end_date: date
    entities: Optional[List[str]] = field(default=None)

    @staticmethod
    def from_dict(data: dict) -> "BackfillApiArch":
        data["start_date"] = date.fromisoformat(data["start_date"])
        data["end_date"] = date.fromisoformat(data["end_date"])
        return BackfillApiArch(**data)
