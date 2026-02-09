'''
Docstring for test

import requests
import json

base = 'https://fuzzy-trina-prenako-sro-b1bc9170.koyeb.app'

# pridanie zamestnanca
r = requests.post(base + '/employee/add', json={'name':'Dániel'})
print(r.json())

# pridanie lokácie
r = requests.post(base + '/location/add', json={'name':'Bratislava'})
print(r.json())

# pridanie dochádzky

r = requests.post(base + '/attendance/add', json={
  'employee_id': 1,
  'location_id': 1,
  'start_time': '2025-09-14T08:00:00',
  'end_time': '2025-09-14T16:00:00'
})
print(r.json())

# vypísanie všetkej dochádzky
r = requests.get(base + '/attendance/list')
print(r.json())
'''
import psycopg2

# Hardcodované credentialy z Koyeb
DB_HOST = "ep-cold-cloud-a2abkwup.eu-central-1.pg.koyeb.app"
DB_USER = "koyeb-adm"
DB_PASSWORD = "npg_QgjvFc6Vk3JL"
DB_NAME = "koyebdb"

# Zostavenie connection stringu
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

try:
    # Pripojenie cez SSL (povinné pre Koyeb)
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cursor = conn.cursor()
    print("Successfully connected to the database!")

    # TEST: získanie aktuálneho času DB
    cursor.execute("SELECT NOW();")
    result = cursor.fetchone()
    print("Database current time:", result)

    cursor.close()
    conn.close()
    print("Connection test completed successfully!")

except Exception as e:
    print("Error connecting to the database:", e)
