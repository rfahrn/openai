# online.py

import asyncio
import base64
import time
from openai import OpenAI
from playwright.async_api import async_playwright
import yaml
with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

client = OpenAI(api_key=config["OPENAI_KEY_TEST"],)

# online.py

import asyncio
import base64
import time
from openai import OpenAI
from playwright.async_api import async_playwright


# --- Helpers ---
async def get_screenshot(page):
    return await page.screenshot()

async def handle_model_action(page, action):
    match action['type']:
        case 'click':
            print(f"[Click] ({action['x']}, {action['y']})")
            await page.mouse.click(action['x'], action['y'], button=action.get('button', 'left'))
        case 'scroll':
            print(f"[Scroll] by ({action['scroll_x']}, {action['scroll_y']})")
            await page.mouse.move(action['x'], action['y'])
            await page.evaluate(f"window.scrollBy({action['scroll_x']}, {action['scroll_y']})")
        case 'keypress':
            for key in action['keys']:
                print(f"[Keypress] {key}")
                await page.keyboard.press(key)
        case 'type':
            print(f"[Type] {action['text']}")
            await page.keyboard.type(action['text'])
        case 'wait':
            print("[Wait]")
            await asyncio.sleep(2)
        case _:
            print(f"[Unhandled Action] {action['type']}")

# --- Main Agent Logic ---
async def run_cua_browser_task():
    med_name = "Dafalgan 500mg"
    user_question = "Standarddosierung für Erwachsene"

    print(f"🔍 Starte Abfrage: {med_name} – {user_question}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://compendium.ch")
        await asyncio.sleep(2)

        # Step 1: Send initial user prompt (no screenshot yet!)
        response = client.responses.create(
            model="computer-use-preview",
            tools=[{
                "type": "computer_use_preview",
                "display_width": 1280,
                "display_height": 768,
                "environment": "browser"
            }],
            input=[
                {"role": "user", "content": f"Suche auf compendium.ch nach '{med_name}' und finde '{user_question}'"}
            ],
            reasoning={"generate_summary": "concise"},
            truncation="auto"
        )

        # Step 2: Main loop
        while True:
            calls = [o for o in response.output if o.type == "computer_call"]
            if not calls:
                print("✅ Keine weiteren Aktionen vom Modell. Prozess abgeschlossen.")
                break

            # Execute action
            action = calls[0].action
            call_id = calls[0].call_id
            await handle_model_action(page, action)
            await asyncio.sleep(1)

            # Screenshot after action
            screenshot = base64.b64encode(await get_screenshot(page)).decode("utf-8")

            # Send screenshot back
            response = client.responses.create(
                model="computer-use-preview",
                previous_response_id=response.id,
                tools=[{
                    "type": "computer_use_preview",
                    "display_width": 1280,
                    "display_height": 768,
                    "environment": "browser"
                }],
                input=[
                    {
                        "call_id": call_id,
                        "type": "computer_call_output",
                        "output": {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{screenshot}"
                        },
                        "current_url": page.url
                    }
                ],
                truncation="auto"
            )

        await browser.close()
        print("🌐 Browser geschlossen.")

# --- Entry Point ---
if __name__ == "__main__":
    asyncio.run(run_cua_browser_task())

