from src.edr.validation.router_regression import (
    compare_raw_row,
    summarize_results,
    validate_regression,
)


print("\n")
print("=" * 80)
print("ROUTER REGRESSION VALIDATION MODULE TEST")
print("=" * 80)


validation_tests = [
    compare_raw_row(
        row=[
            "Maximum Delta-V, Longitudinal (km/h)",
            "-24",
        ],
        row_index=0,
        section_context="CRASH PULSE",
        expected_destination="group5",
        expected_family="delta_v_summary",
        report_id="test001",
        case_id="case001",
        vehicle_number="1",
        source_format="csv",
    ),

    compare_raw_row(
        row=[
            "Safety Belt Status, Driver",
            "Buckled",
        ],
        row_index=1,
        section_context="SYSTEM STATUS AT EVENT",
        expected_destination="group3",
        expected_family="occupant_restraint_status",
        report_id="test002",
        case_id="case002",
        vehicle_number="1",
        source_format="csv",
    ),

    compare_raw_row(
        row=[
            "Ignition Cycles at Investigation",
            "42",
        ],
        row_index=2,
        section_context="MODULE INFORMATION",
        expected_destination="group6",
        expected_family="ignition_cycle_readout",
        report_id="test003",
        case_id="case003",
        vehicle_number="1",
        source_format="csv",
    ),
]


for result in validation_tests:
    print("-" * 80)
    print(f"Label: {result.raw_label}")
    print(f"Expected: {result.expected_destination}")
    print(f"Actual: {result.actual_destination}")
    print(f"Expected family: {result.expected_family}")
    print(f"Actual family: {result.actual_family}")
    print(f"Level: {result.regression_level}")
    print(f"Status: {result.regression_status}")


summary = summarize_results(
    validation_tests
)

checks = validate_regression(
    validation_tests
)


print("\nSUMMARY")
print(summary)

print("\nVALIDATION")
print(checks)