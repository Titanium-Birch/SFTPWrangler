from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


class FileTransformer(ABC):
    @abstractmethod
    def transform(self, csv_content: str) -> str:
        """Subclasses must implement this to transform the given CSV content string.

        Args:
            csv_content (str): string csv content to be transformed

        Returns:
            str: transformed content
        """
        pass

    @staticmethod
    def create_transformer(class_name: str) -> FileTransformer:
        """
        Returns an instance of the specified transformer class.
        :param class_name: name of the transformer class to instantiate
        :return: FileTransformer
        """
        class_map = {
            "RemoveNewlinesInCsvFieldsTransformer": RemoveNewlinesInCsvFieldsTransformer,
        }
        if class_name in class_map:
            return class_map[class_name]()
        else:
            raise ValueError(f"Invalid transformer class name: {class_name}")


class RemoveNewlinesInCsvFieldsTransformer(FileTransformer):
    def transform(self, csv_content: str) -> str:
        """This transformer removes newlines from fields in a CSV file, replacing them with a
        pipe delimiter.

        This helps make CSV files usable in Athena, which expects newlines to
        only indicate a new row in a CSV file, not a new line in a field.

        Our algorithm identifies fields enclosed in double quotes and replaces any newlines
        found within these quoted fields.

        Assumptions/Requirements:
        1. The input CSV must correctly escape fields that contain special characters like commas or newlines using
           double quotes. For example, a field containing a newline should be enclosed in double quotes.
        2. Fields that contain double quotes themselves must escape these quotes with another double quote.

        Args:
            csv_content (str): string csv content to be transformed

        Returns:
            str: transformed content
        """
        # Replace newlines inside quoted strings
        in_quotes = False
        current_field = []

        for char in csv_content:
            if char == '"':
                in_quotes = not in_quotes
            if char == "\n" and in_quotes:
                current_field.append(" | ")  # Replaces newline inside quotes with pipe delimiter
            else:
                current_field.append(char)

        # Join all characters back into the cleaned full content
        return "".join(current_field)
