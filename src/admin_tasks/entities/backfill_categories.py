from dataclasses import dataclass, field
from typing import Optional

from dataclasses_json import DataClassJsonMixin


@dataclass
class BackfillCategories(DataClassJsonMixin):
    peer_id: str
    category_id: Optional[str] = field(default=None)
    start_timestamp: Optional[str] = field(default=None)
    end_timestamp: Optional[str] = field(default=None)
