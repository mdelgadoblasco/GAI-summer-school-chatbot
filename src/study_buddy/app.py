from pathlib import Path
import streamlit as st
from study_buddy.chatbot import build_bot

st.set_page_config(page_title="Study Buddy Chatbot", page_icon="📚")

st.title("📚 Study Buddy Chatbot")
st.caption("A study-focused chatbot with memory, persona, and graceful refusal logic.")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "bot" not in st.session_state:
    st.session_state.bot = build_bot(
        config_path=Path("config/study_buddy.toml"),
        state_path=Path(".study_buddy_state.json"),
    )

with st.sidebar:
    st.header("About")
    st.write(
        "Study Buddy helps students understand concepts, plan revision, "
        "make flashcards, and prepare for exams. It refuses off-topic or "
        "homework-cheating requests politely."
    )

    if st.button("Reset conversation"):
        response = st.session_state.bot.chat("/reset")
        st.session_state.messages = []
        st.success(response)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Ask Study Buddy something...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response = st.session_state.bot.chat(prompt)
        st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})