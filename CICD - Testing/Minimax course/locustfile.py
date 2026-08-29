"""
Locustfile — realistic user simulation.

Locust is Pythonic. Define a User class and its behavior, then Locust
spawns thousands of them and reports stats.
"""
from __future__ import annotations

import random
import time

from locust import HttpUser, between, events, task


class ChatUser(HttpUser):
    """Simulates a real user chatting with the AI."""

    # wait_time: between 1 and 3 seconds between requests (human-like).
    wait_time = between(1, 3)

    def on_start(self):
        """Called once per user when they start. Log in, get a token."""
        # In a real app, call your auth endpoint.
        # self.client.post("/auth/login", json={...})
        self.token = "fake-token"  # replace with real auth

    @task(3)  # weight: 3x more likely than other tasks
    def send_chat_message(self):
        """User sends a chat message."""
        messages = [
            "Hello!",
            "What is FastAPI?",
            "Explain Docker.",
            "Help me write a Python function.",
            "What's the weather like?",
            "Summarize the news today.",
        ]
        self.client.post(
            "/api/chat",
            json={"message": random.choice(messages)},
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/chat",  # groups stats in report
        )

    @task(1)  # less frequent
    def get_history(self):
        """User opens the chat history sidebar."""
        self.client.get(
            "/api/history",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/history",
        )

    @task(1)
    def health_check(self):
        """The UI does periodic health checks."""
        self.client.get("/health", name="/health")


# Optional: thresholds that fail the CI job if breached.
# Add this to your locust invocation:
#   locust -f locustfile.py ... --host URL --headless ...
@events.quitting.add_listener
def _(environment, **kwargs):
    """Run at end. If any of these stats are bad, set process exit code."""
    stats = environment.stats
    if stats.total.fail_ratio > 0.05:  # > 5% errors
        environment.process_exit_code = 1
    if stats.total.get_response_time_percentile(0.95) > 3000:  # P95 > 3s
        environment.process_exit_code = 1
