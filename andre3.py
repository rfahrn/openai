#!/usr/bin/env python3
import argparse
import json
import re
import logging
import yaml
import openai
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

JSON_BLOCK_REGEX = re.compile(r"```(?:json)?\s*([\s\S]+?)\s*```", re.MULTILINE)

def robust_extract_json(response_text):
    code_block_match = JSON_BLOCK_REGEX.search(response_text)
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

def search_pipeline(max_rows):
    """
    Uses the OpenAI API to search for FDA pipeline data and returns a JSON array.
    """
    system_message = (
        "You are a highly knowledgeable expert in pharmaceutical pipeline data and FDA approvals. "
        "Your task is to search the internet using up-to-date, reliable sources (such as official FDA press releases, "
        "manufacturer announcements, and reputable medical journals) for the latest pipeline data on all molecules for which "
        "a US FDA decision is expected in 2025 (including those under FDA Priority Review). "
        "Compile the data into an Excel-style table sorted by indication, active ingredient and expected approval date and add a column called 'information' where to add any interesting findings and add the date in a bracket. "
        "The table must include the following columns exactly as specified: "
        "Indikation, Wirkstoff, Brandname, Produkteigenschaften, Applikationsformen (e.g., Pen, Fertigspritze, Filmtablette, Kapsel), "
        "Lagerungsbedingungen (especially if refrigeration is needed), spezielle Patientengruppen, Informationen für Ärzte, Apotheken und Patienten, "
        "Wirkmechanismus, Kontraindikationen, Nebenwirkungen, Interaktionen, Schulungshinweise, zugelassene Konkurrenzprodukte, and Website "
        "(with URLs of the sources used, separated by semicolons). "
        "If any field cannot be verified, leave it blank. "
        "Do not include any chain-of-thought or internal reasoning. Return only a JSON array of objects with exactly the specified keys and no additional commentary. "
        "For example, an entry in the JSON array should look like this:\n\n"
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
    user_message = (
        f"Please search the internet and compile a complete list of all molecules for which a US FDA decision is expected in 2025 "
        f"(including FDA Priority Review). Sort the results by indication and expected approval date, and return only the first {max_rows} rows. "
        "Ensure that all required columns (Indikation, Wirkstoff, Brandname, Produkteigenschaften, Applikationsformen, Lagerungsbedingungen, "
        "spezielle Patientengruppen, Informationen für Ärzte, Apotheken und Patienten, Wirkmechanismus, Kontraindikationen, Nebenwirkungen, "
        "Interaktionen, Schulungshinweise, zugelassene Konkurrenzprodukte, Website) are present. "
        "Return only the JSON array with no extra text or reasoning."
    )

    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.0,
            max_tokens=1500,
        )
    except Exception as e:
        logging.error(f"OpenAI API error: {e}")
        return None

    raw_reply = response.choices[0].message.content
    logging.info("Received API reply; extracting JSON...")
    result = robust_extract_json(raw_reply)
    
    if result is None:
        logging.error("Could not extract valid JSON; please verify the API response format.")
    return result

def main():
    parser = argparse.ArgumentParser(
        description="Search for FDA pipeline data (decisions expected in 2025) using the OpenAI API and output an Excel table."
    )
    parser.add_argument("-o", "--output", required=True,
                        help="Path to the output Excel file (e.g., updated_pipeline.xlsx)")
    parser.add_argument("-r", "--rows", type=int, default=2,
                        help="Maximum number of rows to return (default: 2)")
    parser.add_argument("-s", "--sheet", default="Pipeline Data",
                        help="Name of the Excel sheet (default: 'Pipeline Data')")
    args = parser.parse_args()

    try:
        with open("config.yaml", "r") as file:
            config = yaml.safe_load(file)
    except Exception as e:
        logging.error(f"Error reading config.yaml: {e}")
        return

    try:
        openai.api_key = config["OPENAI"]
    except KeyError:
        logging.error("OpenAI API key not found in config.yaml under the key 'OpenAI'.")
        return

    logging.info(f"Searching for FDA pipeline data (max {args.rows} rows)...")
    pipeline_data = search_pipeline(args.rows)
    if pipeline_data is None:
        logging.error("No data returned from the search.")
        return

    try:
        df = pd.DataFrame(pipeline_data)
    except Exception as e:
        logging.error(f"Error converting JSON to DataFrame: {e}")
        return

    try:
        df.to_excel(args.output, sheet_name=args.sheet, index=False)
        logging.info(f"Pipeline data saved to {args.output} (sheet: '{args.sheet}').")
    except Exception as e:
        logging.error(f"Error writing Excel file: {e}")

if __name__ == "__main__":
    main()
