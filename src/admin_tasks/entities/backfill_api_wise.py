from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from dataclasses_json import DataClassJsonMixin


@dataclass
class BackfillApiWise(DataClassJsonMixin):
    peer_id: str
    start_date: date
    end_date: date
    sub_accounts: Optional[List[str]] = field(default=None)

    @staticmethod
    def from_dict(data: dict) -> "BackfillApiWise":
        data["start_date"] = date.fromisoformat(data["start_date"])
        data["end_date"] = date.fromisoformat(data["end_date"])
        return BackfillApiWise(**data)
