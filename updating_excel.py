# usage: python updating_excel.py -i Pipline.xlsx -o updated_data.xlsx -r 10 (rows)
import argparse
import json
import re
import requests
import pandas as pd
import time
import yaml
import os


def robust_extract_json(response_text):
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", response_text)
    if code_block_match:
        candidate = code_block_match.group(1)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    start = response_text.find("{")
    end = response_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = response_text[start:end+1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None
    return None

def update_row(row_dict, api_key):
    prompt = (
        "You are an expert in verifying pharmaceutical data, especially for the German market. "
        "Your task is to verify and update each field of the given row using the most current online information from reliable sources. "
        "Please check every column (e.g., Therapiegebiet, Indikation, Verabreichung, Firma, Wirkstoff, Markennamen, "
        "EMEA / FDA Registered, Registrierung CH erwartet im, etc.) using authoritative websites such as compendium.ch, Swissmedic, "
        "and other trusted sources. \n\n"
        "Hinweis: Die Excel-Daten sind in deutscher Sprache. Bitte nutzen Sie auch deutschsprachige Quellen, wo angebracht. \n\n"
        "IMPORTANT: If you use any online source to verify or update a field, include the URL (source link) in the 'Website' column "
        "and make sure these URLs actually exist and are not outdated. If multiple sources are used, separate them with a semicolon and two blank spaces for readability. "
        "If no source was used or no update was made, leave the field unchanged. \n\n"
        "Only update a field if you have confirmed new, reliable information. Otherwise, return the original value. "
        "Return the updated row as a JSON object with the same keys and no additional commentary or text. \n\n"
        "Row data:\n" 
        + json.dumps(row_dict, indent=2, default=str)
    )
    
    payload = {
        "model": "sonar-pro", 
        "web_search_options": {"search_context_size": "high"},
        "temperature": 0.0,
        "messages": [ {"role": "system",
                "content": (
                    "You are a highly knowledgeable and diligent expert in pharmaceutical data verification. "
                    "Your role is to verify each field of the given German data using up-to-date online sources. "
                    "Double-check every column, and only update fields when you are certain about the new data via your extensive research. "
                    "If you cannot verify a field, return the original value. Do not include any commentary in your reply.")}, {"role": "user", "content": prompt }
        ],
        "max_tokens": 8000
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
        response.raise_for_status()  # Raises an HTTPError if the status is 4xx or 5xx
    except requests.RequestException as e:
        print(f"Request error: {e}")
        return row_dict

    try:
        response_data = response.json()
    except json.JSONDecodeError as e:
        print(f"JSON decode error in response: {e}")
        return row_dict

    if "choices" not in response_data or not response_data["choices"]:
        print("No choices found in response.")
        return row_dict

    raw_reply = response_data["choices"][0]["message"]["content"]
    # print(f"Raw reply: {raw_reply}")  

    updated_data = robust_extract_json(raw_reply)
    if updated_data is None:
        print("Could not extract valid JSON; returning original row.")
        return row_dict

    return updated_data

def main():
    parser = argparse.ArgumentParser(
        description="Update pharmaceutical data using Perplexity API."
    )
    parser.add_argument("-i", "--input", required=True,
                        help="Input Excel file path (e.g., Pipeline.xlsx)")
    parser.add_argument("-o", "--output", required=True,
                        help="Output Excel file path (e.g., updated_data.xlsx)")
    parser.add_argument("-r", "--rows", type=int, default=10,
                        help="Number of rows to process from the top of the file")
    parser.add_argument("-s", "--sheet", default="Tabelle für LE2 2022",
                        help="Excel sheet name to process (default: 'Tabelle für LE2 2022')")
    args = parser.parse_args()

    try:
        with open("config.yaml", "r") as file:
            config = yaml.safe_load(file)
    except Exception as e:
        print(f"Error reading config.yaml: {e}")
        return

    try:
        PERPLEXITY_API_KEY = config["Perplexity"]
    except KeyError:
        print("Perplexity API key not found in config.yaml under the key 'Perplexity'.")
        return

    try:
        df = pd.read_excel(args.input, sheet_name=args.sheet)
    except Exception as e:
        print(f"Error reading the Excel file: {e}")
        return

    updated_rows = []
    num_rows = args.rows
    print(f"Processing {num_rows} row(s) from sheet '{args.sheet}' in file '{args.input}'...")

    for index, row in df.head(num_rows).iterrows():
        row_dict = row.to_dict()
        print(f"Processing row {index+1}/{num_rows}...")
        updated_data = update_row(row_dict, PERPLEXITY_API_KEY)
        updated_rows.append(updated_data)
        time.sleep(1)

    try:
        updated_df = pd.DataFrame(updated_rows)
        updated_df.to_excel(args.output, index=False)
        print(f"Updated data saved to {args.output}")
    except Exception as e:
        print(f"Error writing to Excel file: {e}")

if __name__ == "__main__":
    main()
