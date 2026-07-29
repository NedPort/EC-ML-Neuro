import json
from pathlib import Path

from src.semantic.prompts.visual_evidence_prompt import (
    build_visual_evidence_request,
)


def main():
    groups_path = Path(
        "data/processed/6028/"
        "semantic/images/image_groups.json"
    )

    with groups_path.open(
        "r",
        encoding="utf-8",
    ) as input_file:
        grouping = json.load(input_file)

    selected_image = next(
        image
        for image in grouping["images"]
        if image["asset_id"] == "case_6028_asset_0026"
    )

    request = build_visual_evidence_request(
        selected_image
    )

    print("Prompt version:", request["prompt_version"])
    print()
    print("SYSTEM PROMPT")
    print(request["system_prompt"])
    print()
    print("USER PROMPT")
    print(request["user_prompt"])
    print()
    print(
        "Schema:",
        request["json_schema"]["title"],
    )


if __name__ == "__main__":
    main()
    