from src.downloader import CISSDownloader


def main():

    downloader = CISSDownloader()

    downloader.download_case(6028)

    input("\nPress Enter to close...")

    downloader.close()


if __name__ == "__main__":
    main()