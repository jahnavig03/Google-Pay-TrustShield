"""`adk web adk_apps` entry point (local debugging).

Send a PaymentRiskRequest as JSON, or plain text to run the ₹85,000 demo payment with that text
as message_context ("demo1" runs the fixture unchanged).
"""

from trustshield_agents.orchestrator import build_workflow

root_agent = build_workflow()
