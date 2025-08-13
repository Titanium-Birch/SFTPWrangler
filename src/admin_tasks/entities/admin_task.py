from dataclasses import dataclass
from typing import Literal

from admin_tasks.entities.backfill_categories import BackfillCategories
from admin_tasks.entities.backfill_incoming import BackfillIncoming
from admin_tasks.entities.backfill_api_wise import BackfillApiWise
from dataclasses_json import DataClassJsonMixin


@dataclass
class AdminTask(DataClassJsonMixin):
    name: Literal["backfill_categories", "backfill_incoming"]
    task: BackfillCategories | BackfillIncoming | BackfillApiWise
