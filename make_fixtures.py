"""Build the AfyaPlus triage fixtures.

fixtures/triage_messages.json  : 40 unique patient messages (load fixture)
fixtures/triage_labelled.json  : the same 40 messages with an urgency label

Labels are assigned per message by the author using a simple rule:
  emergency = possible life threat now (e.g. cardiac, stroke, anaphylaxis,
              meningitis signs, acute abdomen, haemoptysis)
  urgent    = needs clinic review within ~24h
  routine   = self-care advice, clinic if it worsens
They are NOT clinician-validated. Have a clinician review them before any
accuracy figure from this file is used outside the capstone.
"""
import json
import pathlib
from collections import Counter

pathlib.Path("fixtures").mkdir(exist_ok=True)

LABELLED = [
    ("Fever for two days, drinking fluids", "routine"),
    ("Persistent cough for a week", "routine"),
    ("Child with diarrhoea since morning", "urgent"),
    ("Mild headache after missing lunch", "routine"),
    ("Chest pain radiating to left arm", "emergency"),
    ("Twisted ankle, mild swelling", "routine"),
    ("Rash spreading on the forearm", "urgent"),
    ("Sore throat, no fever", "routine"),
    ("Shortness of breath climbing stairs", "urgent"),
    ("Stomach pain after eating", "routine"),
    ("Toothache for three days", "routine"),
    ("Low-grade fever with body aches", "routine"),
    ("Cut on hand, bleeding stopped", "routine"),
    ("Dizziness on standing up quickly", "routine"),
    ("Ear pain and mild hearing loss", "urgent"),
    ("Back pain after lifting a jerry can", "routine"),
    ("Blurred vision since this morning", "urgent"),
    ("Swollen ankle, cannot bear weight", "urgent"),
    ("Persistent vomiting since last night", "urgent"),
    ("Mild burn on the forearm", "routine"),
    ("High fever with stiff neck", "emergency"),
    ("Sudden weakness on one side", "emergency"),
    ("Difficulty breathing after a bee sting", "emergency"),
    ("Severe abdominal pain, rigid", "emergency"),
    ("Coughing up blood", "emergency"),
    ("Chest tightness at rest", "emergency"),
    ("Mild seasonal allergy symptoms", "routine"),
    ("Sprained wrist from a fall", "routine"),
    ("Sore muscles after exercise", "routine"),
    ("Common cold symptoms, no fever", "routine"),
    ("Insect bite with local swelling", "routine"),
    ("Minor scrape on the knee", "routine"),
    ("Heartburn after a heavy meal", "routine"),
    ("Feeling tired, no other symptoms", "routine"),
    ("Nosebleed that stopped on its own", "routine"),
    ("Sunburn on shoulders", "routine"),
    ("Mild anxiety before an exam", "routine"),
    ("Hiccups lasting one hour", "routine"),
    ("Bruise on the shin from a bump", "routine"),
    ("Runny nose and sneezing", "routine"),
]
assert len(LABELLED) == 40
assert len({m for m, _ in LABELLED}) == 40, "messages must be unique"

messages = [m for m, _ in LABELLED]
labelled = [{"message": m, "urgency": u} for m, u in LABELLED]

with open("fixtures/triage_messages.json", "w") as f:
    json.dump(messages, f, indent=2)
with open("fixtures/triage_labelled.json", "w") as f:
    json.dump(labelled, f, indent=2)

counts = Counter(u for _, u in LABELLED)
print("wrote fixtures/triage_messages.json (40) and "
      "fixtures/triage_labelled.json (40)")
print("label counts:", dict(counts))
