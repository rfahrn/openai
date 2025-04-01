#!/usr/bin/env python3
import argparse
import json
import re
import requests
import pandas as pd
import time
import yaml
import os
from typing import List, Dict, Optional

def robust_extract_json(response_text: str) -> Optional[dict]:
    """
    Enhanced JSON extraction with multiple fallback strategies and debug logging
    """
    # Remove chain-of-thought markers
    cleaned_text = "\n".join(
        line for line in response_text.splitlines() 
        if not line.strip().startswith(("<think>", "//", "#"))
    )

    # Strategy 1: Extract JSON code block
    code_block_match = re.search(r"```(?:json)?\s*({[\s\S]+?})\s*```", cleaned_text)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError as e:
            print(f"Code block JSON error: {e}")

    # Strategy 2: Try parsing entire cleaned text
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        pass

    # Strategy 3: Find deepest JSON structure
    json_candidates = re.findall(r'{(?:[^{}]|(?R))*}', cleaned_text)
    for candidate in reversed(json_candidates):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    print("JSON extraction failed. Raw response:")
    print(cleaned_text[:500] + "...")  # Show first 500 chars for debugging
    return None

def search_pipeline(api_key: str, num_rows: int, offset: int = 0) -> Optional[List[Dict]]:
    """
    Improved API call with structured JSON format enforcement
    """
    system_message = """You are a pharmaceutical data expert. Return ONLY JSON with this structure:
{
  "results": [
    {
      "Indikation": "...",
      "Wirkstoff": "...",
      "Brandname": "...",
      "Produkteigenschaften": "...",
      "Applikationsformen": "...",
      "Lagerungsbedingungen": "...",
      "spezielle Patientengruppen": "...", 
      "Informationen für Ärzte, Apotheken und Patienten": "...",
      "Wirkmechanismus": "...",
      "Kontraindikationen": "...",
      "Nebenwirkungen": "...",
      "Interaktionen": "...",
      "Schulungshinweise": "...",
      "zugelassene Konkurrenzprodukte": "...",
      "Website": "..."
    }
  ]
}"""

    user_message = f"""Search FDA decisions expected in 2025. Return exactly {num_rows} results starting from index {offset}.
Include only verified data from official sources (FDA, manufacturers, clinicaltrials.gov). 
Ensure complete fields and valid JSON format."""

    payload = {
        "model": "sonar-deep-research",
        "temperature": 0.0,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
        "web_search_options": {"search_context_size": "high"},
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            json=payload,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"API request failed: {str(e)}")
        return None

    try:
        response_data = response.json()
        content = response_data['choices'][0]['message']['content']
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Response parsing failed: {str(e)}")
        return None

    json_data = robust_extract_json(content)
    if not json_data or "results" not in json_data:
        print("Invalid JSON structure received")
        return None

    return json_data["results"]

def iterative_search_pipeline(api_key: str, max_rows: int) -> List[Dict]:
    """
    Batch retrieval with deduplication and rate limiting
    """
    results = []
    offset = 0
    batch_size = min(5, max_rows)  # Perplexity's recommended max batch size
    
    while len(results) < max_rows:
        print(f"Fetching {batch_size} rows (total {len(results)}/{max_rows})...")
        
        batch = search_pipeline(api_key, batch_size, offset)
        if not batch:
            print("No data received, stopping search")
            break
            
        # Deduplicate based on key fields
        unique_entries = []
        for entry in batch:
            key = (entry.get("Indikation"), entry.get("Wirkstoff"), entry.get("Brandname"))
            if not any((e["Indikation"], e["Wirkstoff"], e["Brandname"]) == key for e in results):
                unique_entries.append(entry)
                
        results.extend(unique_entries)
        offset += len(batch)
        
        if len(batch) < batch_size:
            print("Reached end of available data")
            break
            
        time.sleep(1.2)  # Respect rate limits (5 RPM = 1 every 12s)
        
    return results[:max_rows]

def main():
    parser = argparse.ArgumentParser(
        description="FDA Pipeline Data Fetcher",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("-o", "--output", required=True,
                        help="Output Excel file path")
    parser.add_argument("-r", "--rows", type=int, default=1,
                        help="Number of rows to retrieve")
    parser.add_argument("-s", "--sheet", default="FDA Pipeline",
                        help="Excel sheet name")
    args = parser.parse_args()

    # Load API key
    try:
        with open("config.yaml") as f:
            config = yaml.safe_load(f)
            api_key = config["Perplexity"]
    except Exception as e:
        print(f"Config error: {str(e)}")
        return

    print(f"Starting FDA pipeline search for {args.rows} rows...")
    data = iterative_search_pipeline(api_key, args.rows)
    
    if not data:
        print("No data retrieved")
        return
        
    try:
        df = pd.DataFrame(data)
        df.to_excel(args.output, sheet_name=args.sheet, index=False)
        print(f"Successfully saved {len(data)} rows to {args.output}")
    except Exception as e:
        print(f"Excel export failed: {str(e)}")

if __name__ == "__main__":
    main()