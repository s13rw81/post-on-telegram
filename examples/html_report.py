# examples/html_report.py
"""Example: send an HTML-formatted report to a Telegram chat."""

from post_on_telegram import Poster, format_pre

poster = Poster()

report_text = "Symbol | Price | Change\n--- | --- | ---\nBTC | 50000 | +2.5%\nETH | 3000 | -1.2%"
report = format_pre(report_text)

if poster.send(report, parse_mode="HTML"):
    print("HTML report sent successfully.")
else:
    print(f"Failed to send: {poster.last_error}")
