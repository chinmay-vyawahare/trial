"""
AI-driven Excel note extractor.

Reads an Excel file containing a "Notes/Remarks" column per row and uses an
LLM to extract three fields per row:
  - forecasted_cx_start_date  (YYYY-MM-DD, converting "Wk-21" style refs)
  - is_blocked                (bool)
  - blocked_reason            (string)

Returns a DataFrame keyed by SITE_ID / PROJECT_ID with the extracted fields,
ready to upsert into ai_based_excel_upload.
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime

from app.services.assistant.llm import get_chat_llm


PROMPT = """
You are an expert data extractor.

Today's date: {current_date}
Current year: {current_year}
Current ISO week number: {current_week}

From the given NOTE, extract the following fields:

1. forecasted_cx_start_date:
   - Convert any week-based info (like "Wk-21") into an actual date (YYYY-MM-DD)
   - Use the provided current year and ISO week logic
   - Assume week starts on Monday
   - If no date info, return null

2. is_blocked:
   - True if the note indicates delay/blockers/issues
   - Otherwise False

3. blocked_reason:
   - If blocked, extract the reason
   - Else null

Return ONLY valid JSON:

{{
  "forecasted_cx_start_date": null,
  "is_blocked": false,
  "blocked_reason": null
}}

NOTE:
{note}
"""


def safe_json_parse(content: str):
    if not content:
        return {
            "forecasted_cx_start_date": None,
            "is_blocked": False,
            "blocked_reason": None,
        }
    try:
        return json.loads(content)
    except Exception:
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            return json.loads(content[start:end])
        except Exception:
            return {
                "forecasted_cx_start_date": None,
                "is_blocked": False,
                "blocked_reason": None,
            }


def clean_nan(df: pd.DataFrame) -> pd.DataFrame:
    return df.replace({np.nan: None, np.inf: None, -np.inf: None})


REQUIRED_COLUMNS = ("SITE_ID", "REGION", "MARKET", "PROJECT_ID")
NOTES_COLUMN_VARIANTS = ("Notes/Remarks", "Notes/ Remarks")


class InvalidExcelColumnsError(ValueError):
    """Raised when the uploaded Excel is missing required columns."""


def process_excel(file_path: str) -> pd.DataFrame:
    df = pd.read_excel(file_path)
    df.columns = df.columns.str.strip()

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    has_notes_col = any(c in df.columns for c in NOTES_COLUMN_VARIANTS)
    if missing or not has_notes_col:
        all_missing = list(missing)
        if not has_notes_col:
            all_missing.append("Notes/Remarks")
        raise InvalidExcelColumnsError(
            "Sorry, this is not as per the required columns for AI extraction. "
            f"Missing column(s): {', '.join(all_missing)}. "
            f"Required columns are: {', '.join(REQUIRED_COLUMNS + ('Notes/Remarks',))}."
        )

    llm = get_chat_llm(temperature=0, max_tokens=200)

    today = datetime.now()
    current_date_str = today.strftime("%Y-%m-%d")
    current_year = today.year
    current_week = today.isocalendar().week

    results = []

    for _, row in df.iterrows():
        note = str(
            row.get("Notes/ Remarks")
            or row.get("Notes/Remarks")
            or ""
        ).strip()

        formatted_prompt = PROMPT.format(
            note=note,
            current_date=current_date_str,
            current_year=current_year,
            current_week=current_week,
        )

        try:
            response = llm.invoke(formatted_prompt)
            content = getattr(response, "content", str(response))
            parsed = safe_json_parse(content)
        except Exception:
            parsed = {
                "forecasted_cx_start_date": None,
                "is_blocked": False,
                "blocked_reason": None,
            }

        parsed["forecasted_cx_start_date"] = parsed.get("forecasted_cx_start_date")
        parsed["is_blocked"] = bool(parsed.get("is_blocked", False))
        parsed["blocked_reason"] = parsed.get("blocked_reason")
        results.append(parsed)

    result_df = pd.DataFrame(results)
    final_df = pd.concat([df.reset_index(drop=True), result_df], axis=1)
    final_df = clean_nan(final_df)

    return final_df[
        [
            "SITE_ID",
            "PROJECT_ID",
            "REGION",
            "MARKET",
            "forecasted_cx_start_date",
            "is_blocked",
            "blocked_reason",
        ]
    ]
