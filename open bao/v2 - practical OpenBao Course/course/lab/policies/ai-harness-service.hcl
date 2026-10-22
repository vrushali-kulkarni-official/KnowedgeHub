# Meridian AI - the FastAPI/LangChain AI harness service
#
# Needs exactly one secret: the Gemini API key.
# Cannot read DB or Redis credentials.
# Cannot list (so it cannot discover what else exists).
# Cannot write (so it cannot corrupt a secret).

path "ai/platform/data/llm/gemini" {
  capabilities = ["read"]
}

path "ai/platform/metadata/llm/gemini" {
  capabilities = ["read"]
}
