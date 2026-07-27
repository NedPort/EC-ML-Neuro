from src.api.client import CISSApi
from src.pipeline.case_processor import CaseProcessor


def main():
    api = CISSApi(headless=False)

    try:
        processor = CaseProcessor(api)
        processor.process_case(6028)

    finally:
        api.close()


if __name__ == "__main__":
    main()