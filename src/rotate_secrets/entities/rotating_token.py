from dataclasses import dataclass
from typing import Any, Dict

from dataclasses_json import DataClassJsonMixin


@dataclass
class RotatingToken(DataClassJsonMixin):
    secret_value: Dict[str, Any]
    valid_until: int