import pytest
from datetime import datetime, timezone

from api.utils.datetime_range_calculator import PreviousDayDatetimeRangeCalculator

class Test_Previous_Day_Datetime_Range_Calculator:

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "current_time, expected_start, expected_end, exclusive",
        [
            (
                # Case 1: If current time is on 2023-09-12 12:00:00.000
                datetime(2023, 9, 12, 12, 0, 0, 0, tzinfo=timezone.utc),
                "2023-09-11T00:00:00.000Z",
                "2023-09-11T23:59:59.999Z",
                False
            ),
            (
                # Case 2: If current time is on 2023-09-12 00:00:00.000
                datetime(2023, 9, 12, 0, 0, 0, 0, tzinfo=timezone.utc),
                "2023-09-11T00:00:00.000Z",
                "2023-09-11T23:59:59.999Z",
                False
            ),
            (
                # Case 3: If current time is on 2023-09-12 23:59:59.999
                datetime(2023, 9, 12, 23, 59, 59, 999, tzinfo=timezone.utc),
                "2023-09-11T00:00:00.000Z",
                "2023-09-11T23:59:59.999Z",
                False
            ),
            (
                # Case 4: If current time is on 2024-02-29 16:38:02.455
                datetime(2024, 2, 29, 16, 38, 2, 455, tzinfo=timezone.utc),
                "2024-02-28T00:00:00.000Z",
                "2024-02-28T23:59:59.999Z",
                False
            ),
            (
                # Case 5: If current time is on 2024-03-01 00:10:01.455
                datetime(2024, 3, 1, 0, 10, 1, 455, tzinfo=timezone.utc),
                "2024-02-29T00:00:00.000Z",
                "2024-02-29T23:59:59.999Z",
                False
            ),
            (
                # Case 1: If current time is on 2023-09-12 12:00:00.000
                datetime(2023, 9, 12, 12, 0, 0, 0, tzinfo=timezone.utc),
                "2023-09-10T23:59:59.999Z",
                "2023-09-12T00:00:00.000Z",
                True
            ),
            (
                # Case 2: If current time is on 2023-09-12 00:00:00.000
                datetime(2023, 9, 12, 0, 0, 0, 0, tzinfo=timezone.utc),
                "2023-09-10T23:59:59.999Z",
                "2023-09-12T00:00:00.000Z",
                True
            ),
            (
                # Case 3: If current time is on 2023-09-12 23:59:59.999
                datetime(2023, 9, 12, 23, 59, 59, 999, tzinfo=timezone.utc),
                "2023-09-10T23:59:59.999Z",
                "2023-09-12T00:00:00.000Z",
                True
            ),
            (
                # Case 4: If current time is on 2024-02-29 16:38:02.455
                datetime(2024, 2, 29, 16, 38, 2, 455, tzinfo=timezone.utc),
                "2024-02-27T23:59:59.999Z",
                "2024-02-29T00:00:00.000Z",
                True
            ),
            (
                # Case 5: If current time is on 2024-03-01 00:10:01.455
                datetime(2024, 3, 1, 0, 10, 1, 455, tzinfo=timezone.utc),
                "2024-02-28T23:59:59.999Z",
                "2024-03-01T00:00:00.000Z",
                True
            ),
        ]
    )
    def test_should_calculate_a_single_range_for_the_previous_day(self, current_time: datetime, expected_start: str, expected_end: str, exclusive: bool) -> None:
        calc = PreviousDayDatetimeRangeCalculator(current_datetime=lambda: current_time, exclusive=exclusive)
        results = calc.calculate()
        assert len(results) == 1

        result = results[0]
        assert result.end_time_iso == expected_end, f"Expected end time: {expected_end}, but got {result.end_time_iso}"
        assert result.start_time_iso == expected_start, f"Expected start time: {expected_start}, but got {result.start_time_iso}"
