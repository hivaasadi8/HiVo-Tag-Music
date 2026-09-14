import json
from pathlib import Path


class Store:
    """ذخیره‌سازی ساده روی JSON - قابل مهاجرت به SQLite/Postgres"""

    def __init__(self, path="state.json"):
        self.path = Path(path)
        if not self.path.exists():
            self.path.write_text(json.dumps({"users": {}, "stats": {}, "sessions": {}}))
        self.data = json.loads(self.path.read_text())

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    # --- کاربران ---
    def add_user(self, user_id, name=""):
        uid = str(user_id)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {"name": name, "files": 0, "joined": None}
            self.save()
            return True
        return False

    def inc_files(self, user_id):
        uid = str(user_id)
        self.data["users"].setdefault(uid, {"files": 0})
        self.data["users"][uid]["files"] = self.data["users"][uid].get("files", 0) + 1
        self.data["stats"]["total_files"] = self.data["stats"].get("total_files", 0) + 1
        self.save()

    def get_stats(self):
        return {
            "users": len(self.data["users"]),
            "files": self.data["stats"].get("total_files", 0)
        }

    # --- سشن‌های ادیت ---
    def set_session(self, user_id, session):
        self.data["sessions"][str(user_id)] = session
        self.save()

    def get_session(self, user_id):
        return self.data["sessions"].get(str(user_id))

    def clear_session(self, user_id):
        self.data["sessions"].pop(str(user_id), None)
        self.save()
