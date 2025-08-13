"""
test_file_transformer.py
Tests the behavior of the FileTransformer class.
"""

import pytest
import os
from utils.file_transformer import RemoveNewlinesInCsvFieldsTransformer
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class Test_FileTransformer_Module:
    # Happy path for RemoveNewlinesInCsvFields: remove some unwanted newlines
    @pytest.mark.unit
    def test_remove_newlines_in_csv_fields(self):
        self._assert_transformation_equality('funny-csv-with-newlines-in-fields.csv', 
                                             'funny-csv-with-newlines-in-fields-transformed-into-proper-csv.csv',
                                             RemoveNewlinesInCsvFieldsTransformer())

    # Happy path for RemoveNewlinesInCsvFields: no need to do anything
    @pytest.mark.unit
    def test_remove_newlines_in_csv_fields_when_nothing_to_do(self):
        self._assert_transformation_equality('funny-csv-with-toprows.csv', 
                                             'funny-csv-with-toprows.csv',
                                             RemoveNewlinesInCsvFieldsTransformer())



    # returns the contents of the specified filename from the "test-files" directory
    def _testfile_contents(self, filename) -> str:
        dir = os.path.join(os.path.dirname(__file__), '..', 'files', 'transformer')
        filepath = os.path.join(dir, filename)
        with open(filepath, "r") as file:
            file_contents = file.read()
        return file_contents

    def _assert_transformation_equality(self, input_filename, filename_for_expected_result, transformer):
        input_contents      = self._testfile_contents(input_filename)
        expected_contents   = self._testfile_contents(filename_for_expected_result)

        transformed_content = transformer.transform(csv_content=input_contents)

        assert transformed_content == expected_contents

    def _expect_an_exception(self, input_filename, transformer):
        input_contents      = self._testfile_contents(input_filename)

        with pytest.raises(Exception):
            transformer.transform(csv_content=input_contents)
