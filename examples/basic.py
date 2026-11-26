# examples/basic.py
"""Basic example: send a text message to a Telegram chat."""

from post_on_telegram import Poster

poster = Poster()
if poster.send("Hello from Post on Telegram!"):
    print("Message sent successfully.")
else:
    print(f"Failed to send: {poster.last_error}")
