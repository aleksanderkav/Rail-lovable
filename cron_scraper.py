#!/usr/bin/env python3
"""
Standalone cron scraper script.
This can be run independently from the FastAPI server for scheduled scraping.
"""

import asyncio
from scheduled_scraper import main

if __name__ == "__main__":
    print("[cron] Starting scheduled scraper...")
    asyncio.run(main())
    print("[cron] Scheduled scraper completed.") 