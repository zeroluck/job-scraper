"""Read-only manual drain preflight; no claims, resets or configuration writes."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import supabase_utils
from linkedin_discovery import adaptive_options, require_detail_only_cycle
from scrape_configuration import load_scrape_configuration


def main():
    if (
        os.getenv("LINKEDIN_DISCOVERY_MODE") != "adaptive_queue"
        or os.getenv("SCRAPE_CONFIG_SOURCE") != "db"
        or os.getenv("SCRAPE_ARCHETYPE", "") != ""
        or config.SCRAPING_SOURCES != ["linkedin"]
        or not os.getenv("LINKEDIN_DETAIL_ONLY_CYCLE_ID")
        or not os.getenv("LINKEDIN_DETAIL_ONLY_SEQUENCE")
    ):
        raise SystemExit("Manual drain environment preflight failed")
    configuration = load_scrape_configuration(db=supabase_utils.supabase)
    cycle = supabase_utils.get_resumable_linkedin_discovery_cycle(partial=False)
    require_detail_only_cycle(cycle, adaptive_options(configuration.settings), partial=False)
    print("Read-only identity/pending preflight passed; sealed cycle and 300-task limit verified")


if __name__ == "__main__":
    main()
