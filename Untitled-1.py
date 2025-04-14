from flask import Flask, request, jsonify
import asyncio
from langchain_openai import ChatOpenAI
from browser_use import Agent, Browser, BrowserConfig
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

# Configure the real Chrome browser on Windows.
browser = Browser(
    config=BrowserConfig(
        chrome_instance_path='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    )
)

# Define an async function that runs your agent.
async def run_agent(question):
    agent = Agent(
        task=(
            "Gehe auf https://compendium.ch/, suche nach dem passenden Medikament (oberste in der Suche) "
            f"und beantworte folgende Frage: {question} mit Infos von der Compendium-Seite. "
            "Fasse klar und medizinisch präzise zusammen. "
            "Wenn du keine Antwort findest, sage einfach 'Ich kann dir nicht helfen'. "
            "Gib auch den letzten Link an, den du besucht hast."
        ),
        llm=ChatOpenAI(model="gpt-4o"),
        browser=browser
    )
    result = await agent.run()
    return result

@app.route("/ask", methods=["POST"])
def ask_agent():
    data = request.get_json()
    question = data.get("question")
    if not question:
        return jsonify({"error": "No question provided."}), 400
    try:
        result = asyncio.run(run_agent(question))
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Run on port 5000 – adjust as needed.
    app.run(debug=True, port=5000)
