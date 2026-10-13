import json
import sys
from pathlib import Path

case_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(case_dir / "cli_skills" / "skills" / "contact-broadcaster"))
from skill import send_broadcast

result = send_broadcast(
    "Home survey in progress",
    str(case_dir / "sandbox" / "contacts.txt"),
)
print(json.dumps(result))
