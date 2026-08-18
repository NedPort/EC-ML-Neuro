"""
Run the data audit for one downloaded CISS case.
"""

import argparse

from src.audit.case_auditor import (
    CaseAuditor,
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create the comprehensive audit "
            "for one CISS case."
        )
    )

    parser.add_argument(
        "case_id",
        type=int,
        help="CISS case ID, such as 6028 or 7009",
    )

    parser.add_argument(
        "--data-root",
        default="data",
        help="Root data directory",
    )

    arguments = parser.parse_args()    ## This case number is temporary

    auditor = CaseAuditor(
        data_root=arguments.data_root
    )

    auditor.audit_case(
        arguments.case_id
    )


if __name__ == "__main__":
    main() 