import streamlit as st
import requests

st.set_page_config(page_title="💊 Compendium Bot", layout="centered")
st.title("Welcome to the Compendium Bot!")

question = st.text_input("Was möchtest du wissen?", placeholder="z. B. Wirkung von Dafalgan, Dosierung etc.")

if st.button("Frage stellen"):
    if question.strip():
        with st.spinner("Die KI sucht im Compendium... 🧠"):
            try:
                response = requests.post("http://localhost:5000/ask", json={"question": question})
                response.raise_for_status()
                data = response.json()
                result = data.get("result", "")
                st.success("✅ Antwort vom Compendium Agent:")
                st.markdown(result.strip())
            except Exception as e:
                st.error(f"Fehler: {e}")
    else:
        st.warning("Bitte eine Frage eingeben.")
