import streamlit as st
import asyncio
import nest_asyncio
import sys
from langchain_openai import ChatOpenAI
from browser_use import Agent, Browser, BrowserConfig, Browser
from dotenv import load_dotenv
import concurrent.futures

load_dotenv()


st.set_page_config(page_title="💊 Compendium Bot", layout="centered")
st.title("Welcome to the Compendium Bot!")
question = st.text_input("Was möchtest du wissen?", placeholder="z. B. Wirkung von Dafalgan, Dosierung etc.")

async def run_agent(question):
    browser = Browser()
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
    await browser.close()
    return result

def run_async_agent(q):
    return asyncio.run(run_agent(q))

if st.button("Frage stellen"):
    if question.strip():
        with st.spinner("Die KI sucht im Compendium... 🧠"):
            try:
                # Run the async function in a separate thread.
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_async_agent, question)
                    result = future.result()
                    
                st.success("✅ Antwort vom Compendium Agent:")
                st.markdown(result.strip())
            except Exception as e:
                st.error(f"Fehler: {e}")
    else:
        st.warning("Bitte eine Frage eingeben.")
