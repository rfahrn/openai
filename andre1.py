#!/usr/bin/env python3
import argparse
import json
import re
import requests
import pandas as pd
import yaml
import os
from pydantic import BaseModel, RootModel, ValidationError
from typing import List

# 1) Define a model for each row
class PipelineEntry(BaseModel):
    Indikation: str
    Wirkstoff: str
    Brandname: str
    Produkteigenschaften: str
    Applikationsformen: str
    Lagerungsbedingungen: str
    spezielle_Patientengruppen: str
    Informationen_fuer_Aerzte_Apotheken_und_Patienten: str
    Wirkmechanismus: str
    Kontraindikationen: str
    Nebenwirkungen: str
    Interaktionen: str
    Schulungshinweise: str
    zugelassene_Konkurrenzprodukte: str
    Website: str

# 2) Define a root model that wraps a list of `PipelineEntry`
class PipelineEntries(RootModel[List[PipelineEntry]]):
    """Represents a list of PipelineEntry objects at the root level."""

def robust_extract_json(response_text: str):
    # Attempt multiple ways to extract valid JSON
    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError:
        pass
    
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", response_text)
    if code_block_match:
        candidate = code_block_match.group(1)
        try:
            return json.loads(candidate.strip())
        except json.JSONDecodeError:
            pass
    
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = response_text[start:end+1]
        try:
            return json.loads(candidate.strip())
        except json.JSONDecodeError:
            pass
    
    return None

def search_pipeline(api_key: str, max_rows: int):
    system_message = (
        "You are a highly knowledgeable expert in pharmaceutical pipeline data and FDA approvals. "
        "Return ONLY a valid JSON array of objects, strictly matching the fields in the schema. "
        "No chain-of-thought, no code fences, no extra text. "
        "If any field is unknown, leave it blank."
    )

    user_message = (
        f"List all molecules with an FDA decision expected in 2025. "
        f"Sort by Indikation and expected approval date. "
        f"Return only the first {max_rows} rows as a JSON array. "
        "No text or commentary outside the JSON."
    )

    # Let’s get the JSON schema from PipelineEntries (RootModel) 
    # to nudge the LLM to return valid data
    schema_for_list = PipelineEntries.model_json_schema()

    payload = {
        "model": "sonar-deep-research",
        "web_search_options": {"search_context_size": "low"},
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"schema": schema_for_list},
        },
        "max_tokens": 8000,
        "temperature": 0.0,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Request error: {e}")
        return None

    try:
        response_data = response.json()
    except json.JSONDecodeError as e:
        print(f"JSON decode error in response: {e}")
        return None

    if "choices" not in response_data or not response_data["choices"]:
        print("No choices found in response.")
        return None

    raw_reply = response_data["choices"][0]["message"]["content"]
    print("Raw reply from LLM:\n", raw_reply)  # Debugging

    # Attempt to parse the JSON
    raw_json = robust_extract_json(raw_reply)
    if raw_json is None:
        print("Could not extract valid JSON; check the API response.")
        return None

    # Parse with Pydantic’s RootModel
    try:
        pipeline_entries = PipelineEntries.model_validate(raw_json)
        return pipeline_entries
    except ValidationError as ve:
        print("JSON did not match the Pydantic schema:")
        print(ve)
        return None

def main():
    parser = argparse.ArgumentParser(
        description="Search the internet for FDA pipeline data (for 2025 approvals) using Perplexity API and output an Excel table."
    )
    parser.add_argument("-o", "--output", required=True,
                        help="Path to the output Excel file (e.g., updated_pipeline.xlsx)")
    parser.add_argument("-r", "--rows", type=int, default=2,
                        help="Maximum number of rows to return (default: 2)")
    parser.add_argument("-s", "--sheet", default="Pipeline Data",
                        help="Name of the Excel sheet (default: 'Pipeline Data')")
    args = parser.parse_args()

    # Load config for Perplexity key
    try:
        with open("config.yaml", "r") as file:
            config = yaml.safe_load(file)
    except Exception as e:
        print(f"Error reading config.yaml: {e}")
        return

    try:
        PERPLEXITY_API_KEY = config["Perplexity"]
    except KeyError:
        print("Perplexity API key not found in config.yaml under 'Perplexity'.")
        return

    print(f"Searching for FDA pipeline data (max {args.rows} rows)...")
    pipeline_entries = search_pipeline(PERPLEXITY_API_KEY, args.rows)
    if pipeline_entries is None:
        print("No data returned or data invalid.")
        return

    # pipeline_entries is a RootModel[List[PipelineEntry]]
    # Access the inner list with .root
    entries_list = pipeline_entries.root

    # Convert each entry to a dict and build a DataFrame
    df = pd.DataFrame([entry.model_dump() for entry in entries_list])

    # Write to Excel
    try:
        df.to_excel(args.output, sheet_name=args.sheet, index=False)
        print(f"Pipeline data saved to {args.output} in sheet '{args.sheet}'.")
    except Exception as e:
        print(f"Error writing to Excel file: {e}")

if __name__ == "__main__":
    main()
