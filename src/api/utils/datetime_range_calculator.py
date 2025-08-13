from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List

from dataclasses_json import DataClassJsonMixin


@dataclass
class DatetimeRange(DataClassJsonMixin):
    start_time_iso: str
    end_time_iso: str

    def file_base_name(self: "DatetimeRange") -> str:
        """Returns the DatetimeRange formatted as a file basename without the extension.

        Returns:
            str: formatted str, e.g. 20241113_080000_to_20241113_180000
        """
        start_dt = datetime.fromisoformat(self.start_time_iso.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(self.end_time_iso.replace("Z", "+00:00"))

        start_str = start_dt.strftime("%Y%m%d_%H%M%S")
        end_str = end_dt.strftime("%Y%m%d_%H%M%S")
        return f"{start_str}_to_{end_str}"


class DatetimeRangeCalculator:
    def now(self: "DatetimeRangeCalculator") -> datetime:
        """Returns the current datetime.

        Returns:
            datetime: the current datetime
        """
        return datetime.now()

    def calculate(self: "DatetimeRangeCalculator") -> List[DatetimeRange]:
        """Subclasses must implement this to return a list of DatetimeRanges
        that are applicable in the callers context.

        Returns:
            List[DatetimeRange]: a list of DatetimeRange instances
        """
        return list()


class PreviousDayDatetimeRangeCalculator(DatetimeRangeCalculator):
    def __init__(self, current_datetime: Callable[[], datetime], exclusive: bool = False) -> None:
        self.current_datetime = current_datetime
        self.exclusive = exclusive

    def now(self: "PreviousDayDatetimeRangeCalculator") -> datetime:
        return self.current_datetime()

    def calculate(self: "PreviousDayDatetimeRangeCalculator") -> List[DatetimeRange]:
        """Returns a single DatetimeRange that includes the entirety of the
        previous day.

        Returns:
            List[DatetimeRange]: a range denoting the previous day
        """
        now = self.current_datetime().astimezone(timezone.utc)
        end_of_previous_day = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            milliseconds=(0 if self.exclusive else 1)
        )
        start_of_previous_day = (
            end_of_previous_day - timedelta(hours=24) + timedelta(milliseconds=(-1 if self.exclusive else 1))
        )

        start_time_iso = start_of_previous_day.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        end_time_iso = end_of_previous_day.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        return [DatetimeRange(start_time_iso=start_time_iso, end_time_iso=end_time_iso)]


class BackfillDatetimeRangeCalculator(DatetimeRangeCalculator):
    def __init__(
        self, current_datetime: Callable[[], datetime], start_date: date, end_date: date, exclusive: bool = False
    ) -> None:
        if start_date is None or end_date is None:
            raise ValueError("start_date and end_date must not be None.")

        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date.")

        self.current_datetime = current_datetime
        self.start_date = start_date
        self.end_date = end_date
        self.exclusive = exclusive

    def now(self: "BackfillDatetimeRangeCalculator") -> datetime:
        return self.current_datetime()

    def calculate(self: "BackfillDatetimeRangeCalculator") -> List[DatetimeRange]:
        """Generates a list of DatetimeRanges for each day between start_date
        and end_date.

        Returns:
            List[DatetimeRange]: contain an item per day
        """
        date_ranges = []

        current_date = self.start_date
        while current_date <= self.end_date:
            start_of_day = datetime.combine(current_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            start_of_day = start_of_day - timedelta(milliseconds=(1 if self.exclusive else 0))
            start_time_iso = start_of_day.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            end_of_day = start_of_day + timedelta(hours=24, milliseconds=(1 if self.exclusive else -1))
            end_time_iso = end_of_day.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            date_ranges.append(DatetimeRange(start_time_iso=start_time_iso, end_time_iso=end_time_iso))

            current_date += timedelta(days=1)

        return date_ranges
