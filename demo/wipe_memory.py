"""Reset the agent's mind. REACH world data is untouched.

    .venv/bin/python demo/wipe_memory.py            # wipe everything
    .venv/bin/python demo/wipe_memory.py carla_codes  # wipe one user + their threads

Run between rehearsals so beat 1 is genuinely cold.
"""
import pathlib
import sys

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from agent.memory import Memory  # noqa: E402

m = Memory()
ck = m.client["reach_agent_checkpoints"]

if len(sys.argv) > 1:
    user = sys.argv[1]
    for coll in ("observations", "beliefs", "runs"):
        n = m.db[coll].delete_many({"user": user}).deleted_count
        print(f"{coll}: -{n}")
    m.db.state.delete_many({"_id": f"cursor:{user}"})
    for coll in ck.list_collection_names():
        n = ck[coll].delete_many({"thread_id": {"$regex": user}}).deleted_count
        print(f"checkpoints/{coll}: -{n}")
else:
    m.client.drop_database("reach_agent")
    m.client.drop_database("reach_agent_checkpoints")
    print("dropped reach_agent + reach_agent_checkpoints")
print("cold.")
