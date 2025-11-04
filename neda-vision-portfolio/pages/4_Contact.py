import streamlit as st

st.set_page_config(page_title="Contact · Neda Vision", page_icon="✉️", layout="wide")
st.title("Contact")

st.markdown("If you'd like to get in touch, use the form below or email me.")

with st.form("contact_form"):
    name = st.text_input("Name")
    email = st.text_input("Email")
    message = st.text_area("Message", height=160)
    submitted = st.form_submit_button("Send")
    if submitted:
        if name and email and message:
            st.success("Thanks! This demo form doesn't send emails, but you can copy the message below:")
            st.code(f"From: {name} <{email}>\n\n{message}")
        else:
            st.error("Please complete all fields.")

st.markdown("**Email:** [neda@example.com](mailto:neda@example.com)")
