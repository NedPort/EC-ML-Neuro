"""
Prompt construction for individual-image visual evidence extraction.
"""

import json

from src.semantic.schemas.visual_evidence import (
    VISUAL_EVIDENCE_SCHEMA,
)


PROMPT_VERSION = "visual_evidence_v1.0"


SYSTEM_PROMPT = """
You are a Visual Evidence Expert analyzing photographs from
motor-vehicle crash investigations.

Your task is to record only information directly supported by the
provided photograph. Do not perform crash reconstruction in this
stage.

Follow these rules:

1. Separate visible evidence from assumptions.
2. Do not infer exact speed, Delta-V, impact force, injury outcome,
   event sequence, or definitive collision configuration.
3. Do not assume that a missing component was removed by the crash.
   It may have been removed, repositioned, or covered during the
   investigation.
4. Record investigative artifacts such as measurement gauges,
   targets, labels, coverings, and component markings.
5. Use left and right from the vehicle's perspective:
   - In a direct front view, image-left corresponds to vehicle-right.
   - In a direct rear view, image-left corresponds to vehicle-left.
6. Use "not_visible" when the photograph does not show enough evidence.
   Do not use "visible_absent" simply because an item is outside the
   camera view.
7. Visible severity describes only the apparent visual extent. It is
   not a repair-cost estimate, injury estimate, or structural rating.
8. Describe uncertainty explicitly.
9. Create separate damage observations for distinct components or
   regions.
10. Return JSON only. Do not include Markdown, commentary, or text
    outside the required JSON object.
11. The output must conform exactly to the supplied JSON schema.
""".strip()


def build_visual_evidence_request(image_record):
    """
    Build a provider-independent request for one image.
    """

    required_fields = [
        "case_id",
        "asset_id",
        "vehicle_number",
        "ciss_category",
        "normalized_category",
        "relative_path",
    ]

    missing_fields = [
        field
        for field in required_fields
        if field not in image_record
    ]

    if missing_fields:
        raise ValueError(
            "Image record is missing required fields: "
            + ", ".join(missing_fields)
        )

    context = {
        "case_id": image_record["case_id"],
        "asset_id": image_record["asset_id"],
        "vehicle_number": image_record["vehicle_number"],
        "ciss_category": image_record["ciss_category"],
        "normalized_category": (
            image_record["normalized_category"]
        ),
        "relative_path": image_record["relative_path"],
    }

    user_prompt = f"""
Analyze the attached original crash-investigation photograph.

The following information comes from the CISS asset registry and may
be used only for image identity, grouping, and viewpoint context:

{json.dumps(context, indent=2)}

Produce one individual-image visual-evidence record.

Important:
- Analyze the photograph independently from crash metadata.
- Do not use case summaries, CDC codes, EDR values, or investigator
  conclusions in this first visual pass.
- Use the exact case ID, asset ID, path, vehicle number, and category
  provided above.
- Set model_provenance using the actual provider, model, prompt
  version, and processing time.
- Prompt version: {PROMPT_VERSION}
- Return valid JSON matching the supplied schema.
""".strip()

    return {
        "prompt_version": PROMPT_VERSION,
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "json_schema": VISUAL_EVIDENCE_SCHEMA,
        "image_record": context,
    }
