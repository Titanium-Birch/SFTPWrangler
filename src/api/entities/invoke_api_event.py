
from dataclasses import dataclass

from dataclasses_json import DataClassJsonMixin


@dataclass
class InvokeApiEvent(DataClassJsonMixin):
    id: str