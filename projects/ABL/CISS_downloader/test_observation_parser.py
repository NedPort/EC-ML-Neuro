from src.edr.parsers.observation_parser import (
    parse_observation,
)


TEST_ROWS = [
    [
        "Maximum Delta-V, Longitudinal (km/h)",
        "-24",
    ],

    [
        "ETC Lamp",
        "Off, Off, Off, Off, Off, Off, Off, Off",
    ],

    [
        "Time (msec)",
        "Delta-V, Longitudinal (km/h)",
        "Delta-V, Lateral (km/h)",
    ],

    [
        "SYSTEM STATUS AT EVENT "
        "(MOST RECENT EVENT)",
    ],

    [
        "Gear Position (ATX)",
        "Drive",
        "Drive",
        "Drive",
        "Drive",
        "Drive",
    ],

    [
        "Side Crash, Left",
        "Yes",
    ],

    [],
]


for index, row in enumerate(
    TEST_ROWS
):
    result = parse_observation(
        row=row,
        row_index=index,
        section_context="TEST SECTION",
    )

    print("=" * 70)
    print(
        f"Input: {row}"
    )

    print(
        f"Type: {result.observation_type}"
    )

    print(
        f"Label: {result.label}"
    )

    print(
        f"Values: {result.values}"
    )

    print(
        f"Value count: {result.value_count}"
    )

    print(
        f"Packed sequence: "
        f"{result.packed_sequence}"
    )

    print(
        f"Repeated: {result.is_repeated}"
    )

    print(
        f"Section: "
        f"{result.section_context}"
    )