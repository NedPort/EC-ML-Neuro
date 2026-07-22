from src.api import CISSApi

api = CISSApi()

case = api.get_case_details(6028)

print(case.keys())