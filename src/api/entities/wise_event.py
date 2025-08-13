from dataclasses import dataclass, field
from typing import Optional

from dataclasses_json import DataClassJsonMixin, config


@dataclass
class WiseEventDataResource(DataClassJsonMixin):
    id: int
    profile_id: int
    type: str


@dataclass
class WiseEventData(DataClassJsonMixin):
    resource: WiseEventDataResource
    amount: Optional[str] = field(default=None)
    balance_id: Optional[str] = field(default=None, metadata=config(exclude=lambda value: value is None))
    currency: Optional[str] = field(default=None)
    transaction_type: Optional[str] = field(default=None)
    occurred_at: Optional[str] = field(default=None)
    transfer_reference: Optional[str] = field(default=None, metadata=config(exclude=lambda value: value is None))
    channel_name: Optional[str] = field(default=None, metadata=config(exclude=lambda value: value is None))


@dataclass
class WiseEvent(DataClassJsonMixin):
    subscription_id: str
    event_type: str
    schema_version: str
    sent_at: str
    data: WiseEventData
