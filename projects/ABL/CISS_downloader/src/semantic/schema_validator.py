"""
Validation utilities for semantic JSON records.
"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator


class SemanticSchemaValidator:
    """
    Validate semantic records against a JSON schema.
    """

    def __init__(self, schema):
        self.schema = schema

        # Confirm that the schema itself is valid.
        Draft202012Validator.check_schema(schema)

        self.validator = Draft202012Validator(schema)

    def validate_record(self, record):
        """
        Validate a Python dictionary.

        Returns a list of readable validation errors.
        """

        errors = sorted(
            self.validator.iter_errors(record),
            key=lambda error: list(error.absolute_path),
        )

        messages = []

        for error in errors:
            location = ".".join(
                str(part)
                for part in error.absolute_path
            )

            if not location:
                location = "<root>"

            messages.append(
                f"{location}: {error.message}"
            )

        return messages

    def validate_file(self, file_path):
        """
        Load and validate a semantic JSON file.
        """

        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(
                f"Semantic file does not exist: {file_path}"
            )

        try:
            with file_path.open(
                "r",
                encoding="utf-8",
            ) as input_file:
                record = json.load(input_file)

        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Semantic file is not valid JSON: {file_path}"
            ) from error

        errors = self.validate_record(record)

        if errors:
            print(f"Validation failed: {file_path}")

            for message in errors:
                print(f"  - {message}")

            return False

        print(f"Semantic record is valid: {file_path}")

        return True
    