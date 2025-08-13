import pytest
from datetime import date, datetime
from api.utils.datetime_range_calculator import BackfillDatetimeRangeCalculator

class Test_Backfill_Datetime_Range_Calculator:

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "start_date, end_date, expected_ranges, exclusive",
        [
            (
                date(2023, 9, 11),
                date(2023, 9, 11),
                [
                    ("2023-09-11T00:00:00.000Z", "2023-09-11T23:59:59.999Z"),
                ],
                False,
            ),
            (
                date(2023, 9, 10),
                date(2023, 9, 12),
                [
                    ("2023-09-10T00:00:00.000Z", "2023-09-10T23:59:59.999Z"),
                    ("2023-09-11T00:00:00.000Z", "2023-09-11T23:59:59.999Z"),
                    ("2023-09-12T00:00:00.000Z", "2023-09-12T23:59:59.999Z"),
                ],
                False,
            ),
            (
                # leap year date range
                date(2024, 2, 28),
                date(2024, 3, 1),
                [
                    ("2024-02-28T00:00:00.000Z", "2024-02-28T23:59:59.999Z"),
                    ("2024-02-29T00:00:00.000Z", "2024-02-29T23:59:59.999Z"),
                    ("2024-03-01T00:00:00.000Z", "2024-03-01T23:59:59.999Z"),
                ],
                False
            ),
            (
                date(2023, 9, 11),
                date(2023, 9, 11),
                [
                    ("2023-09-10T23:59:59.999Z", "2023-09-12T00:00:00.000Z"),
                ],
                True,
            ),
            (
                date(2023, 9, 10),
                date(2023, 9, 12),
                [
                    ("2023-09-09T23:59:59.999Z", "2023-09-11T00:00:00.000Z"),
                    ("2023-09-10T23:59:59.999Z", "2023-09-12T00:00:00.000Z"),
                    ("2023-09-11T23:59:59.999Z", "2023-09-13T00:00:00.000Z"),
                ],
                True,
            ),
            (
                # leap year date range
                date(2024, 2, 28),
                date(2024, 3, 1),
                [
                    ("2024-02-27T23:59:59.999Z", "2024-02-29T00:00:00.000Z"),
                    ("2024-02-28T23:59:59.999Z", "2024-03-01T00:00:00.000Z"),
                    ("2024-02-29T23:59:59.999Z", "2024-03-02T00:00:00.000Z"),
                ],
                True
            ),
        ]
    )
    def test_should_calculate_ranges_for_each_day_between_start_and_end(self, start_date: date, end_date: date, expected_ranges: list, exclusive: bool) -> None:
        calc = BackfillDatetimeRangeCalculator(current_datetime=lambda: datetime.now(), start_date=start_date, end_date=end_date, exclusive=exclusive)
        results = calc.calculate()

        assert len(results) == len(expected_ranges), f"Expected {len(expected_ranges)} ranges, but got {len(results)}"

        for result, (expected_start, expected_end) in zip(results, expected_ranges):
            assert result.start_time_iso == expected_start, f"Expected start time: {expected_start}, but got {result.start_time_iso}"
            assert result.end_time_iso == expected_end, f"Expected end time: {expected_end}, but got {result.end_time_iso}"
