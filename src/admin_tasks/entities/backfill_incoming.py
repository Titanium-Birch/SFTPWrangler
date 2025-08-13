from dataclasses import dataclass, field
from typing import Optional

from dataclasses_json import DataClassJsonMixin


@dataclass
class BackfillIncoming(DataClassJsonMixin):
    peer_id: str
    extension: str
    start_timestamp: Optional[str] = field(default=None)
    end_timestamp: Optional[str] = field(default=None)
