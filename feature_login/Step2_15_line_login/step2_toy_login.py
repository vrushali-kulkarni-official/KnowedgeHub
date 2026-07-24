import streamlit as st

# ⚠️ A toy "user database" — JUST a dict in memory for now
# DO NOT do this for real. I'm doing it ON PURPOSE so we can watch it fail.
USERS = {
    "alice": "wonderland",
    "bob": "builder",
}


def login_screen():
    """The form the user sees when NOT logged in."""
    st.title("🔐 Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Log in"):
        if USERS.get(username) == password:
            # 🎉 "Authenticated" — flip the flag
            st.session_state.logged_in = True
            st.session_state.username = username
            st.rerun()  # re-run the script so the if/else at the bottom routes us to main_app()
        else:
            st.error("Wrong username or password")


def main_app():
    """The protected part of the app — only reachable if logged_in is True."""
    st.title(f"Welcome {st.session_state.username} 👋")
    st.write("You are now inside the protected area.")
    st.write("This is where your chatbot will live in the real version.")
    if st.button("Log out"):
        st.session_state.logged_in = False
        st.rerun()


# Initialize the flag once per session
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# Router: one of two screens, based on the flag
if st.session_state.logged_in:
    main_app()
else:
    login_screen()
