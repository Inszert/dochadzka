import requests

BASE_URL = "https://fuzzy-trina-prenako-sro-b1bc9170.koyeb.app"

def safe_post(endpoint, data):
    url = f"{BASE_URL}{endpoint}"
    try:
        r = requests.post(url, json=data)
        print(f"POST {endpoint} -> Status: {r.status_code}")
        print("Response text:", r.text)
        try:
            return r.json()
        except Exception:
            print("Response is not valid JSON.")
            return None
    except Exception as e:
        print(f"Request failed: {e}")
        return None

def safe_get(endpoint):
    url = f"{BASE_URL}{endpoint}"
    try:
        r = requests.get(url)
        print(f"GET {endpoint} -> Status: {r.status_code}")
        print("Response text:", r.text)
        try:
            return r.json()
        except Exception:
            print("Response is not valid JSON.")
            return None
    except Exception as e:
        print(f"Request failed: {e}")
        return None

# 1️⃣ Pridanie zamestnanca
employee_data = {"name": "Daniel", "position": "Worker"}
emp_resp = safe_post("/employee/add", employee_data)
print("Add employee response:", emp_resp)

# 2️⃣ Pridanie miesta
location_data = {"name": "Bratislava"}
loc_resp = safe_post("/location/add", location_data)
print("Add location response:", loc_resp)

# 3️⃣ Pridanie dochádzky
attendance_data = {
    "employee_id": 1,
    "location_id": 1,
    "date": "2025-09-14",
    "check_in": "08:00",
    "check_out": "12:00"
}
att_resp = safe_post("/attendance/add", attendance_data)
print("Add attendance response:", att_resp)

# 4️⃣ Výpis všetkej dochádzky
all_att = safe_get("/attendance/list")
print("All attendance:", all_att)
