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
