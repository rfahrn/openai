#!/usr/bin/env python3
import argparse
import json
import re
import requests
import pandas as pd
import time
import yaml
import os

def robust_extract_json(response_text):
    """
    Attempts to extract a JSON array from the response text.
    First, it removes any lines starting with '<think>' to strip out chain-of-thought markers.
    It then tries to find a JSON code block; if that fails, it looks for a substring that starts with '[' and ends with ']'.
    """
    # Remove any lines starting with <think>
    cleaned_text = "\n".join(
        line for line in response_text.splitlines() if not line.strip().startswith("<think>")
    )
    
    # Try to extract JSON from a code block
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned_text)
    if code_block_match:
        candidate = code_block_match.group(1)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Fallback: look for a JSON array in the cleaned text
    start = cleaned_text.find("[")
    end = cleaned_text.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned_text[start:end+1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return None

def search_pipeline(api_key, num_rows, offset=0):
    """
    Call the API to retrieve a batch of results.
    The offset lets the LLM know that previous rows have already been provided.
    Streaming is enabled so that results are printed as they arrive.
    """
    system_message = (
        "You are a highly knowledgeable expert in pharmaceutical pipeline data and FDA approvals. "
        "Your task is to search the internet using up-to-date, reliable sources (such as official FDA press releases, "
        "manufacturer announcements, and reputable medical journals) for the latest pipeline data on all molecules for which "
        "a US FDA decision is expected in 2025 (including those under FDA Priority Review). "
        "Compile the data into an Excel-style table sorted by indication, active ingredient and expected approval date and add a column called 'information' "
        "to include any interesting findings along with the date in a bracket. "
        "The table must include the following columns exactly as specified: "
        "Indikation, Wirkstoff, Brandname, Produkteigenschaften, Applikationsformen (e.g., Pen, Fertigspritze, Filmtablette, Kapsel), "
        "Lagerungsbedingungen (especially if refrigeration is needed), spezielle Patientengruppen, "
        "Informationen für Ärzte, Apotheken und Patienten, Wirkmechanismus, Kontraindikationen, Nebenwirkungen, "
        "Interaktionen, Schulungshinweise, zugelassene Konkurrenzprodukte, and Website "
        "(with URLs of the sources used, separated by semicolons). "
        "If any field cannot be verified, leave it blank. "
        "Do not include any chain-of-thought or internal reasoning. Return only a JSON array of objects with exactly the specified keys and no additional commentary. "
        "For example, return something like this:\n\n"
        "```json\n"
        "{\n"
        "  \"Indikation\": \"Cystische Fibrose (CF)\",\n"
        "  \"Wirkstoff\": \"Vanzacaftor/Tezacaftor/Deutivacaftor\",\n"
        "  \"Brandname\": \"Alyftrek\",\n"
        "  \"Produkteigenschaften\": \"Dreifach-Kombinationstherapie (CFTR-Modulatoren) für Patienten ab 6 Jahren\",\n"
        "  \"Applikationsformen\": \"Orale Tabletten (einmal tägliche Einnahme)\",\n"
        "  \"Lagerungsbedingungen\": \"Raumtemperatur\",\n"
        "  \"spezielle Patientengruppen\": \"Zugelassen ab 6 Jahren; in Schwangerschaft nur nach strenger Abwägung\",\n"
        "  \"information\": \"FDA-Entscheidung am 15. Januar 2025 (FDA Priority Review) (2023-10-01)\",\n"
        "  \"Informationen für Ärzte, Apotheken und Patienten\": \"Vor Therapiebeginn sollte ein Gentest die CFTR-Mutation bestätigen; Leberwerte sollten überwacht werden.\",\n"
        "  \"Wirkmechanismus\": \"Verbessert Menge und Funktion des CFTR-Proteins – Vanzacaftor und Tezacaftor fördern den Transport defekter CFTR-Proteine, während Deutivacaftor die Öffnungszeit des Kanals verlängert.\",\n"
        "  \"Kontraindikationen\": \"Schwere Leberinsuffizienz\",\n"
        "  \"Nebenwirkungen\": \"Kopfschmerzen, Atemwegsinfekte, Diarrhoe, erhöhte Leberenzymwerte\",\n"
        "  \"Interaktionen\": \"Starke CYP3A-Induktoren (z.B. Rifampicin) können die Wirksamkeit vermindern; Grapefruitsaft meiden.\",\n"
        "  \"Schulungshinweise\": \"Regelmäßige Kontrolle und Patientenschulung notwendig.\",\n"
        "  \"zugelassene Konkurrenzprodukte\": \"Trikafta\",\n"
        "  \"Website\": \"https://www.fda.gov; https://www.drugs.com\"\n"
        "}\n"
        "```"
    )
    # Adjust the user message if we're asking for additional rows
    if offset > 0:
        user_message = (
            f"Please search the internet and compile a complete list of additional molecules for which a US FDA decision is expected in 2025 "
            f"(including FDA Priority Review). Skip the first {offset} rows and return only the next {num_rows} rows. "
            "Ensure that all required columns (Indikation, Wirkstoff, Brandname, Produkteigenschaften, Applikationsformen, Lagerungsbedingungen, "
            "spezielle Patientengruppen, Informationen für Ärzte, Apotheken und Patienten, Wirkmechanismus, Kontraindikationen, Nebenwirkungen, "
            "Interaktionen, Schulungshinweise, zugelassene Konkurrenzprodukte, Website) are present. "
            "Return only the JSON array with no extra text or reasoning, and do not include any chain-of-thought markers."
        )
    else:
        user_message = (
            f"Please search the internet and compile a complete list of all molecules for which a US FDA decision is expected in 2025 "
            f"(including FDA Priority Review). Sort the results by indication and expected approval date, and return only the first {num_rows} rows. "
            "Ensure that all required columns (Indikation, Wirkstoff, Brandname, Produkteigenschaften, Applikationsformen, Lagerungsbedingungen, "
            "spezielle Patientengruppen, Informationen für Ärzte, Apotheken und Patienten, Wirkmechanismus, Kontraindikationen, Nebenwirkungen, "
            "Interaktionen, Schulungshinweise, zugelassene Konkurrenzprodukte, Website) are present. "
            "Return only the JSON array with no extra text or reasoning, and do not include any chain-of-thought markers."
        )

    payload = {
        "model": "sonar-deep-research",  # using the sonar-pro model
        "web_search_options": {"search_context_size": "low"},
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 3000,
        "temperature": 0.0,
        "stream": True  # enable streaming
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            json=payload,
            headers=headers,
            stream=True  # using streaming mode
        )
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Request error: {e}")
        return None

    # Stream the response tokens and build the complete reply
    raw_reply = ""
    try:
        for line in response.iter_lines(decode_unicode=True):
            if line:
                raw_reply += line
                print(line, end="")  # Optionally print each chunk as it arrives
        print()  
    except Exception as e:
        print(f"Error during streaming: {e}")
        return None

    result = robust_extract_json(raw_reply)
    if result is None:
        print("Could not extract valid JSON; check the API response.")
    return result

def iterative_search_pipeline(api_key, max_rows):
    """
    Repeatedly calls the search_pipeline function until the number of unique rows reaches max_rows.
    The offset is increased each iteration to ask for additional rows.
    """
    aggregated_results = []
    offset = 0
    while len(aggregated_results) < max_rows:
        remaining_rows = max_rows - len(aggregated_results)
        print(f"\nRequesting {remaining_rows} rows starting from offset {offset}...")
        result = search_pipeline(api_key, remaining_rows, offset)
        if result is None:
            print("No data returned in this iteration. Exiting loop.")
            break
        if not isinstance(result, list):
            print("API response is not a list. Exiting.")
            break

        for entry in result:
            key = (entry.get("Indikation"), entry.get("Wirkstoff"), entry.get("Brandname"))
            if not any((r.get("Indikation"), r.get("Wirkstoff"), r.get("Brandname")) == key for r in aggregated_results):
                aggregated_results.append(entry)

        offset += len(result)
        print(f"Total aggregated rows: {len(aggregated_results)}")
        if len(result) < remaining_rows:
            print("Received fewer rows than requested; ending search.")
            break
        time.sleep(1)

    return aggregated_results[:max_rows]

def main():
    parser = argparse.ArgumentParser(
        description="Search the internet for FDA pipeline data (for decisions expected in 2025) using Perplexity API and output an Excel table."
    )
    parser.add_argument("-o", "--output", required=True,
                        help="Path to the output Excel file (e.g., updated_pipeline.xlsx)")
    parser.add_argument("-r", "--rows", type=int, default=1,
                        help="Maximum number of rows to return (default: 10)")
    parser.add_argument("-s", "--sheet", default="Pipeline Data",
                        help="Name of the Excel sheet (default: 'Pipeline Data')")
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

    print(f"Searching for FDA pipeline data (max {args.rows} rows)...")
    pipeline_data = iterative_search_pipeline(PERPLEXITY_API_KEY, args.rows)
    if not pipeline_data:
        print("No data returned from the search.")
        return

    try:
        df = pd.DataFrame(pipeline_data)
    except Exception as e:
        print(f"Error converting JSON to DataFrame: {e}")
        return

    try:
        df.to_excel(args.output, sheet_name=args.sheet, index=False)
        print(f"Pipeline data saved to {args.output} in sheet '{args.sheet}'.")
    except Exception as e:
        print(f"Error writing to Excel file: {e}")

if __name__ == "__main__":
    main()
