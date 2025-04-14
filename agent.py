from langchain_openai import ChatOpenAI
from browser_use import Agent
import asyncio
from dotenv import load_dotenv
import yaml
load_dotenv()
quesiton = "Was ist die Wirkung von Dafalgan?"
async def main():
    agent = Agent(
        task= "Gehe auf https://compendium.ch/, suche nach dem passenden Medikament (oberste in der Suche).und beantworte folgende Frage: "
        f"{quesiton} mit Infos von der Compendium-Seite. Fasse klar und medizinisch präzise zusammen.Wenn du keine Antwort findest, sage einfach 'Ich kann dir nicht helfen'. Gib auch den letzten Link an, den du besucht hast.",
        llm=ChatOpenAI(model="gpt-4o"),
    )
    result = await agent.run()
    print(result)

asyncio.run(main())